#!/usr/bin/env python3
"""
Enrich ecosystem CSV with asset support data from The Grid API.

For rows already matched to Grid profiles (have Root ID / Matched URL),
queries the Grid API for product→asset relationships and writes findings
back to the CSV's stablecoin and evidence columns.

Usage:
    python scripts/enrich_grid_assets.py --chain near --dry-run
    python scripts/enrich_grid_assets.py --chain near --limit 20
    python scripts/enrich_grid_assets.py --chain near
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.columns import CORRECT_COLUMNS
from lib.csv_utils import load_csv, write_csv, find_main_csv
from lib.grid_client import GridAPIClient
from lib.grid_client.support import (
    TARGET_ASSET_GRID_MAP,
    extract_supported_tickers,
    check_target_support,
)


# ── Configuration ──────────────────────────────────────────────────────────

REQUEST_DELAY = 0.2  # seconds between Grid API calls (Grid has no rate limit)

# Stablecoin asset keys
STABLECOIN_KEYS = {"USDT", "USDC"}


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


def enrich_from_grid(
    csv_path: Path,
    chain: str,
    target_assets: List[str],
    dry_run: bool = False,
    limit: int = 0,
) -> Tuple[int, int, int]:
    """
    Enrich Grid-matched rows with asset support data from the Grid API.

    Returns (total_rows, grid_matched_rows, enriched_rows).
    """
    client = GridAPIClient()

    print(f"\nLoading CSV: {csv_path}")
    rows = load_csv(csv_path)
    total = len(rows)
    print(f"  {total} rows total")

    # Filter to rows with Grid matches (have Matched URL)
    grid_rows = [(i, row) for i, row in enumerate(rows)
                 if row.get("Matched URL", "").strip()
                 and "false positive" not in row.get("Notes", "").lower()]

    matched_count = len(grid_rows)
    print(f"  {matched_count} Grid-matched rows (excluding false positives)")

    if limit > 0:
        grid_rows = grid_rows[:limit]
        print(f"  Processing first {limit}")

    enriched = 0

    for idx, (row_idx, row) in enumerate(grid_rows):
        name = row.get("Project Name", "").strip()
        matched_url = row.get("Matched URL", "").strip()

        print(f"  [{idx+1}/{len(grid_rows)}] {name}", end="", flush=True)

        # Rate limit
        if idx > 0:
            time.sleep(REQUEST_DELAY)

        # Query Grid for asset support using the matched URL
        roots = client.search_with_support_by_url(matched_url)
        if not roots:
            print(" -> no root data")
            continue

        root = roots[0]
        supported_tickers = extract_supported_tickers(root)
        target_support = check_target_support(supported_tickers, target_assets)

        supported_list = [a for a, v in target_support.items() if v]
        if not supported_list:
            print(" -> no target assets in Grid")
            continue

        enriched += 1

        # Build updates
        updates = {}

        # Stablecoin heuristic columns
        has_usdt = target_support.get("USDT", False)
        has_usdc = target_support.get("USDC", False)
        has_any_stablecoin = has_usdt or has_usdc

        if has_any_stablecoin:
            updates["Suspect USDT support?"] = "TRUE"
            updates["Web3 but no stablecoin"] = ""
            if has_usdt and has_usdc:
                updates["General Stablecoin Adoption"] = "TRUE"

        # Build evidence
        evidence_parts = [f"{a} (supported_by)" for a in supported_list]
        evidence_str = f"Grid: {'; '.join(evidence_parts)}"

        existing_evidence = row.get("Evidence & Source URLs", "").strip()
        if existing_evidence:
            if "Grid:" not in existing_evidence:
                updates["Evidence & Source URLs"] = f"{existing_evidence} | {evidence_str}"
        else:
            updates["Evidence & Source URLs"] = evidence_str

        # Build notes
        note_text = f"Grid confirms: {'; '.join(supported_list)}"
        existing_notes = row.get("Notes", "").strip()
        if existing_notes:
            if "Grid confirms" not in existing_notes:
                updates["Notes"] = f"{existing_notes} | {note_text}"
        else:
            updates["Notes"] = note_text

        print(f" -> {', '.join(supported_list)}")

        if not dry_run:
            rows[row_idx].update(updates)

    # Write output
    if not dry_run and enriched > 0:
        output_path = csv_path.with_name(csv_path.stem + "_grid_enriched.csv")
        write_csv(rows, output_path)
        print(f"\nGrid-enriched CSV: {output_path}")
    elif dry_run:
        print("\n[DRY RUN] No files written.")

    return total, matched_count, enriched


def main():
    parser = argparse.ArgumentParser(
        description="Enrich ecosystem CSV with Grid API asset support data"
    )
    parser.add_argument(
        "--chain", required=True, help="Chain ID (e.g., near, aptos)"
    )
    parser.add_argument(
        "--csv", help="Path to CSV (auto-detected from data/<chain>/ if omitted)"
    )
    parser.add_argument(
        "--assets", default=None,
        help="Comma-separated target assets (default: from chains.json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview enrichment without writing files",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Process only first N Grid-matched rows (for testing)",
    )
    args = parser.parse_args()

    # Resolve target assets
    chain_config = load_chain_config(args.chain)
    if args.assets:
        target_assets = [a.strip().upper() for a in args.assets.split(",")]
    else:
        target_assets = chain_config.get("target_assets", ["USDT", "USDC", "SOL", "STRK", "ADA"])

    # Always include USDC for stablecoin detection
    if "USDC" not in target_assets:
        target_assets.append("USDC")

    print(f"Target assets: {target_assets}")
    print(f"Chain: {args.chain}")

    # Resolve CSV path
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

    total, matched, enriched = enrich_from_grid(
        csv_path, args.chain, target_assets,
        dry_run=args.dry_run, limit=args.limit,
    )

    print(f"\n{'='*60}")
    print(f"GRID ASSET ENRICHMENT SUMMARY")
    print(f"{'='*60}")
    print(f"Total rows:         {total}")
    print(f"Grid-matched:       {matched}")
    print(f"Enriched with assets: {enriched}")
    print(f"Target assets:      {', '.join(target_assets)}")

    if args.dry_run:
        print("\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
