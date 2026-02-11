#!/usr/bin/env python3
"""
Compare scraped ecosystem data with existing CSV and identify:
1. Duplicates that might need data enhancement
2. New projects to add to the CSV

Usage: python compare_and_merge.py
"""

import csv
import json
import re
from pathlib import Path
from difflib import SequenceMatcher

# Paths
BASE_DIR = Path(__file__).parent.parent
CSV_PATH = BASE_DIR / "Aptos Ecosystem Research" / "aptos_usdt_ecosystem_research.csv"
OUTPUT_DIR = BASE_DIR / "Aptos Ecosystem Research"

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

# DefiLlama Aptos protocols (from API)
DEFILLAMA_DATA = [
    {"name": "Binance CEX", "slug": "binance-cex", "url": "https://www.binance.com", "twitter": "@binance", "category": "CEX", "tvl": 175787171836},
    {"name": "OKX", "slug": "okx", "url": "https://www.okx.com", "twitter": "@okx", "category": "CEX", "tvl": 23427519504},
    {"name": "Bitfinex", "slug": "bitfinex", "url": "https://www.bitfinex.com", "twitter": "@bitfinex", "category": "CEX", "tvl": 20839862915},
    {"name": "Bybit", "slug": "bybit", "url": "https://www.bybit.com", "twitter": "@bybit_official", "category": "CEX", "tvl": 17668168251},
    {"name": "Gate", "slug": "gate-exchange", "url": "https://www.gate.io", "twitter": "@gate_io", "category": "CEX", "tvl": 6200000000},
    {"name": "MEXC", "slug": "mexc", "url": "https://www.mexc.com", "twitter": "@MEXC_Global", "category": "CEX", "tvl": 2800000000},
    {"name": "KuCoin", "slug": "kucoin", "url": "https://www.kucoin.com", "twitter": "@kaboringucoin", "category": "CEX", "tvl": 2400000000},
    {"name": "BlackRock BUIDL", "slug": "blackrock-buidl", "url": "https://www.blackrock.com", "twitter": "@BlackRock", "category": "RWA", "tvl": 2200000000},
    {"name": "Portal", "slug": "portal-swap", "url": "https://portal.exchange", "twitter": "@portal_hq", "category": "Bridge", "tvl": 1500000000},
    {"name": "PancakeSwap AMM", "slug": "pancakeswap-amm", "url": "https://pancakeswap.finance", "twitter": "@PancakeSwap", "category": "Dexes", "tvl": 1400000000},
    {"name": "HashKey Exchange", "slug": "hashkey", "url": "https://hashkey.com", "twitter": "@HashKeyExchange", "category": "CEX", "tvl": 1100000000},
    {"name": "Ondo Yield Assets", "slug": "ondo", "url": "https://ondo.finance", "twitter": "@OndoFinance", "category": "RWA", "tvl": 900000000},
    {"name": "Echo Lending", "slug": "echo-lending", "url": "https://echo.xyz", "twitter": "@Echo_Protocol", "category": "Lending", "tvl": 193000000},
    {"name": "Echelon Market", "slug": "echelon-market", "url": "https://echelon.market", "twitter": "@EchelonMarket", "category": "Lending", "tvl": 96000000},
    {"name": "Aave Aptos", "slug": "aave-aptos", "url": "https://aptos.aave.com", "twitter": "@aave", "category": "Lending", "tvl": 57000000},
    {"name": "Hyperion", "slug": "hyperion", "url": "https://hyperion.xyz", "twitter": "@hyperaboringion_xyz", "category": "Dexes", "tvl": 56000000},
    {"name": "Amnis Finance", "slug": "amnis-finance", "url": "https://amnis.finance", "twitter": "@AmnisFinance", "category": "Liquid Staking", "tvl": 45000000},
    {"name": "Thala LSD", "slug": "thala-lsd", "url": "https://thalalabs.xyz", "twitter": "@ThalaLabs", "category": "Liquid Staking", "tvl": 42000000},
    {"name": "Aries Markets", "slug": "aries-markets", "url": "https://ariesmarkets.xyz", "twitter": "@AriesMarkets", "category": "Lending", "tvl": 40000000},
    {"name": "Aptin Finance V2", "slug": "aptin-finance-v2", "url": "https://aptin.io", "twitter": "@AptinLabs", "category": "Lending", "tvl": 35000000},
    {"name": "ThalaSwap", "slug": "thalaswap", "url": "https://thalalabs.xyz", "twitter": "@ThalaLabs", "category": "Dexes", "tvl": 32000000},
    {"name": "Merkle Trade", "slug": "merkle-trade", "url": "https://merkle.trade", "twitter": "@MerkleTrade", "category": "Derivatives", "tvl": 28000000},
    {"name": "Cellana Finance", "slug": "cellana-finance", "url": "https://cellana.finance", "twitter": "@CellanaFinance", "category": "Dexes", "tvl": 25000000},
    {"name": "Liquidswap", "slug": "liquidswap", "url": "https://liquidswap.com", "twitter": "@PontemNetwork", "category": "Dexes", "tvl": 22000000},
    {"name": "Meso Finance", "slug": "meso-finance", "url": "https://mesofinance.xyz", "twitter": "@MesoFinance", "category": "Lending", "tvl": 18000000},
    {"name": "Joule Finance", "slug": "joule-finance", "url": "https://joule.finance", "twitter": "@JouleFinance", "category": "Lending", "tvl": 15000000},
    {"name": "Econia", "slug": "econia", "url": "https://econia.dev", "twitter": "@EconiaLabs", "category": "Dexes", "tvl": 12000000},
    {"name": "Emojicoin.fun", "slug": "emojicoin", "url": "https://emojicoin.fun", "twitter": "@emojicoin_fun", "category": "Launchpad", "tvl": 8000000},
    {"name": "Tortuga Finance", "slug": "tortuga-finance", "url": "https://tortuga.finance", "twitter": "@TortugaFinance", "category": "Liquid Staking", "tvl": 7000000},
    {"name": "Kana Labs", "slug": "kana-labs", "url": "https://kanalabs.io", "twitter": "@KanaLabs", "category": "Dexes", "tvl": 5000000},
    {"name": "Panora", "slug": "panora", "url": "https://panora.exchange", "twitter": "@PanoraExchange", "category": "Dexes", "tvl": 4000000},
    {"name": "VibrantX", "slug": "vibrantx", "url": "https://vibrantx.finance", "twitter": "@VibrantXFi", "category": "Yield", "tvl": 3500000},
    {"name": "Mirage Protocol", "slug": "mirage-protocol", "url": "https://mirage.money", "twitter": "@MirageProtocol", "category": "Derivatives", "tvl": 3000000},
    {"name": "Sushi Aptos", "slug": "sushi-aptos", "url": "https://sushi.com", "twitter": "@SushiSwap", "category": "Dexes", "tvl": 2500000},
    {"name": "Abel Finance", "slug": "abel-finance", "url": "https://abel.finance", "twitter": "@AbelFinance", "category": "Lending", "tvl": 2000000},
    {"name": "Propbase", "slug": "propbase", "url": "https://propbase.app", "twitter": "@PropbaseApp", "category": "RWA", "tvl": 1800000},
    {"name": "MoneyFi", "slug": "moneyfi", "url": "https://moneyfi.xyz", "twitter": "@MoneyFi_xyz", "category": "Lending", "tvl": 1500000},
    {"name": "Kofi Finance", "slug": "kofi-finance", "url": "https://kofi.finance", "twitter": "@KofiFinance", "category": "Yield", "tvl": 1200000},
    {"name": "MOAR Market", "slug": "moar-market", "url": "https://moar.market", "twitter": "@MOARMarket", "category": "Lending", "tvl": 1000000},
    {"name": "Superposition", "slug": "superposition", "url": "https://superposition.xyz", "twitter": "@superposition_x", "category": "Dexes", "tvl": 800000},
    {"name": "Auro Finance", "slug": "auro-finance", "url": "https://auro.finance", "twitter": "@AuroFinance", "category": "Yield", "tvl": 600000},
    {"name": "StreamFlow", "slug": "streamflow", "url": "https://streamflow.finance", "twitter": "@streamaboringflow_fi", "category": "Payments", "tvl": 500000},
    {"name": "Earnium", "slug": "earnium", "url": "https://earnium.io", "twitter": "@EarniumIO", "category": "Yield", "tvl": 400000},
    {"name": "GoAPT", "slug": "goapt", "url": "https://goapt.xyz", "twitter": "@GoAPT_xyz", "category": "Yield", "tvl": 300000},
    {"name": "Bridgers", "slug": "bridgers", "url": "https://bridgers.xyz", "twitter": "@BridgersXYZ", "category": "Bridge", "tvl": 200000},
    {"name": "TrustAKE", "slug": "trustake", "url": "https://trustake.com", "twitter": "@TrustAKE", "category": "Liquid Staking", "tvl": 150000},
]


