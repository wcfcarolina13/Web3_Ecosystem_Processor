"""
Flask blueprint for the Import Wizard — parse, map, analyze, preview, commit.

Routes:
    GET  /import                   — Import wizard page (HTML)
    POST /api/import/parse         — Parse uploaded CSV or pasted text
    POST /api/import/map           — Auto-map or confirm column mappings
    POST /api/import/analyze       — Split by ecosystem, detect duplicates
    POST /api/import/preview       — Generate merge preview with diffs
    POST /api/import/commit        — Backup + write merged CSVs
"""

import json
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
)

from lib.columns import CORRECT_COLUMNS
from lib.csv_utils import (
    backup_csv,
    find_main_csv,
    load_csv,
    write_csv,
)
from lib.logging_config import get_logger
from lib.import_engine import (
    apply_column_mapping,
    auto_map_columns,
    detect_computed_columns,
    detect_ecosystems,
    execute_merge,
    find_duplicates,
    generate_merge_preview,
    parse_input,
    split_by_ecosystem,
)

from .import_session import import_sessions
from .pipeline_manager import pipeline_manager

logger = get_logger(__name__)

import_bp = Blueprint("import", __name__)

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "chains.json"


def _load_chains_config() -> list:
    """Load chain definitions from config/chains.json."""
    with open(CONFIG_PATH) as f:
        return json.load(f)["chains"]


# ── HTML page ──


@import_bp.route("/import")
def import_page():
    """Render the import wizard page."""
    chains = _load_chains_config()
    return render_template(
        "import.html",
        chains=chains,
        canonical_columns=CORRECT_COLUMNS,
        show_chain_selector=False,
    )


# ── Step 1: Parse ──


@import_bp.route("/api/import/parse", methods=["POST"])
def api_import_parse():
    """
    Parse uploaded CSV or pasted text.

    Accepts either:
      - multipart/form-data with a 'file' field (CSV upload)
      - application/json with a 'text' field (clipboard paste)

    Returns session_id, stats, and sample rows.
    """
    content = None
    input_method = None
    filename = None

    # Try file upload first
    file = request.files.get("file")
    if file and file.filename:
        if not file.filename.endswith((".csv", ".tsv", ".txt")):
            return jsonify({"error": "File must be .csv, .tsv, or .txt"}), 400
        try:
            content = file.read().decode("utf-8")
        except UnicodeDecodeError:
            file.seek(0)
            content = file.read().decode("latin-1")
        input_method = "file"
        filename = file.filename
    else:
        # Try JSON body with text field
        data = request.get_json(force=True, silent=True) or {}
        text = data.get("text", "").strip()
        if text:
            content = text
            input_method = "paste"

    if not content:
        return jsonify({"error": "No file or text provided"}), 400

    # Parse
    try:
        headers, rows = parse_input(content)
    except Exception as e:
        return jsonify({"error": f"Failed to parse input: {e}"}), 400

    if not rows:
        return jsonify({"error": "No data rows found"}), 400

    # Detect ecosystems
    ecosystem_counts = detect_ecosystems(rows)

    # Create session
    session = import_sessions.create_session()
    import_sessions.update_session(
        session.session_id,
        raw_headers=headers,
        raw_rows=rows,
        detected_ecosystems=ecosystem_counts,
        input_method=input_method,
        filename=filename,
    )

    # Sample rows (first 5)
    sample = rows[:5]

    logger.info(
        "Import parse: %d rows, %d columns, %d ecosystems (session %s)",
        len(rows),
        len(headers),
        len(ecosystem_counts),
        session.session_id,
    )

    return jsonify({
        "session_id": session.session_id,
        "row_count": len(rows),
        "column_count": len(headers),
        "columns": headers,
        "ecosystem_counts": ecosystem_counts,
        "sample_rows": sample,
    })


# ── Step 2: Column Mapping ──


