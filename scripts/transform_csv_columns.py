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


# Mapping from old column names to new column names
COLUMN_MAPPING = {
    "Best social": "Telegram Channels"  # Map Best social to Telegram Channels
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

    # Transform each row
    transformed_rows = []
    for row in rows:
        new_row = {}
        for col in CORRECT_COLUMNS:
            # Check if we have a direct match
            if col in row:
                new_row[col] = row[col]
            # Check if there's a mapped column
            elif col in COLUMN_MAPPING.values():
                # Find the old column that maps to this new column
                for old_col, new_col in COLUMN_MAPPING.items():
                    if new_col == col and old_col in row:
                        new_row[col] = row[old_col]
                        break
                else:
                    new_row[col] = ''
            else:
                new_row[col] = ''
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