def normalize_name(name):
    """Normalize a project name for comparison."""
    name = name.lower()
    # Remove common suffixes
    name = re.sub(r'\s*(protocol|finance|labs|wallet|exchange|market|markets|v\d+|amm|lsd|cdp|aptos|cex)$', '', name, flags=re.I)
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

        # Exact match after normalization
        if normalized == existing_norm:
            return existing, 1.0

        # High similarity
        sim = similarity(normalized, existing_norm)
        if sim > 0.8:
            return existing, sim

        # Check if one contains the other
        if normalized in existing_norm or existing_norm in normalized:
            return existing, 0.9

    return None, 0.0


def load_existing_csv():
    """Load existing CSV and return list of dicts."""
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def compare_data():
    """Compare DefiLlama data with existing CSV."""
    existing = load_existing_csv()
    existing_names = [row['Name'] for row in existing]

    duplicates = []  # Found in both, might need enhancement
    new_projects = []  # Only in DefiLlama, not in CSV

    for project in DEFILLAMA_DATA:
        match, score = find_match(project['name'], existing_names)

        if match:
            duplicates.append({
                'defillama_name': project['name'],
                'existing_name': match,
                'match_score': score,
                'defillama_url': project['url'],
                'defillama_twitter': project['twitter'],
                'defillama_category': project['category'],
                'defillama_tvl': project['tvl'],
            })
        else:
            new_projects.append(project)

    return duplicates, new_projects, existing


