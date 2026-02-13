"""
Data loading and metric computation for the dashboard.

Reads CSV files via lib.csv_utils and computes all dashboard metrics.
CSV is re-read on each request (~791 rows, <50ms, no caching needed).
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import List, Dict, Optional

from lib.csv_utils import load_csv, find_main_csv

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "chains.json"

# Boolean columns rendered as checkboxes in the Full view
BOOLEAN_COLUMNS = {
    "Suspect USDT support?",
    "Skip",
    "Added",
    "Web3 but no stablecoin",
    "General Stablecoin Adoption",
    "To be Added",
    "Processed?",
    "In Admin",
    "TG/TON appstore (no main URL)",
}


# ── Chain config ──────────────────────────────────────────────

def get_available_chains() -> List[Dict]:
    """Return chains that have data directories with CSV files."""
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    available = []
    for c in config["chains"]:
        csv_path = find_main_csv(c["id"])
        if csv_path and csv_path.exists():
            available.append({
                "id": c["id"],
                "name": c["name"],
                "target_assets": c.get("target_assets", []),
            })
    return available


def load_chain_config(chain: str) -> dict:
    """Load a specific chain's config from chains.json."""
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    for c in config["chains"]:
        if c["id"] == chain:
            return c
    return {"id": chain, "name": chain.title(), "target_assets": []}


def load_chain_data(chain: str) -> List[Dict]:
    """Load the main ecosystem CSV for a chain."""
    csv_path = find_main_csv(chain)
    if not csv_path or not csv_path.exists():
        return []
    return load_csv(csv_path, validate=False)


def get_csv_path(chain: str) -> Optional[Path]:
    """Get the CSV file path for display purposes."""
    return find_main_csv(chain)


# ── Helpers ───────────────────────────────────────────────────

def _is_true(val: str) -> bool:
    """Check if a CSV field is truthy."""
    return val.strip().upper() in ("TRUE", "YES", "1")


def _is_nonempty(val: str) -> bool:
    """Check if a CSV field has content."""
    return bool(val.strip())


def _split_semicolons(val: str) -> List[str]:
    """Split a semicolon-separated field into cleaned parts."""
    if not val.strip():
        return []
    return [p.strip() for p in val.split(";") if p.strip()]


def _split_pipes(val: str) -> List[str]:
    """Split a pipe-separated field into cleaned parts."""
    if not val.strip():
        return []
    return [p.strip() for p in val.split("|") if p.strip()]


# ── Summary stats ─────────────────────────────────────────────

def compute_summary(rows: List[Dict]) -> dict:
    """Compute top-level summary statistics."""
    total = len(rows)
    if total == 0:
        return {k: 0 for k in [
            "total_projects", "with_website", "with_x_link", "with_telegram",
            "with_category", "skip_count", "added_count", "processed_count",
            "in_admin_count", "grid_matched", "grid_match_pct",
            "with_evidence", "with_evidence_pct",
        ]}

    with_website = sum(1 for r in rows if _is_nonempty(r.get("Website", "")))
    with_x = sum(1 for r in rows if _is_nonempty(r.get("X Link", "")))
    with_tg = sum(1 for r in rows if _is_nonempty(r.get("Telegram", "")))
    with_cat = sum(1 for r in rows if _is_nonempty(r.get("Category", "")))
    skip = sum(1 for r in rows if _is_true(r.get("Skip", "")))
    added = sum(1 for r in rows if _is_true(r.get("Added", "")))
    processed = sum(1 for r in rows if _is_true(r.get("Processed?", "")))
    in_admin = sum(1 for r in rows if _is_true(r.get("In Admin", "")))
    grid_matched = sum(1 for r in rows if _is_nonempty(r.get("Profile Name", "")))
    with_evidence = sum(1 for r in rows if _is_nonempty(r.get("Evidence & Source URLs", "")))

    return {
        "total_projects": total,
        "with_website": with_website,
        "with_website_pct": round(with_website / total * 100, 1),
        "with_x_link": with_x,
        "with_telegram": with_tg,
        "with_category": with_cat,
        "skip_count": skip,
        "added_count": added,
        "processed_count": processed,
        "in_admin_count": in_admin,
        "grid_matched": grid_matched,
        "grid_match_pct": round(grid_matched / total * 100, 1),
        "with_evidence": with_evidence,
        "with_evidence_pct": round(with_evidence / total * 100, 1),
    }


# ── Research flags ────────────────────────────────────────────

