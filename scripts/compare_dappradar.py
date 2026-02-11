#!/usr/bin/env python3
"""
Compare DappRadar data with existing CSV.
"""

import csv
import re
from pathlib import Path
from difflib import SequenceMatcher

BASE_DIR = Path(__file__).parent.parent
CSV_PATH = BASE_DIR / "Aptos Ecosystem Research" / "aptos_usdt_ecosystem_research.csv"

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

# DappRadar Aptos dapps (from rankings page)
DAPPRADAR_DATA = [
    {"name": "DApp World", "slug": "dapp-world", "category": "Games"},
    {"name": "PancakeSwap V2", "slug": "pancakeswap-v2", "category": "DeFi"},
    {"name": "Jump.trade", "slug": "jump-trade", "category": "Marketplaces"},
    {"name": "Chingari", "slug": "chingari", "category": "Social"},
    {"name": "Galxe", "slug": "galxe", "category": "Social"},
    {"name": "Ondo Finance", "slug": "ondo-finance", "category": "DeFi"},
    {"name": "motoDEX", "slug": "motodex", "category": "Games"},
    {"name": "PancakeSwap V3", "slug": "pancakeswap-v3", "category": "DeFi"},
    {"name": "SushiSwap V3", "slug": "sushiswap-v3", "category": "DeFi"},
    {"name": "KGeN", "slug": "kgen", "category": "Games"},
    {"name": "Interport Finance", "slug": "interport-finance", "category": "DeFi"},
    {"name": "GOQii", "slug": "goqii", "category": "Other"},
    {"name": "IN - match3", "slug": "in-match3", "category": "Games"},
    {"name": "Aries Markets", "slug": "aries-markets", "category": "DeFi"},
    {"name": "Thala", "slug": "thala", "category": "DeFi"},
    {"name": "Aptos Arena", "slug": "aptos-arena", "category": "Games"},
    {"name": "Baptswap", "slug": "baptswap", "category": "DeFi"},
    {"name": "Wapal", "slug": "wapal", "category": "Marketplaces"},
    {"name": "Amnis Finance", "slug": "amnis-finance", "category": "DeFi"},
    {"name": "Panora", "slug": "panora", "category": "DeFi"},
    {"name": "Econia", "slug": "econia", "category": "DeFi"},
    {"name": "Liquid Swap", "slug": "liquidswap", "category": "DeFi"},
    {"name": "Tortuga", "slug": "tortuga", "category": "DeFi"},
    {"name": "VibrantX", "slug": "vibrantx", "category": "DeFi"},
    {"name": "Aptin Finance", "slug": "aptin-finance", "category": "DeFi"},
    {"name": "MegaPools", "slug": "megapools", "category": "Games"},
    {"name": "TapFlux", "slug": "tapflux", "category": "Games"},
    {"name": "Ape.ing", "slug": "apeing", "category": "Games"},
    {"name": "Call of Myth", "slug": "call-of-myth", "category": "Games"},
    {"name": "Prompt Harvest", "slug": "prompt-harvest", "category": "Games"},
    {"name": "MineX", "slug": "minex", "category": "Games"},
    {"name": "CX Chain", "slug": "cx-chain", "category": "Other"},
    {"name": "Jocc", "slug": "jocc", "category": "Games"},
    {"name": "HyperSui", "slug": "hypersui", "category": "Other"},
    {"name": "GemHunt", "slug": "gemhunt", "category": "Games"},
    {"name": "SVERSE", "slug": "sverse", "category": "Games"},
    {"name": "CoinVs", "slug": "coinvs", "category": "Games"},
    {"name": "WoA | War of Art", "slug": "war-of-art", "category": "Games"},
    {"name": "Scream AI", "slug": "scream-ai", "category": "Other"},
    {"name": "Rivyu", "slug": "rivyu", "category": "Other"},
    {"name": "Buinkers", "slug": "buinkers", "category": "Games"},
    {"name": "ChainEsport", "slug": "chainesport", "category": "Games"},
    {"name": "BattleDoge", "slug": "battledoge", "category": "Games"},
    {"name": "SPL", "slug": "spl", "category": "Games"},
    {"name": "GTA Crypto", "slug": "gta-crypto", "category": "Games"},
    {"name": "OneXfer", "slug": "onexfer", "category": "Other"},
    {"name": "Illuvium: Overworld", "slug": "illuvium-overworld", "category": "Games"},
    {"name": "Stormhail Heroes", "slug": "stormhail-heroes", "category": "Games"},
    {"name": "DataHive AI", "slug": "datahive-ai", "category": "Other"},
    {"name": "SolSo", "slug": "solso", "category": "Games"},
]