def generate_report(duplicates, new_projects, existing):
    """Generate a comparison report."""
    report = []
    report.append("=" * 60)
    report.append("ECOSYSTEM DATA COMPARISON REPORT")
    report.append("=" * 60)
    report.append("")
    report.append(f"Existing CSV entries: {len(existing)}")
    report.append(f"DefiLlama Aptos protocols: {len(DEFILLAMA_DATA)}")
    report.append(f"Duplicates found: {len(duplicates)}")
    report.append(f"New projects to add: {len(new_projects)}")
    report.append("")

    report.append("-" * 60)
    report.append("DUPLICATES (may need data enhancement)")
    report.append("-" * 60)
    for d in duplicates[:20]:  # Show first 20
        report.append(f"  DefiLlama: {d['defillama_name']}")
        report.append(f"  CSV:      {d['existing_name']} (match: {d['match_score']:.0%})")
        report.append(f"  URL: {d['defillama_url']}")
        report.append(f"  Twitter: {d['defillama_twitter']}")
        report.append(f"  TVL: ${d['defillama_tvl']:,}")
        report.append("")

    report.append("-" * 60)
    report.append("NEW PROJECTS TO ADD")
    report.append("-" * 60)
    for p in new_projects:
        report.append(f"  Name: {p['name']}")
        report.append(f"  URL: {p['url']}")
        report.append(f"  Twitter: {p['twitter']}")
        report.append(f"  Category: {p['category']}")
        report.append(f"  TVL: ${p['tvl']:,}")
        report.append("")

    return "\n".join(report)


def sanitize_csv_field(value):
    """Sanitize a field value for CSV - remove or replace commas to prevent column splitting."""
    if isinstance(value, str):
        # Replace commas with semicolons to avoid CSV parsing issues in Google Sheets
        return value.replace(',', ';')
    return value


def generate_new_csv_rows(new_projects):
    """Generate CSV rows for new projects using the correct column structure."""
    rows = []
    for p in new_projects:
        is_defi = p['category'] in ['CEX', 'Dexes', 'Lending', 'Derivatives', 'Bridge', 'RWA']
        # Format TVL without commas (use underscores or no separator)
        tvl_formatted = f"${p['tvl']}" if p['tvl'] < 1000 else f"${p['tvl']/1000000:.1f}M" if p['tvl'] < 1000000000 else f"${p['tvl']/1000000000:.1f}B"

        row = {col: '' for col in CORRECT_COLUMNS}  # Initialize all columns as empty
        row.update({
            'Name': sanitize_csv_field(p['name']),
            'Suspect USDT support?': 'TRUE' if is_defi else '',
            'Web3 but no stablecoin': '' if is_defi else 'TRUE',
            'Notes': sanitize_csv_field(f"{p['category']} - TVL: {tvl_formatted}"),
            'Source': 'DefiLlama',
            'Category': sanitize_csv_field(p['category']),
            'Best URL': p['url'],
            'Slug': p['slug'],
            'Telegram Channels': p['twitter'],  # Twitter goes to Telegram Channels for now
            'AI Research': 'TRUE',
            'AI Notes & Sources': sanitize_csv_field(f"{p['category']} from DefiLlama"),
            'Chain': 'Aptos',
        })
        rows.append(row)
    return rows


if __name__ == "__main__":
    print("Loading existing CSV...")
    existing = load_existing_csv()

    print("Comparing data...")
    duplicates, new_projects, existing = compare_data()

    print("\n" + generate_report(duplicates, new_projects, existing))

    # Save report
    report_path = OUTPUT_DIR / "comparison_report.txt"
    with open(report_path, 'w') as f:
        f.write(generate_report(duplicates, new_projects, existing))
    print(f"\nReport saved to: {report_path}")

    # Generate new rows CSV
    if new_projects:
        new_rows = generate_new_csv_rows(new_projects)
        new_csv_path = OUTPUT_DIR / "new_projects_to_add.csv"
        with open(new_csv_path, 'w', newline='', encoding='utf-8') as f:
            if new_rows:
                writer = csv.DictWriter(f, fieldnames=CORRECT_COLUMNS)
                writer.writeheader()
                writer.writerows(new_rows)
        print(f"New projects CSV saved to: {new_csv_path}")
