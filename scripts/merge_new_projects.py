#!/usr/bin/env python3
"""
Merge new projects from comparison into the main CSV.
"""

import csv
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CSV_PATH = BASE_DIR / "Aptos Ecosystem Research" / "aptos_usdt_ecosystem_research.csv"
NEW_PROJECTS_PATH = BASE_DIR / "Aptos Ecosystem Research" / "new_projects_to_add.csv"

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


def merge_csvs():
    """Append new projects to the main CSV."""
    # Read existing CSV
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        existing_rows = list(reader)
        fieldnames = reader.fieldnames

    existing_names = {row['Name'].lower() for row in existing_rows}
    print(f"Existing entries: {len(existing_rows)}")

    # Check if new projects file exists
    if not NEW_PROJECTS_PATH.exists():
        print(f"No new projects file found at: {NEW_PROJECTS_PATH}")
        return

    # Read new projects
    with open(NEW_PROJECTS_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        new_rows = list(reader)

    print(f"New projects to consider: {len(new_rows)}")

    # Filter out any duplicates
    added = []
    for row in new_rows:
        if row['Name'].lower() not in existing_names:
            added.append(row)
            existing_names.add(row['Name'].lower())

    print(f"New projects to add (after duplicate check): {len(added)}")

    # Append to CSV using the correct column order
    if added:
        with open(CSV_PATH, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CORRECT_COLUMNS)
            for row in added:
                clean_row = {k: row.get(k, '') for k in CORRECT_COLUMNS}
                writer.writerow(clean_row)

        print(f"\nAdded {len(added)} new projects to CSV:")
        for row in added:
            print(f"  - {row['Name']}")

    # Final count
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        final_count = len(list(reader))

    print(f"\nFinal CSV entries: {final_count}")


if __name__ == "__main__":
    merge_csvs()
