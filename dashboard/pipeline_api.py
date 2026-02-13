"""
Flask blueprint for the pipeline UI — upload, run, progress, download.

Routes:
    GET  /pipeline                  — Pipeline page (HTML)
    POST /api/upload                — Upload a CSV file
    POST /api/pipeline/start        — Start the enrichment pipeline
    GET  /api/pipeline/status/<id>  — Poll pipeline progress
    GET  /api/download/<chain>      — Download the enriched CSV
    GET  /api/chains                — List available chains
"""

import json
import os
import re
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
)

from lib.columns import REQUIRED_COLUMNS
from lib.csv_utils import find_main_csv, load_csv, write_csv
from lib.logging_config import get_logger
from .pipeline_manager import pipeline_manager
from .scraper_manager import scraper_manager

logger = get_logger(__name__)

pipeline_bp = Blueprint("pipeline", __name__)

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "chains.json"


def _load_chains_config() -> list:
    """Load chain definitions from config/chains.json."""
    with open(CONFIG_PATH) as f:
        return json.load(f)["chains"]


def _chain_info() -> list:
    """Return chain list with data availability info."""
    chains = _load_chains_config()
    result = []
    for c in chains:
        csv_path = find_main_csv(c["id"])
        row_count = 0
        if csv_path and csv_path.exists():
            try:
                rows = load_csv(csv_path, validate=False)
                row_count = len(rows)
            except Exception:
                pass
        result.append({
            "id": c["id"],
            "name": c["name"],
            "has_data": csv_path is not None and csv_path.exists(),
            "row_count": row_count,
            "target_assets": c.get("target_assets", ["USDT", "USDC"]),
        })
    return result


# ── HTML page ──


@pipeline_bp.route("/pipeline")
def pipeline_page():
    """Render the pipeline UI page."""
    from scripts.enrich_all import STEPS, STEP_DESCRIPTIONS

    chain = request.args.get("chain", current_app.config.get("DEFAULT_CHAIN", "near"))
    chains_list = _load_chains_config()
    chain_data = _chain_info()

    return render_template(
        "pipeline.html",
        chain=chain,
        chains=chains_list,
        chain_data=chain_data,
        steps=STEPS,
        step_descriptions=STEP_DESCRIPTIONS,
        is_running=pipeline_manager.is_running,
        is_discovering=scraper_manager.is_running,
        show_chain_selector=False,
    )


# ── API routes ──


@pipeline_bp.route("/api/chains")
def api_chains():
    """List all chains with data info."""
    return jsonify(_chain_info())


@pipeline_bp.route("/api/upload", methods=["POST"])
def api_upload():
    """
    Upload a CSV file for a chain.

    Expects multipart form with:
      - chain: chain ID (e.g., "near")
      - file: the CSV file
    """
    if pipeline_manager.is_running:
        return jsonify({"error": "Cannot upload while pipeline is running"}), 409

    chain = request.form.get("chain")
    if not chain:
        return jsonify({"error": "Missing 'chain' field"}), 400

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file uploaded"}), 400

    if not file.filename.endswith(".csv"):
        return jsonify({"error": "File must be a .csv"}), 400

    # Read and validate the CSV
    import csv
    import io

    try:
        content = file.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
    except Exception as e:
        return jsonify({"error": f"Failed to parse CSV: {e}"}), 400

    if not rows:
        return jsonify({"error": "CSV is empty"}), 400

    # Validate required columns
    headers = set(rows[0].keys()) if rows else set()
    missing = REQUIRED_COLUMNS - headers
    if missing:
        return jsonify({
            "error": f"CSV missing required columns: {', '.join(sorted(missing))}",
            "required": sorted(REQUIRED_COLUMNS),
            "found": sorted(headers),
        }), 400

    # Write to data/<chain>/
    data_dir = PROJECT_ROOT / "data" / chain.lower()
    data_dir.mkdir(parents=True, exist_ok=True)
    output_path = data_dir / f"{chain.lower()}_ecosystem_research.csv"

    # Use the columns from the uploaded file (preserve extra columns)
    write_csv(rows, output_path, columns=list(reader.fieldnames or rows[0].keys()))
    logger.info("Uploaded %d rows to %s", len(rows), output_path)

    return jsonify({
        "message": f"Uploaded {len(rows)} rows for {chain}",
        "rows": len(rows),
        "path": str(output_path),
    })


@pipeline_bp.route("/api/pipeline/start", methods=["POST"])
def api_pipeline_start():
    """
    Start the enrichment pipeline.

    JSON body:
      - chain: chain ID
      - skip: list of step names to skip (optional)
    """
    # Mutual exclusion
    if scraper_manager.is_running:
        return jsonify({"error": "Cannot run pipeline while discovery is running"}), 409

    data = request.get_json(force=True, silent=True) or {}
    chain = data.get("chain")
    if not chain:
        return jsonify({"error": "Missing 'chain' field"}), 400

    # Find the CSV
    csv_path = find_main_csv(chain)
    if not csv_path or not csv_path.exists():
        return jsonify({"error": f"No CSV found for chain '{chain}'"}), 404

    # Load chain config for target assets
    from scripts.enrich_all import STEPS, load_chain_config

    try:
        chain_config = load_chain_config(chain)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    target_assets = chain_config.get("target_assets", ["USDT", "USDC"])

    # Determine steps
    skip = set(data.get("skip", []))
    steps = [s for s in STEPS if s not in skip]

    if not steps:
        return jsonify({"error": "No steps selected"}), 400

    # Start the pipeline
    try:
        job_id = pipeline_manager.start_pipeline(
            chain=chain,
            csv_path=csv_path,
            target_assets=target_assets,
            steps=steps,
        )
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify({"job_id": job_id, "chain": chain, "steps": steps})