@import_bp.route("/api/import/map", methods=["POST"])
def api_import_map():
    """
    Auto-generate or confirm column mappings.

    JSON body:
      - session_id: required
      - mappings: optional dict of {incoming: canonical} overrides
      - confirm: if true, apply mappings and transform rows
    """
    data = request.get_json(force=True, silent=True) or {}
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    session = import_sessions.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found or expired"}), 400

    if not session.raw_rows:
        return jsonify({"error": "No data parsed (complete step 1 first)"}), 400

    confirm = data.get("confirm", False)

    if not confirm:
        # Auto-generate mappings
        auto = auto_map_columns(session.raw_headers)
        computed = detect_computed_columns(session.raw_rows)

        import_sessions.update_session(
            session_id,
            auto_mappings=auto,
            computed_columns=computed,
        )

        return jsonify({
            "session_id": session_id,
            "mappings": auto,
            "computed_columns": computed,
            "canonical_columns": list(CORRECT_COLUMNS),
        })

    # Confirm mode: apply user-provided or auto mappings
    user_mappings = data.get("mappings")
    if not user_mappings:
        # Fall back to auto-generated
        if not session.auto_mappings:
            return jsonify({"error": "No mappings available. Generate auto-map first."}), 400
        user_mappings = {
            m["incoming"]: (m["mapped_to"] or "__skip__")
            for m in session.auto_mappings
        }

    computed = session.computed_columns or detect_computed_columns(session.raw_rows)

    # Apply mappings
    mapped = apply_column_mapping(session.raw_rows, user_mappings, computed)

    import_sessions.update_session(
        session_id,
        column_mapping=user_mappings,
        computed_columns=computed,
        mapped_rows=mapped,
    )

    logger.info(
        "Import map confirmed: %d rows mapped (session %s)",
        len(mapped),
        session_id,
    )

    return jsonify({
        "session_id": session_id,
        "status": "mapped",
        "mapped_row_count": len(mapped),
        "sample_rows": mapped[:5],
    })


# ── Step 3: Analyze (Ecosystem Split + Duplicates) ──


@import_bp.route("/api/import/analyze", methods=["POST"])
def api_import_analyze():
    """
    Split rows by ecosystem and detect duplicates against existing chain CSVs.

    JSON body:
      - session_id: required
    """
    data = request.get_json(force=True, silent=True) or {}
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    session = import_sessions.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found or expired"}), 400

    if not session.mapped_rows:
        return jsonify({"error": "Column mapping not confirmed (complete step 2 first)"}), 400

    chains_config = _load_chains_config()

    # Split by ecosystem
    splits, unmatched = split_by_ecosystem(session.mapped_rows, chains_config)

    # For each known chain, detect duplicates
    all_duplicates = {}
    all_new_rows = {}
    ecosystems_info = []

    for chain_id, rows in splits.items():
        # Check if this is a known chain
        is_known = any(c["id"] == chain_id for c in chains_config)

        if not is_known:
            # Unknown chain — skip duplicate detection
            all_new_rows[chain_id] = rows
            ecosystems_info.append({
                "chain": chain_id,
                "chain_name": chain_id,
                "total_incoming": len(rows),
                "new_rows": len(rows),
                "duplicate_rows": 0,
                "has_existing_csv": False,
                "existing_row_count": 0,
                "is_known_chain": False,
            })
            continue

        # Load existing CSV
        csv_path = find_main_csv(chain_id)
        existing_rows = []
        if csv_path and csv_path.exists():
            try:
                existing_rows = load_csv(csv_path, validate=False)
            except Exception:
                pass

        # Find duplicates
        dupes, new = find_duplicates(rows, existing_rows)
        all_duplicates[chain_id] = dupes
        all_new_rows[chain_id] = new

        chain_name = next(
            (c["name"] for c in chains_config if c["id"] == chain_id),
            chain_id,
        )

        ecosystems_info.append({
            "chain": chain_id,
            "chain_name": chain_name,
            "total_incoming": len(rows),
            "new_rows": len(new),
            "duplicate_rows": len(dupes),
            "has_existing_csv": bool(csv_path and csv_path.exists()),
            "existing_row_count": len(existing_rows),
            "is_known_chain": True,
        })

    import_sessions.update_session(
        session_id,
        ecosystem_splits=splits,
        duplicates=all_duplicates,
        new_rows=all_new_rows,
        unmatched_ecosystems=unmatched,
    )

    # Compute totals
    total_new = sum(len(v) for v in all_new_rows.values())
    total_dupes = sum(len(v) for v in all_duplicates.values())

    logger.info(
        "Import analyze: %d ecosystems, %d new, %d duplicates (session %s)",
        len(ecosystems_info),
        total_new,
        total_dupes,
        session_id,
    )

    return jsonify({
        "session_id": session_id,
        "ecosystems": ecosystems_info,
        "unmatched_ecosystems": unmatched,
        "totals": {
            "total_rows": len(session.mapped_rows),
            "matched_to_chains": sum(
                e["total_incoming"] for e in ecosystems_info if e["is_known_chain"]
            ),
            "unmatched": sum(
                e["total_incoming"] for e in ecosystems_info if not e["is_known_chain"]
            ),
            "new": total_new,
            "duplicates": total_dupes,
        },
    })


# ── Step 4: Preview ──


