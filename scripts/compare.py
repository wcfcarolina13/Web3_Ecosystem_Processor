#!/usr/bin/env python3
"""
Compare scraped data from a source against existing CSV.
Chain-agnostic -- loads data from files, not hardcoded arrays.

Usage:
    python scripts/compare.py --chain aptos --source defillama --data data/aptos/defillama_scraped.json
    python scripts/compare.py --chain aptos --source dappradar --data data/aptos/dappradar_scraped.json
    python scripts/compare.py --chain aptos --source defillama --data data/aptos/defillama_scraped.json --csv data/aptos/aptos_usdt_ecosystem_research.csv
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.columns import CORRECT_COLUMNS, empty_row
from lib.matching import find_match
from lib.csv_utils import (
    load_csv,
    write_csv,
    sanitize_csv_field,
    resolve_data_path,
    find_main_csv,
)


def load_scraped_data(data_path: Path) -> list:
    """Load scraped data from a JSON file."""
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_data(scraped: list, existing_names: list, source: str):
    """
    Compare scraped data with existing names.

    Returns (duplicates, new_projects).
    """
    duplicates = []
    new_projects = []

    for project in scraped:
        name = project.get("name", "")
        if not name:
            continue

        match, score = find_match(name, existing_names)

        if match:
            duplicates.append(
                {
                    "scraped_name": name,
                    "existing_name": match,
                    "match_score": score,
                    "source": source,
                    "scraped_data": project,
                }
            )
        else:
            new_projects.append(project)

    return duplicates, new_projects


def generate_report(
    duplicates: list,
    new_projects: list,
    existing_count: int,
    scraped_count: int,
    source: str,
    chain: str,
) -> str:
    """Generate a comparison report."""
    report = []
    report.append("=" * 60)
    report.append(f"ECOSYSTEM DATA COMPARISON REPORT")
    report.append(f"Chain: {chain} | Source: {source}")
    report.append("=" * 60)
    report.append("")
    report.append(f"Existing CSV entries: {existing_count}")
    report.append(f"{source} scraped items: {scraped_count}")
    report.append(f"Duplicates found: {len(duplicates)}")
    report.append(f"New projects to add: {len(new_projects)}")
    report.append("")

    report.append("-" * 60)
    report.append("DUPLICATES (may need data enhancement)")
    report.append("-" * 60)
    for d in duplicates[:30]:
        report.append(f"  {source}: {d['scraped_name']}")
        report.append(f"  CSV:    {d['existing_name']} (match: {d['match_score']:.0%})")
        scraped = d.get("scraped_data", {})
        if scraped.get("url") or scraped.get("website"):
            report.append(f"  URL: {scraped.get('url') or scraped.get('website')}")
        if scraped.get("twitter"):
            report.append(f"  Twitter: {scraped['twitter']}")
        if scraped.get("tvl"):
            tvl = scraped["tvl"]
            if isinstance(tvl, (int, float)) and tvl > 0:
                report.append(f"  TVL: ${tvl:,.0f}")
        report.append("")

    report.append("-" * 60)
    report.append("NEW PROJECTS TO ADD")
    report.append("-" * 60)
    for p in new_projects:
        report.append(f"  Name: {p.get('name', '?')}")
        url = p.get("url") or p.get("website") or ""
        if url:
            report.append(f"  URL: {url}")
        if p.get("twitter"):
            report.append(f"  Twitter: {p['twitter']}")
        if p.get("category"):
            report.append(f"  Category: {p['category']}")
        if p.get("tvl"):
            tvl = p["tvl"]
            if isinstance(tvl, (int, float)) and tvl > 0:
                report.append(f"  TVL: ${tvl:,.0f}")
        report.append("")

    return "\n".join(report)


def generate_new_csv_rows(new_projects: list, chain: str, source: str) -> list:
    """Generate CSV row dicts for new projects."""
    rows = []
    defi_categories = {
        "CEX", "Dexes", "Lending", "Derivatives", "Bridge", "RWA",
        "DeFi", "Exchanges", "Yield", "Liquid Staking", "Payments",
        "Launchpad",
    }

    for p in new_projects:
        category = p.get("category", "")
        is_defi = category in defi_categories
        url = p.get("url") or p.get("website") or ""
        slug = p.get("slug", "")

        # If no main URL but we have a slug and source, construct a reference URL
        if not url and slug:
            source_urls = {
                "dappradar": f"https://dappradar.com/dapp/{slug}",
                "defillama": f"https://defillama.com/protocol/{slug}",
            }
            url = source_urls.get(source.lower(), "")

        twitter = p.get("twitter", "")
        # Build X Link from handle (strip @ prefix if present)
        x_handle_clean = twitter.lstrip("@") if twitter else ""
        x_link = f"https://x.com/{x_handle_clean}" if x_handle_clean else ""

        row = empty_row(chain)
        row.update(
            {
                "Project Name": sanitize_csv_field(p.get("name", "")),
                "Suspect USDT support?": "TRUE" if is_defi else "",
                "Web3 but no stablecoin": "" if is_defi else "TRUE",
                "Notes": sanitize_csv_field(
                    f"{category} from {source}" + (
                        f" - TVL: ${p['tvl']:,.0f}" if p.get("tvl") and isinstance(p["tvl"], (int, float)) and p["tvl"] > 0 else ""
                    )
                ),
                "Source": source,
                "Category": sanitize_csv_field(category),
                "Website": url,
                "X Link": x_link,
                "X Handle": twitter,
                "Chain": chain,
            }
        )
        rows.append(row)

    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Compare scraped ecosystem data against existing CSV"
    )
    parser.add_argument(
        "--chain", required=True, help="Chain name (e.g., aptos, tron)"
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Data source name (e.g., defillama, dappradar)",
    )
    parser.add_argument(
        "--data", required=True, help="Path to scraped data JSON file"
    )
    parser.add_argument(
        "--csv", help="Path to existing CSV (auto-detected from data/<chain>/ if omitted)"
    )
    args = parser.parse_args()

    # Resolve CSV path
    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_path = find_main_csv(args.chain)
        if not csv_path:
            print(f"Error: No CSV found in data/{args.chain}/")
            print("Use --csv to specify the path, or run init_chain.sh first.")
            sys.exit(1)

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}")
        sys.exit(1)

    # Load data
    print(f"Loading existing CSV: {csv_path}")
    existing = load_csv(csv_path)
    existing_names = [row["Project Name"] for row in existing]

    print(f"Loading scraped data: {data_path}")
    scraped = load_scraped_data(data_path)

    # Compare
    print("Comparing data...")
    duplicates, new_projects = compare_data(scraped, existing_names, args.source)

    # Generate report
    report = generate_report(
        duplicates, new_projects, len(existing), len(scraped), args.source, args.chain
    )
    print("\n" + report)

    # Save report
    output_dir = resolve_data_path(args.chain)
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / f"comparison_report_{args.source}.txt"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report saved to: {report_path}")

    # Generate new projects CSV
    if new_projects:
        new_rows = generate_new_csv_rows(new_projects, args.chain, args.source)
        new_csv_path = output_dir / f"new_projects_{args.source}.csv"
        write_csv(new_rows, new_csv_path)
        print(f"New projects CSV saved to: {new_csv_path}")
    else:
        print("No new projects to add.")


if __name__ == "__main__":
    main()
