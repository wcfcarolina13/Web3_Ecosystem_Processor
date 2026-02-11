#!/usr/bin/env python3
"""
Merge new projects into the main CSV for a chain.
Chain-agnostic -- resolves paths from --chain argument.

Usage:
    python scripts/merge.py --chain aptos --source defillama
    python scripts/merge.py --chain aptos --new-csv data/aptos/new_projects_defillama.csv
    python scripts/merge.py --chain aptos --new-csv data/aptos/new_projects_defillama.csv --csv data/aptos/aptos_usdt_ecosystem_research.csv
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.columns import CORRECT_COLUMNS
from lib.csv_utils import load_csv, append_csv, resolve_data_path, find_main_csv


def merge_csvs(main_csv: Path, new_csv: Path):
    """Append new projects to the main CSV, skipping duplicates."""
    # Read existing
    existing_rows = load_csv(main_csv)
    existing_names = {row["Project Name"].lower() for row in existing_rows}
    print(f"Existing entries: {len(existing_rows)}")

    # Read new projects
    new_rows = load_csv(new_csv)
    print(f"New projects to consider: {len(new_rows)}")

    # Filter out duplicates
    added = []
    for row in new_rows:
        name = row.get("Name", "").lower()
        if name and name not in existing_names:
            added.append(row)
            existing_names.add(name)

    print(f"New projects to add (after duplicate check): {len(added)}")

    # Append to CSV
    if added:
        append_csv(added, main_csv)
        print(f"\nAdded {len(added)} new projects to CSV:")
        for row in added:
            print(f"  - {row.get('Name', '?')}")

    # Final count
    final_rows = load_csv(main_csv)
    print(f"\nFinal CSV entries: {len(final_rows)}")


def main():
    parser = argparse.ArgumentParser(
        description="Merge new projects into the main ecosystem research CSV"
    )
    parser.add_argument(
        "--chain", required=True, help="Chain name (e.g., aptos, tron)"
    )
    parser.add_argument(
        "--source",
        help="Source name (e.g., defillama) -- used to find new_projects_<source>.csv",
    )
    parser.add_argument(
        "--new-csv",
        help="Explicit path to new projects CSV (overrides --source auto-detection)",
    )
    parser.add_argument(
        "--csv",
        help="Path to main CSV (auto-detected from data/<chain>/ if omitted)",
    )
    args = parser.parse_args()

    # Resolve main CSV path
    if args.csv:
        main_csv = Path(args.csv)
    else:
        main_csv = find_main_csv(args.chain)
        if not main_csv:
            print(f"Error: No main CSV found in data/{args.chain}/")
            print("Use --csv to specify the path.")
            sys.exit(1)

    if not main_csv.exists():
        print(f"Error: Main CSV not found: {main_csv}")
        sys.exit(1)

    # Resolve new projects CSV
    if args.new_csv:
        new_csv = Path(args.new_csv)
    elif args.source:
        new_csv = resolve_data_path(args.chain, f"new_projects_{args.source}.csv")
    else:
        print("Error: Provide either --source or --new-csv")
        sys.exit(1)

    if not new_csv.exists():
        print(f"Error: New projects CSV not found: {new_csv}")
        print("Run compare.py first to generate it.")
        sys.exit(1)

    print(f"Main CSV:         {main_csv}")
    print(f"New projects CSV: {new_csv}")
    print()

    merge_csvs(main_csv, new_csv)


if __name__ == "__main__":
    main()