@pipeline_bp.route("/api/pipeline/status/<job_id>")
def api_pipeline_status(job_id):
    """Poll pipeline progress."""
    job = pipeline_manager.get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@pipeline_bp.route("/api/download/<chain>")
def api_download(chain):
    """Download the enriched CSV for a chain."""
    csv_path = find_main_csv(chain)
    if not csv_path or not csv_path.exists():
        return jsonify({"error": f"No CSV found for chain '{chain}'"}), 404

    return send_file(
        csv_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name=csv_path.name,
    )


# ── Add Chain ──


@pipeline_bp.route("/api/chains/add", methods=["POST"])
def api_add_chain():
    """
    Add a new chain to config/chains.json.

    JSON body:
      - id: chain ID (lowercase, alphanumeric + hyphens)
      - name: display name
      - defillama_slug: DefiLlama chain name (e.g., "Solana")
      - target_assets: comma-separated asset list (optional, default "USDT,USDC")
    """
    data = request.get_json(force=True, silent=True) or {}

    chain_id = (data.get("id") or "").strip().lower()
    name = (data.get("name") or "").strip()
    defillama_slug = (data.get("defillama_slug") or "").strip()
    target_assets_raw = (data.get("target_assets") or "USDT,USDC").strip()

    # Validate
    if not chain_id:
        return jsonify({"error": "Chain ID is required"}), 400
    if not re.match(r"^[a-z0-9][a-z0-9\-]*$", chain_id):
        return jsonify({"error": "Chain ID must be lowercase alphanumeric (hyphens OK)"}), 400
    if not name:
        return jsonify({"error": "Display name is required"}), 400
    if not defillama_slug:
        return jsonify({"error": "DefiLlama slug is required"}), 400

    # Parse target assets
    target_assets = [a.strip().upper() for a in target_assets_raw.split(",") if a.strip()]
    if not target_assets:
        target_assets = ["USDT", "USDC"]

    # Load existing config
    try:
        with open(CONFIG_PATH) as f:
            config = json.load(f)
    except Exception as e:
        return jsonify({"error": f"Failed to load chains.json: {e}"}), 500

    # Check for duplicate ID
    existing_ids = {c["id"] for c in config["chains"]}
    if chain_id in existing_ids:
        return jsonify({"error": f"Chain '{chain_id}' already exists"}), 409

    # Build chain entry
    new_chain = {
        "id": chain_id,
        "name": name,
        "target_assets": target_assets,
        "sources": {
            "defillama": {
                "chain_slug": defillama_slug,
                "url": f"https://defillama.com/chain/{defillama_slug}",
            }
        },
    }
    config["chains"].append(new_chain)

    # Atomic write: temp file + os.replace
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=CONFIG_PATH.parent, suffix=".tmp", prefix="chains_"
        )
        with os.fdopen(fd, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CONFIG_PATH)
    except Exception as e:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return jsonify({"error": f"Failed to write chains.json: {e}"}), 500

    # Create data directory
    data_dir = PROJECT_ROOT / "data" / chain_id
    data_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Added chain '%s' (%s), DefiLlama slug=%s", chain_id, name, defillama_slug)
    return jsonify({"message": f"Chain '{name}' added", "chain": new_chain})


# ── Discovery ──


@pipeline_bp.route("/api/discover/sources/<chain>")
def api_discover_sources(chain):
    """List available discovery sources for a chain."""
    # DefiLlama is always available
    sources = [
        {
            "id": "defillama",
            "name": "DefiLlama",
            "description": "DeFi protocols with TVL, URLs, and social links",
        }
    ]
    return jsonify(sources)


@pipeline_bp.route("/api/discover/start", methods=["POST"])
def api_discover_start():
    """
    Start project discovery.

    JSON body:
      - chain: chain ID
      - sources: list of source IDs (e.g., ["defillama"])
    """
    # Mutual exclusion: neither pipeline nor discovery should be running
    if pipeline_manager.is_running:
        return jsonify({"error": "Cannot discover while pipeline is running"}), 409
    if scraper_manager.is_running:
        return jsonify({"error": "A discovery job is already running"}), 409

    data = request.get_json(force=True, silent=True) or {}
    chain = data.get("chain")
    sources = data.get("sources", [])

    if not chain:
        return jsonify({"error": "Missing 'chain' field"}), 400
    if not sources:
        return jsonify({"error": "No sources selected"}), 400

    try:
        job_id = scraper_manager.start_discovery(chain=chain, sources=sources)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify({"job_id": job_id, "chain": chain, "sources": sources})


@pipeline_bp.route("/api/discover/status/<job_id>")
def api_discover_status(job_id):
    """Poll discovery progress."""
    job = scraper_manager.get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


# ── Extension Download ──

EXTENSION_DIR = PROJECT_ROOT / "extension"
EXTENSION_EXCLUDE = {".DS_Store", "__pycache__", ".git", "Thumbs.db"}


@pipeline_bp.route("/api/download/extension")
def api_download_extension():
    """Download the Chrome extension as a ZIP file."""
    if not EXTENSION_DIR.exists():
        return jsonify({"error": "Extension directory not found"}), 404

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(EXTENSION_DIR):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in EXTENSION_EXCLUDE]
            for fname in files:
                if fname in EXTENSION_EXCLUDE:
                    continue
                fpath = Path(root) / fname
                arcname = fpath.relative_to(EXTENSION_DIR)
                zf.write(fpath, arcname)

    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name="ecosystem-scraper.zip",
    )