def compute_research_flags(rows: List[Dict]) -> dict:
    """Compute research boolean flag counts."""
    return {
        "suspect_usdt": sum(1 for r in rows if _is_true(r.get("Suspect USDT support?", ""))),
        "web3_no_stable": sum(1 for r in rows if _is_true(r.get("Web3 but no stablecoin", ""))),
        "general_stablecoin": sum(1 for r in rows if _is_true(r.get("General Stablecoin Adoption", ""))),
    }


# ── Enrichment coverage ──────────────────────────────────────

def compute_enrichment_coverage(rows: List[Dict]) -> dict:
    """
    Parse Evidence & Source URLs column for enrichment source prefixes.

    Actual formats in the data:
    - "Grid: USDT (supported_by); USDC (supported_by)"
    - "USDT: $217;797"  (DefiLlama token holdings)
    - "SOL: deployed on solana (CoinGecko)"
    - "website-scan: scanned"
    - Pipe | separates sources
    """
    grid_count = 0
    defillama_count = 0
    coingecko_count = 0
    website_count = 0
    no_evidence = 0

    for r in rows:
        evidence = r.get("Evidence & Source URLs", "").strip()
        if not evidence:
            no_evidence += 1
            continue

        parts = _split_pipes(evidence)
        has_grid = False
        has_defillama = False
        has_coingecko = False
        has_website = False

        for part in parts:
            p = part.strip()
            if p.startswith("Grid:"):
                has_grid = True
            elif "(CoinGecko)" in p:
                has_coingecko = True
            elif p.startswith("website-scan:"):
                has_website = True
            elif re.match(r"^(USDT|USDC):\s*\$", p):
                has_defillama = True
            elif p.startswith("DeFi:") or p.startswith("chains:"):
                has_defillama = True

        if has_grid:
            grid_count += 1
        if has_defillama:
            defillama_count += 1
        if has_coingecko:
            coingecko_count += 1
        if has_website:
            website_count += 1

    total = len(rows)
    return {
        "grid": grid_count,
        "grid_pct": round(grid_count / total * 100, 1) if total else 0,
        "defillama": defillama_count,
        "defillama_pct": round(defillama_count / total * 100, 1) if total else 0,
        "coingecko": coingecko_count,
        "coingecko_pct": round(coingecko_count / total * 100, 1) if total else 0,
        "website_scan": website_count,
        "website_scan_pct": round(website_count / total * 100, 1) if total else 0,
        "no_evidence": no_evidence,
        "no_evidence_pct": round(no_evidence / total * 100, 1) if total else 0,
    }


# ── Source attribution ────────────────────────────────────────

def compute_source_breakdown(rows: List[Dict]) -> List[Dict]:
    """
    Parse Source column (semicolon-separated), count projects per source.
    Returns sorted list of {source, count}.
    """
    counter = Counter()
    for r in rows:
        sources = _split_semicolons(r.get("Source", ""))
        for s in sources:
            # Normalize: strip whitespace, lowercase for grouping
            counter[s.strip()] += 1

    # Sort by count desc, return top entries
    return [{"source": s, "count": c} for s, c in counter.most_common(20)]


# ── Category breakdown ────────────────────────────────────────

def compute_category_breakdown(rows: List[Dict]) -> List[Dict]:
    """
    Parse Category column (semicolon-separated), count per category.
    Normalizes case (title case).
    """
    counter = Counter()
    for r in rows:
        cats = _split_semicolons(r.get("Category", ""))
        for cat in cats:
            normalized = cat.strip().title()
            if normalized:
                counter[normalized] += 1

    return [{"category": c, "count": n} for c, n in counter.most_common(15)]


# ── Grid matching ─────────────────────────────────────────────

def compute_grid_status(rows: List[Dict]) -> dict:
    """
    Compute Grid matching breakdown:
    - matched vs unmatched
    - The Grid Status distribution
    - Matched via distribution
    """
    matched = 0
    unmatched = 0
    status_counter = Counter()
    method_counter = Counter()

    for r in rows:
        profile = r.get("Profile Name", "").strip()
        if profile:
            matched += 1
            status = r.get("The Grid Status", "").strip()
            method = r.get("Matched via", "").strip()
            if status:
                status_counter[status] += 1
            if method:
                method_counter[method] += 1
        else:
            unmatched += 1

    return {
        "matched": matched,
        "unmatched": unmatched,
        "statuses": [{"status": s, "count": c} for s, c in status_counter.most_common()],
        "methods": [{"method": m, "count": c} for m, c in method_counter.most_common()],
    }


