#!/usr/bin/env python3
"""
Transform an existing CSV to match the correct column structure.

Usage:
    python scripts/transform_csv_columns.py --chain aptos
    python scripts/transform_csv_columns.py --csv data/aptos/aptos_usdt_ecosystem_research.csv
"""

import argparse
import csv
import sys
from pathlib import Path

# Add parent dir to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.columns import CORRECT_COLUMNS
from lib.csv_utils import find_main_csv, resolve_data_path


# Mapping from old column names to new standard column names
COLUMN_MAPPING = {
    "Name": "Project Name",
    "Best URL": "Website",
    "Best social": "X Handle",
    "Telegram Channels": "X Handle",  # Legacy: twitter was stored here
    "Status": "The Grid Status",
    "AI Evidence URLs": "Evidence URLs",
    "Original URL": None,      # Dropped
    "Slug": None,              # Dropped
    "Secondary URL": None,     # Dropped
    "AI Research": None,       # Dropped
    "AI Notes & Sources": None,  # Dropped
    "Category Rank": None,     # Dropped
    "USDT Support": None,      # Dropped
    "USDT Type": None,         # Dropped
    "Starknet Support": None,  # Dropped
    "Starknet Type": None,     # Dropped
    "Solana Support": None,    # Dropped
    "Solana Type": None,       # Dropped
    "Profile Name 2": None,    # Dropped
    "Root ID 2": None,         # Dropped
    "Matched URL 2": None,     # Dropped
    "Matched via 2": None,     # Dropped
}


def transform_csv(csv_path: Path, output_path: Path = None):
    """Transform CSV to match the correct column structure."""
    if not csv_path.exists():
        print(f"Error: CSV not found: {csv_path}")
        return False

    if output_path is None:
        output_path = csv_path.with_name(csv_path.stem + "_transformed.csv")

    # Read existing CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        old_fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"Read {len(rows)} rows from existing CSV")
    print(f"Old columns ({len(old_fieldnames)}): {old_fieldnames}")
    print(f"New columns ({len(CORRECT_COLUMNS)}): {list(CORRECT_COLUMNS)}")

    # Build reverse mapping: new_col -> [old_col, ...]
    reverse_map = {}
    for old_col, new_col in COLUMN_MAPPING.items():
        if new_col is not None:
            reverse_map.setdefault(new_col, []).append(old_col)

    # Transform each row
    transformed_rows = []
    for row in rows:
        new_row = {}
        for col in CORRECT_COLUMNS:
            # Check if we have a direct match in the source row
            if col in row:
                new_row[col] = row[col]
            # Check if an old column maps to this new column
            elif col in reverse_map:
                value = ''
                for old_col in reverse_map[col]:
                    if old_col in row and row[old_col]:
                        value = row[old_col]
                        break
                new_row[col] = value
            else:
                new_row[col] = ''

        # Build X Link from X Handle if not already set
        if not new_row.get("X Link") and new_row.get("X Handle"):
            handle = new_row["X Handle"].lstrip("@").strip()
            if handle and not handle.startswith("http"):
                new_row["X Link"] = f"https://x.com/{handle}"

        transformed_rows.append(new_row)

    # Write transformed CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CORRECT_COLUMNS)
        writer.writeheader()
        writer.writerows(transformed_rows)

    print(f"\nTransformed CSV written to: {output_path}")
    print(f"Total rows: {len(transformed_rows)}")

    # Show column differences
    old_set = set(old_fieldnames)
    new_set = set(CORRECT_COLUMNS)

    added = new_set - old_set
    removed = old_set - new_set
    if added:
        print(f"\nColumns added: {added}")
    if removed:
        print(f"Columns removed: {removed}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Transform CSV to match the standard column structure"
    )
    parser.add_argument("--chain", help="Chain name (e.g., aptos) — auto-detects main CSV")
    parser.add_argument("--csv", help="Path to specific CSV file to transform")
    parser.add_argument("--output", help="Output path (default: <input>_transformed.csv)")

    args = parser.parse_args()

    if args.csv:
        csv_path = Path(args.csv)
    elif args.chain:
        csv_path = find_main_csv(args.chain)
        if csv_path is None:
            print(f"Error: No ecosystem research CSV found for chain '{args.chain}'")
            print(f"  Expected in: {resolve_data_path(args.chain)}")
            sys.exit(1)
    else:
        parser.print_help()
        print("\nError: Provide either --chain or --csv")
        sys.exit(1)

    output_path = Path(args.output) if args.output else None

    if not transform_csv(csv_path, output_path):
        sys.exit(1)


if __name__ == "__main__":
    main()