@import_bp.route("/api/import/preview", methods=["POST"])
def api_import_preview():
    """
    Generate merge preview with side-by-side diffs.

    JSON body:
      - session_id: required
      - strategies: optional dict of {chain: {column: strategy}} overrides
    """
    data = request.get_json(force=True, silent=True) or {}
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    session = import_sessions.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found or expired"}), 400

    if session.duplicates is None or session.new_rows is None:
        return jsonify({"error": "Analysis not run (complete step 3 first)"}), 400

    user_strategies = data.get("strategies", {})
    computed_cols = session.computed_columns or []

    chains_preview = []
    all_strategies = {}

    for chain_id in set(list(session.duplicates.keys()) + list(session.new_rows.keys())):
        dupes = session.duplicates.get(chain_id, [])
        new = session.new_rows.get(chain_id, [])
        chain_strategies = user_strategies.get(chain_id, {})
        all_strategies[chain_id] = chain_strategies

        preview = generate_merge_preview(
            dupes, new, chain_strategies, computed_cols
        )

        # Detect new columns (in incoming but not in canonical)
        new_columns = []
        if new:
            for col in new[0].keys():
                if col not in CORRECT_COLUMNS and col not in new_columns:
                    new_columns.append(col)

        chains_preview.append({
            "chain": chain_id,
            **preview,
            "new_columns": new_columns,
        })

    import_sessions.update_session(
        session_id,
        merge_strategies=all_strategies,
        merge_preview={cp["chain"]: cp for cp in chains_preview},
    )

    logger.info("Import preview generated (session %s)", session_id)

    return jsonify({
        "session_id": session_id,
        "chains": chains_preview,
    })


# ── Step 5: Commit ──


@import_bp.route("/api/import/commit", methods=["POST"])
def api_import_commit():
    """
    Execute the merge: create backups and write merged CSVs.

    JSON body:
      - session_id: required
    """
    # Mutual exclusion
    if pipeline_manager.is_running:
        return jsonify({"error": "Cannot import while pipeline is running"}), 409

    data = request.get_json(force=True, silent=True) or {}
    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    session = import_sessions.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found or expired"}), 400

    if session.merge_preview is None:
        return jsonify({"error": "Preview not generated (complete step 4 first)"}), 400

    chains_config = _load_chains_config()
    computed_cols = session.computed_columns or []
    results = []

    for chain_id in session.merge_preview:
        # Only commit known chains
        is_known = any(c["id"] == chain_id for c in chains_config)
        if not is_known:
            continue

        dupes = session.duplicates.get(chain_id, [])
        new = session.new_rows.get(chain_id, [])
        strategies = session.merge_strategies.get(chain_id, {})

        # Load existing CSV (or start fresh)
        csv_path = find_main_csv(chain_id)
        existing_rows = []

        if csv_path and csv_path.exists():
            try:
                existing_rows = load_csv(csv_path, validate=False)
            except Exception:
                pass
        else:
            # Create new CSV path
            data_dir = PROJECT_ROOT / "data" / chain_id
            data_dir.mkdir(parents=True, exist_ok=True)
            csv_path = data_dir / f"{chain_id}_ecosystem_research.csv"

        # Create backup if file exists
        backup_path = None
        if csv_path.exists():
            try:
                backup_path = backup_csv(csv_path, suffix="pre-import")
            except Exception as e:
                logger.warning("Failed to backup %s: %s", csv_path, e)

        # Execute merge
        try:
            merged, added, updated, skipped = execute_merge(
                chain=chain_id,
                existing_rows=existing_rows,
                new_rows=new,
                duplicates=dupes,
                strategies=strategies,
                computed_cols=computed_cols,
            )

            # Determine columns: canonical + any extras
            all_cols = list(CORRECT_COLUMNS)
            for row in merged:
                for col in row:
                    if col not in all_cols:
                        all_cols.append(col)

            write_csv(merged, csv_path, columns=all_cols)

            results.append({
                "chain": chain_id,
                "rows_added": added,
                "rows_updated": updated,
                "rows_skipped": skipped,
                "total_rows_after": len(merged),
                "backup_path": str(backup_path) if backup_path else None,
                "csv_path": str(csv_path),
            })

            logger.info(
                "Import commit for %s: +%d updated=%d skipped=%d (total=%d)",
                chain_id,
                added,
                updated,
                skipped,
                len(merged),
            )

        except Exception as e:
            logger.error("Import commit failed for %s: %s", chain_id, e)
            results.append({
                "chain": chain_id,
                "error": str(e),
            })

    # Store result
    import_sessions.update_session(session_id, commit_result=results)

    total_added = sum(r.get("rows_added", 0) for r in results if "error" not in r)
    total_updated = sum(r.get("rows_updated", 0) for r in results if "error" not in r)

    return jsonify({
        "session_id": session_id,
        "results": results,
        "summary": {
            "chains_affected": len([r for r in results if "error" not in r]),
            "total_added": total_added,
            "total_updated": total_updated,
        },
    })