# ── Website scan results ─────────────────────────────────────

def compute_website_scan_details(rows: List[Dict]) -> dict:
    """
    Parse Notes for [UNVERIFIED website-scan] entries to show
    what assets were detected via keyword scanning.
    """
    asset_counter = Counter()
    stablecoin_mentions = 0
    web3_signals = 0
    total_hits = 0

    for r in rows:
        notes = r.get("Notes", "")
        if "[UNVERIFIED website-scan]" not in notes:
            continue

        total_hits += 1
        # Extract the scan portion after [UNVERIFIED website-scan]
        idx = notes.index("[UNVERIFIED website-scan]")
        scan_text = notes[idx:]

        # Check for specific asset keywords
        for asset in ["USDT", "USDC", "SOL", "STRK", "ADA", "APT", "ETH", "BTC"]:
            if f"{asset} keywords" in scan_text:
                asset_counter[asset] += 1

        if "stablecoin mentions" in scan_text:
            stablecoin_mentions += 1
        if "web3" in scan_text.lower():
            web3_signals += 1

    return {
        "total_hits": total_hits,
        "asset_hits": [{"asset": a, "count": c} for a, c in asset_counter.most_common()],
        "stablecoin_mentions": stablecoin_mentions,
        "web3_signals": web3_signals,
    }


# ── Website health ───────────────────────────────────────────

def _get_health_status(row: Dict) -> str:
    """Extract health-check status from Evidence column."""
    evidence = row.get("Evidence & Source URLs", "")
    match = re.search(r"health-check:\s*(\w+)", evidence)
    return match.group(1) if match else ""


def _extract_health_detail(evidence: str) -> str:
    """Extract detail from health-check marker (e.g., 'dead (HTTP 404)' → 'HTTP 404')."""
    match = re.search(r"health-check:\s*\w+\s*\(([^)]+)\)", evidence)
    return match.group(1) if match else ""


def compute_website_health(rows: List[Dict]) -> dict:
    """
    Parse Evidence for health-check markers.
    Returns counts of alive, dead, timeout, dns_fail, error, unchecked.
    """
    alive = 0
    dead = 0
    timeout = 0
    dns_fail = 0
    error = 0
    unchecked = 0
    no_url = 0
    dead_projects = []

    for r in rows:
        website = r.get("Website", "").strip()
        status = _get_health_status(r)

        if not website:
            no_url += 1
            continue

        if not status:
            unchecked += 1
            continue

        evidence = r.get("Evidence & Source URLs", "")
        proj_info = {
            "name": r.get("Project Name", "").strip(),
            "website": website,
            "detail": _extract_health_detail(evidence),
        }

        if status == "alive":
            alive += 1
        elif status == "dead":
            dead += 1
            dead_projects.append(proj_info)
        elif status == "timeout":
            timeout += 1
            proj_info["detail"] = proj_info["detail"] or "timeout"
            dead_projects.append(proj_info)
        elif status == "dns_fail":
            dns_fail += 1
            proj_info["detail"] = proj_info["detail"] or "DNS failure"
            dead_projects.append(proj_info)
        elif status == "error":
            error += 1
            proj_info["detail"] = proj_info["detail"] or "connection error"
            dead_projects.append(proj_info)

    total_checked = alive + dead + timeout + dns_fail + error
    total_dead = dead + timeout + dns_fail + error

    return {
        "alive": alive,
        "dead": dead,
        "timeout": timeout,
        "dns_fail": dns_fail,
        "error": error,
        "unchecked": unchecked,
        "no_url": no_url,
        "total_checked": total_checked,
        "total_dead": total_dead,
        "dead_pct": round(total_dead / total_checked * 100, 1) if total_checked else 0,
        "alive_pct": round(alive / total_checked * 100, 1) if total_checked else 0,
        "dead_projects": sorted(dead_projects, key=lambda x: x["name"])[:50],
    }


# ── Project table ─────────────────────────────────────────────

