#!/usr/bin/env python3
"""
Match ecosystem CSV projects against The Grid API and detect asset support gaps.

For each project in the CSV:
1. Search The Grid by name, then by URL as fallback
2. Fill Profile Name, Root ID, Matched URL, Matched via, The Grid Status
3. Check product→asset relationships for target assets (USDt, SOL, STRK, ADA)
4. Compare Grid support vs DefiLlama evidence to find gaps
5. Output enriched CSV + gap report

Usage:
    python scripts/grid_match.py --chain avalanche --csv data.csv
    python scripts/grid_match.py --chain avalanche --csv data.csv --dry-run
    python scripts/grid_match.py --chain avalanche --csv data.csv --limit 20
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.columns import CORRECT_COLUMNS
from lib.csv_utils import load_csv, write_csv, find_main_csv
from lib.grid_client import GridAPIClient


# ── Configuration ──────────────────────────────────────────────────────────

REQUEST_DELAY = 0.3  # seconds between Grid API calls

# Map our target asset tickers to Grid asset tickers/names
# Grid uses "USDt" not "USDT", and full names like "Solana" not "SOL"
TARGET_ASSET_GRID_MAP = {
    "USDT": {"USDt", "USDT", "Tether USDt", "Tether"},
    "USDC": {"USDC", "USD Coin"},
    "SOL": {"SOL", "Solana"},
    "STRK": {"STRK", "Starknet"},
    "ADA": {"ADA", "Cardano"},
}


# ── Matching Logic ─────────────────────────────────────────────────────────

def normalize_for_search(name: str) -> str:
    """Clean a project name for Grid search."""
    # Remove common suffixes that hurt search
    clean = name.strip()
    for suffix in [" Protocol", " Finance", " Network", " Labs", " DAO",
                   " Exchange", " DEX", " Swap", " Bridge", " V2", " V3",
                   " AMM", " DeFi"]:
        if clean.endswith(suffix) and len(clean) > len(suffix) + 2:
            clean = clean[: -len(suffix)].strip()
    return clean


def score_name_match(grid_name: str, search_name: str) -> float:
    """Score how well a Grid profile name matches our project name."""
    g = grid_name.lower().strip()
    s = search_name.lower().strip()

    if g == s:
        return 1.0
    # One contains the other as a whole word
    if re.search(r"\b" + re.escape(s) + r"\b", g):
        return 0.9
    if re.search(r"\b" + re.escape(g) + r"\b", s):
        return 0.85
    # One starts with the other
    if g.startswith(s) or s.startswith(g):
        return 0.8
    # Substring
    if s in g or g in s:
        return 0.6
    return 0.0


def extract_supported_tickers(root_data: dict) -> Set[str]:
    """
    Extract all asset tickers that are 'Supported by' any product under this root.
    """
    tickers = set()
    for product in root_data.get("products", []):
        for rel in product.get("productAssetRelationships", []):
            support_type = rel.get("assetSupportType") or {}
            if support_type.get("slug") == "supported_by":
                asset = rel.get("asset", {})
                ticker = asset.get("ticker", "")
                name = asset.get("name", "")
                if ticker:
                    tickers.add(ticker)
                if name:
                    tickers.add(name)
    return tickers


def check_target_support(supported_tickers: Set[str], target_assets: List[str]) -> Dict[str, bool]:
    """
    Check which target assets are supported based on Grid tickers.
    Returns {asset: True/False}.
    """
    result = {}
    for asset in target_assets:
        grid_aliases = TARGET_ASSET_GRID_MAP.get(asset, {asset})
        found = bool(grid_aliases & supported_tickers)
        result[asset] = found
    return result


def match_project(
    client: GridAPIClient,
    name: str,
    website: str,
) -> Tuple[Optional[dict], str]:
    """
    Try to match a project to The Grid.

    Returns (root_data_or_None, match_method).
    match_method is "name", "url", or "".
    """
    # Strategy 1: Search by name (skip very short names — too ambiguous)
    search_term = normalize_for_search(name)
    if len(search_term) < 3:
        search_term = name.strip()  # Use original if normalization made it too short
    profiles = client.search_with_support_by_name(search_term, limit=5) if len(search_term) >= 3 else []

    best_match = None
    best_score = 0.0

    for pi in profiles:
        score = score_name_match(pi.get("name", ""), name)
        if score > best_score and score >= 0.8:
            root = pi.get("root")
            if root:
                best_match = {
                    "profile": pi,
                    "root": root,
                }
                best_score = score

    if best_match:
        return best_match, "name"

    # Strategy 2: Search by URL
    if website:
        time.sleep(REQUEST_DELAY)
        roots = client.search_with_support_by_url(website)
        if roots:
            root = roots[0]
            profiles = root.get("profileInfos", [])
            if profiles:
                return {
                    "profile": profiles[0],
                    "root": root,
                }, "url"

    return None, ""


# ── Main ───────────────────────────────────────────────────────────────────

def load_chain_config(chain_id: str) -> dict:
    """Load chain config from chains.json."""
    config_path = Path(__file__).parent.parent / "config" / "chains.json"
    if not config_path.exists():
        return {}
    with open(config_path, "r") as f:
        data = json.load(f)
    for chain in data.get("chains", []):
        if chain["id"] == chain_id:
            return chain
    return {}


def run_grid_match(
    csv_path: Path,
    chain: str,
    target_assets: List[str],
    dry_run: bool = False,
    limit: int = 0,
) -> Tuple[int, int, int, List[dict]]:
    """
    Match CSV rows to Grid and check asset support gaps.

    Returns (total, matched, gaps_found, gap_report_rows).
    """
    client = GridAPIClient()

    # Load CSV
    print(f"Loading CSV: {csv_path}")
    rows = load_csv(csv_path)
    total = len(rows)
    if limit > 0:
        rows = rows[:limit]
        print(f"  Processing first {limit} of {total} rows")
    else:
        print(f"  {total} rows to process")

    matched_count = 0
    gap_count = 0
    gap_report = []
    output_rows = []

    for i, row in enumerate(rows):
        name = row.get("Project Name", "").strip()
        website = row.get("Website", "").strip()

        if not name:
            output_rows.append(row)
            continue

        print(f"  [{i+1}/{len(rows)}] {name}", end="", flush=True)

        # Rate limit
        if i > 0:
            time.sleep(REQUEST_DELAY)

        # Match against Grid
        match_data, match_method = match_project(client, name, website)

        if not match_data:
            print(" → not in Grid")
            gap_report.append({
                "Project Name": name,
                "Status": "NOT IN GRID",
                "Match Method": "",
                "Grid Profile": "",
                "Grid URL": "",
                "Grid Supported": "",
                "Missing Assets": "",
                "DefiLlama Evidence": row.get("Evidence URLs", ""),
                "Notes": "Project not found in The Grid",
            })
            output_rows.append(row)
            continue

        matched_count += 1
        profile = match_data["profile"]
        root = match_data["root"]

        profile_name = profile.get("name", "")
        root_id = root.get("id", "")
        root_url = root.get("urlMain", "")
        root_slug = root.get("slug", "")
        profile_status = profile.get("profileStatus", {}).get("name", "") if profile.get("profileStatus") else ""

        # Get supported tickers
        supported_tickers = extract_supported_tickers(root)
        target_support = check_target_support(supported_tickers, target_assets)

        supported_list = [a for a, v in target_support.items() if v]
        missing_list = [a for a, v in target_support.items() if not v]

        # Check for gaps: we have DefiLlama evidence but Grid is missing support
        evidence = row.get("Evidence URLs", "").strip()
        real_gaps = []
        for asset in missing_list:
            # Check if DefiLlama found this asset
            if asset in evidence:
                real_gaps.append(asset)

        has_gap = len(real_gaps) > 0

        # Console output
        status_parts = [f"matched via {match_method}"]
        if supported_list:
            status_parts.append(f"Grid has: {','.join(supported_list)}")
        if real_gaps:
            status_parts.append(f"MISSING: {','.join(real_gaps)}")
            gap_count += 1
        print(f" → {profile_name} ({'; '.join(status_parts)})")

        # Update row
        updates = {
            "Profile Name": profile_name,
            "Root ID": root_id,
            "Matched URL": root_url,
            "Matched via": match_method,
            "The Grid Status": profile_status,
        }

        # Build gap note
        if real_gaps:
            gap_note = f"Grid missing: {', '.join(real_gaps)}"
            existing_notes = row.get("Notes", "").strip()
            if existing_notes:
                if gap_note not in existing_notes:
                    updates["Notes"] = f"{existing_notes} | {gap_note}"
            else:
                updates["Notes"] = gap_note

        if not dry_run:
            row.update(updates)

        output_rows.append(row)

        # Add to gap report
        if has_gap or not supported_list:
            gap_report.append({
                "Project Name": name,
                "Status": "GAPS FOUND" if real_gaps else "NO TARGET SUPPORT",
                "Match Method": match_method,
                "Grid Profile": profile_name,
                "Grid URL": root_url,
                "Grid Supported": ", ".join(supported_list) if supported_list else "none",
                "Missing Assets": ", ".join(real_gaps) if real_gaps else ", ".join(missing_list),
                "DefiLlama Evidence": evidence[:200] if evidence else "",
                "Notes": f"Grid missing {', '.join(real_gaps)} despite DefiLlama evidence" if real_gaps else "No target assets supported in Grid",
            })

    # Write outputs
    if not dry_run:
        # Enriched CSV
        output_path = csv_path.with_name(csv_path.stem + "_grid_matched.csv")
        write_csv(output_rows, output_path)
        print(f"\nGrid-matched CSV: {output_path}")

        # Gap report
        if gap_report:
            gap_path = csv_path.with_name(csv_path.stem + "_gap_report.csv")
            gap_columns = [
                "Project Name", "Status", "Match Method", "Grid Profile",
                "Grid URL", "Grid Supported", "Missing Assets",
                "DefiLlama Evidence", "Notes",
            ]
            write_csv(gap_report, gap_path, columns=gap_columns)
            print(f"Gap report:       {gap_path}")
    elif dry_run:
        print("\n[DRY RUN] No files written.")

    return total, matched_count, gap_count, gap_report


def main():
    parser = argparse.ArgumentParser(
        description="Match ecosystem CSV to Grid API and detect asset support gaps"
    )
    parser.add_argument(
        "--chain", required=True, help="Chain ID (e.g., avalanche, aptos)"
    )
    parser.add_argument(
        "--csv", help="Path to CSV (auto-detected from data/<chain>/ if omitted)"
    )
    parser.add_argument(
        "--assets", default=None,
        help="Comma-separated target assets (default: from chains.json)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Process only first N rows (for testing)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview without writing files",
    )
    args = parser.parse_args()

    # Resolve CSV
    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_path = find_main_csv(args.chain)
        if not csv_path:
            print(f"Error: No CSV found in data/{args.chain}/")
            sys.exit(1)

    if not csv_path.exists():
        print(f"Error: CSV not found: {csv_path}")
        sys.exit(1)

    # Parse target assets
    if args.assets:
        target_assets = [a.strip().upper() for a in args.assets.split(",") if a.strip()]
    else:
        chain_config = load_chain_config(args.chain)
        target_assets = chain_config.get("target_assets", ["USDT", "USDC"])
        # For Grid gap analysis, exclude USDC (not a research target, just stablecoin detection)
        target_assets = [a for a in target_assets if a != "USDC"]

    print(f"Target assets for gap analysis: {target_assets}")
    print(f"Chain: {args.chain}")
    print()

    total, matched, gaps, gap_report = run_grid_match(
        csv_path, args.chain, target_assets, args.dry_run, args.limit
    )

    # Summary
    print("\n" + "=" * 60)
    print("GRID MATCHING SUMMARY")
    print("=" * 60)
    print(f"Total rows:         {total}")
    print(f"Grid matches:       {matched} ({matched*100//max(total,1)}%)")
    print(f"Not in Grid:        {total - matched}")
    print(f"Gaps detected:      {gaps}")
    print(f"Target assets:      {', '.join(target_assets)}")

    if gap_report:
        print(f"\nTop gaps:")
        for g in gap_report[:10]:
            missing = g.get("Missing Assets", "")
            if missing:
                print(f"  {g['Project Name']:30s} | {g['Status']:20s} | Missing: {missing}")

    if args.dry_run:
        print("\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
