#!/usr/bin/env python3
"""
Transform the existing CSV to match the correct column structure from the reference.
"""

import csv
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CSV_PATH = BASE_DIR / "Aptos Ecosystem Research" / "aptos_usdt_ecosystem_research.csv"
OUTPUT_PATH = BASE_DIR / "Aptos Ecosystem Research" / "aptos_usdt_ecosystem_research_transformed.csv"

# Correct column order from the reference CSV
CORRECT_COLUMNS = [
    "Name",
    "Suspect USDT support?",
    "Skip",
    "Added",
    "Web3 but no stablecoin",
    "General Stablecoin Adoption",
    "To be Added",
    "Processed?",
    "In Admin",
    "TG/TON appstore (no main URL)",
    "Final Status",
    "Notes",
    "Source",
    "Category",
    "Category Rank",
    "Original URL",
    "Best URL",
    "Status",
    "Matched URL",
    "Profile Name",
    "Slug",
    "Root ID",
    "Telegram Channels",
    "Secondary URL",
    "AI Research",
    "AI Notes & Sources",
    "Chain",
    "USDT Support",
    "USDT Type",
    "Starknet Support",
    "Starknet Type",
    "Solana Support",
    "Solana Type",
    "AI Evidence URLs"
]

# Mapping from old column names to new column names (for columns that might have different names)
COLUMN_MAPPING = {
    "Best social": "Telegram Channels"  # Map Best social to Telegram Channels
}


def transform_csv():
    """Transform CSV to match the correct column structure."""
    # Read existing CSV
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        old_fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"Read {len(rows)} rows from existing CSV")
    print(f"Old columns ({len(old_fieldnames)}): {old_fieldnames}")
    print(f"New columns ({len(CORRECT_COLUMNS)}): {CORRECT_COLUMNS}")

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
    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CORRECT_COLUMNS)
        writer.writeheader()
        writer.writerows(transformed_rows)

    print(f"\nTransformed CSV written to: {OUTPUT_PATH}")
    print(f"Total rows: {len(transformed_rows)}")

    # Show column differences
    old_set = set(old_fieldnames)
    new_set = set(CORRECT_COLUMNS)

    print(f"\nColumns added: {new_set - old_set}")
    print(f"Columns removed: {old_set - new_set}")


if __name__ == "__main__":
    transform_csv()