def get_project_table(rows: List[Dict], filters: dict) -> List[Dict]:
    """
    Return filtered project rows with display-ready columns.
    """
    result = []
    search = filters.get("search", "").strip().lower()
    cat_filter = filters.get("category", "").strip()
    source_filter = filters.get("source", "").strip()
    grid_filter = filters.get("grid_matched", "").strip()
    evidence_filter = filters.get("has_evidence", "").strip()
    health_filter = filters.get("website_health", "").strip()

    for r in rows:
        name = r.get("Project Name", "").strip()

        # Apply filters
        if search and search not in name.lower():
            continue
        if cat_filter and cat_filter.lower() not in r.get("Category", "").lower():
            continue
        if source_filter and source_filter.lower() not in r.get("Source", "").lower():
            continue
        if grid_filter == "yes" and not _is_nonempty(r.get("Profile Name", "")):
            continue
        if grid_filter == "no" and _is_nonempty(r.get("Profile Name", "")):
            continue
        if evidence_filter == "yes" and not _is_nonempty(r.get("Evidence & Source URLs", "")):
            continue
        if evidence_filter == "no" and _is_nonempty(r.get("Evidence & Source URLs", "")):
            continue

        # Website health filter
        health = _get_health_status(r)
        if health_filter == "alive" and health != "alive":
            continue
        if health_filter == "dead" and health not in ("dead", "timeout", "dns_fail", "error"):
            continue
        if health_filter == "unchecked" and health:
            continue

        # Build display row
        evidence = r.get("Evidence & Source URLs", "").strip()
        result.append({
            "name": name,
            "category": r.get("Category", "").strip(),
            "source": r.get("Source", "").strip(),
            "website": r.get("Website", "").strip(),
            "x_handle": r.get("X Handle", "").strip(),
            "grid_status": r.get("The Grid Status", "").strip(),
            "profile_name": r.get("Profile Name", "").strip(),
            "evidence": evidence[:120] + ("..." if len(evidence) > 120 else ""),
            "suspect_usdt": _is_true(r.get("Suspect USDT support?", "")),
            "general_stablecoin": _is_true(r.get("General Stablecoin Adoption", "")),
            "web3_no_stable": _is_true(r.get("Web3 but no stablecoin", "")),
            "skip": _is_true(r.get("Skip", "")),
            "added": _is_true(r.get("Added", "")),
            "notes": r.get("Notes", "").strip()[:150],
            "website_health": health or "unchecked",
        })

    return result


def get_all_columns(rows: List[Dict]) -> List[str]:
    """Get all column headers present in the CSV data, preserving order."""
    if not rows:
        return []
    # Use the first row's keys (csv.DictReader preserves header order)
    return list(rows[0].keys())


def get_project_table_full(rows: List[Dict], filters: dict) -> List[Dict]:
    """
    Return filtered project rows with ALL columns (for full view).
    Same filter logic as get_project_table() but returns raw row dicts.
    """
    result = []
    search = filters.get("search", "").strip().lower()
    cat_filter = filters.get("category", "").strip()
    source_filter = filters.get("source", "").strip()
    grid_filter = filters.get("grid_matched", "").strip()
    evidence_filter = filters.get("has_evidence", "").strip()
    health_filter = filters.get("website_health", "").strip()

    for r in rows:
        name = r.get("Project Name", r.get("Name", "")).strip()

        # Apply same filters
        if search and search not in name.lower():
            continue
        if cat_filter and cat_filter.lower() not in r.get("Category", "").lower():
            continue
        if source_filter and source_filter.lower() not in r.get("Source", "").lower():
            continue
        if grid_filter == "yes" and not _is_nonempty(r.get("Profile Name", "")):
            continue
        if grid_filter == "no" and _is_nonempty(r.get("Profile Name", "")):
            continue
        if evidence_filter == "yes" and not _is_nonempty(r.get("Evidence & Source URLs", "")):
            continue
        if evidence_filter == "no" and _is_nonempty(r.get("Evidence & Source URLs", "")):
            continue

        health = _get_health_status(r)
        if health_filter == "alive" and health != "alive":
            continue
        if health_filter == "dead" and health not in ("dead", "timeout", "dns_fail", "error"):
            continue
        if health_filter == "unchecked" and health:
            continue

        # Return full row with all columns
        result.append(dict(r))

    return result


def get_filter_options(rows: List[Dict]) -> dict:
    """Get unique filter values for dropdowns."""
    categories = set()
    sources = set()
    for r in rows:
        for c in _split_semicolons(r.get("Category", "")):
            categories.add(c.strip().title())
        for s in _split_semicolons(r.get("Source", "")):
            sources.add(s.strip())

    return {
        "categories": sorted(categories),
        "sources": sorted(sources),
    }
