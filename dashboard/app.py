"""Flask routes for the Ecosystem Research dashboard."""

from flask import Blueprint, render_template, jsonify, request, current_app

from .data_service import (
    get_available_chains,
    load_chain_config,
    load_chain_data,
    get_csv_path,
    compute_summary,
    compute_research_flags,
    compute_enrichment_coverage,
    compute_source_breakdown,
    compute_category_breakdown,
    compute_grid_status,
    compute_website_scan_details,
    compute_website_health,
    get_project_table,
    get_filter_options,
)

bp = Blueprint("dashboard", __name__)


def _get_chain():
    """Get the active chain from query params or app default."""
    return request.args.get("chain", current_app.config["DEFAULT_CHAIN"])


# ── HTML Routes ───────────────────────────────────────────────

@bp.route("/")
def index():
    """Main dashboard page with summary charts."""
    chain = _get_chain()
    chains = get_available_chains()
    rows = load_chain_data(chain)
    chain_config = load_chain_config(chain)
    csv_path = get_csv_path(chain)

    summary = compute_summary(rows)
    flags = compute_research_flags(rows)
    enrichment = compute_enrichment_coverage(rows)
    sources = compute_source_breakdown(rows)
    categories = compute_category_breakdown(rows)
    grid_status = compute_grid_status(rows)
    website_scan = compute_website_scan_details(rows)
    website_health = compute_website_health(rows)

    return render_template(
        "index.html",
        chain=chain,
        chains=chains,
        chain_config=chain_config,
        csv_path=str(csv_path) if csv_path else "N/A",
        summary=summary,
        flags=flags,
        enrichment=enrichment,
        sources=sources,
        categories=categories,
        grid_status=grid_status,
        website_scan=website_scan,
        website_health=website_health,
    )


@bp.route("/guide")
def guide():
    """User guide page."""
    chain = _get_chain()
    chains = get_available_chains()
    return render_template("guide.html", chain=chain, chains=chains)


@bp.route("/table")
def table():
    """Full project table with search/filter."""
    chain = _get_chain()
    chains = get_available_chains()
    rows = load_chain_data(chain)

    filters = {
        "search": request.args.get("search", ""),
        "category": request.args.get("category", ""),
        "source": request.args.get("source", ""),
        "grid_matched": request.args.get("grid_matched", ""),
        "has_evidence": request.args.get("has_evidence", ""),
        "website_health": request.args.get("website_health", ""),
    }

    projects = get_project_table(rows, filters)
    filter_options = get_filter_options(rows)

    return render_template(
        "table.html",
        chain=chain,
        chains=chains,
        projects=projects,
        filters=filters,
        filter_options=filter_options,
        total=len(rows),
        shown=len(projects),
    )


# ── JSON API Routes ───────────────────────────────────────────

@bp.route("/api/summary")
def api_summary():
    """JSON endpoint for dashboard data."""
    chain = _get_chain()
    rows = load_chain_data(chain)
    chain_config = load_chain_config(chain)

    return jsonify({
        "chain": chain,
        "summary": compute_summary(rows),
        "flags": compute_research_flags(rows),
        "enrichment": compute_enrichment_coverage(rows),
        "sources": compute_source_breakdown(rows),
        "categories": compute_category_breakdown(rows),
        "grid_status": compute_grid_status(rows),
        "website_scan": compute_website_scan_details(rows),
        "website_health": compute_website_health(rows),
    })


@bp.route("/api/projects")
def api_projects():
    """JSON endpoint for filtered project list."""
    chain = _get_chain()
    rows = load_chain_data(chain)
    filters = {
        "search": request.args.get("search", ""),
        "category": request.args.get("category", ""),
        "source": request.args.get("source", ""),
        "grid_matched": request.args.get("grid_matched", ""),
        "has_evidence": request.args.get("has_evidence", ""),
        "website_health": request.args.get("website_health", ""),
    }
    return jsonify(get_project_table(rows, filters))