def normalize_name(name):
    """Normalize a project name for comparison."""
    name = name.lower()
    name = re.sub(r'\s*(protocol|finance|labs|wallet|exchange|market|markets|v\d+|swap)$', '', name, flags=re.I)
    name = re.sub(r'[^a-z0-9]', '', name)
    return name


def similarity(a, b):
    """Calculate string similarity ratio."""
    return SequenceMatcher(None, a, b).ratio()


def find_match(name, existing_names):
    """Find the best match for a name in existing names."""
    normalized = normalize_name(name)

    for existing in existing_names:
        existing_norm = normalize_name(existing)

        if normalized == existing_norm:
            return existing, 1.0

        sim = similarity(normalized, existing_norm)
        if sim > 0.8:
            return existing, sim

        if normalized in existing_norm or existing_norm in normalized:
            return existing, 0.9

    return None, 0.0


def sanitize_csv_field(value):
    """Sanitize a field value for CSV - remove or replace commas to prevent column splitting."""
    if isinstance(value, str):
        # Replace commas with semicolons to avoid CSV parsing issues in Google Sheets
        return value.replace(',', ';')
    return value


def load_existing_csv():
    """Load existing CSV and return list of names."""
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return [row['Name'] for row in reader]


def compare_data():
    """Compare DappRadar data with existing CSV."""
    existing_names = load_existing_csv()

    duplicates = []
    new_projects = []

    for project in DAPPRADAR_DATA:
        match, score = find_match(project['name'], existing_names)

        if match:
            duplicates.append({
                'dappradar_name': project['name'],
                'existing_name': match,
                'match_score': score
            })
        else:
            new_projects.append(project)

    return duplicates, new_projects, existing_names


if __name__ == "__main__":
    existing_names = load_existing_csv()
    print(f"Existing CSV entries: {len(existing_names)}")
    print(f"DappRadar dapps: {len(DAPPRADAR_DATA)}")

    duplicates, new_projects, _ = compare_data()

    print(f"\nDuplicates found: {len(duplicates)}")
    print(f"New projects: {len(new_projects)}")

    print("\n" + "=" * 50)
    print("NEW PROJECTS FROM DAPPRADAR")
    print("=" * 50)
    for p in new_projects:
        print(f"  - {p['name']} ({p['category']})")
        print(f"    URL: https://dappradar.com/dapp/{p['slug']}")

    # Generate CSV rows for new projects
    if new_projects:
        output_path = BASE_DIR / "Aptos Ecosystem Research" / "dappradar_new_projects.csv"
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CORRECT_COLUMNS)
            writer.writeheader()

            for p in new_projects:
                is_defi = p['category'] in ['DeFi', 'Exchanges']
                row = {col: '' for col in CORRECT_COLUMNS}  # Initialize all columns as empty
                row.update({
                    'Name': sanitize_csv_field(p['name']),
                    'Suspect USDT support?': 'TRUE' if is_defi else '',
                    'Web3 but no stablecoin': '' if is_defi else 'TRUE',
                    'Notes': sanitize_csv_field(f"{p['category']} dapp on Aptos"),
                    'Source': 'DappRadar',
                    'Category': sanitize_csv_field(p['category']),
                    'Best URL': f"https://dappradar.com/dapp/{p['slug']}",
                    'Slug': p['slug'],
                    'AI Research': 'TRUE',
                    'AI Notes & Sources': sanitize_csv_field(f"{p['category']} from DappRadar"),
                    'Chain': 'Aptos',
                })
                writer.writerow(row)

        print(f"\nNew projects saved to: {output_path}")
