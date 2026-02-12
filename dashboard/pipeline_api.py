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
