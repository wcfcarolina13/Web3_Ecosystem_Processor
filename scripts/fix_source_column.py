#!/usr/bin/env python3
"""
Fix the Source column in ecosystem CSVs.

Replaces 'Generic Scraper' with the actual source website hostname
derived from context (usually the page that was scraped).

For the NEAR chain, the generic-scraped items came from wallet.near.org.
For other chains, uses the Website column hostname as a fallback.

Also applicable as a general cleanup: ensures Source always refers to the
data source website, not the scraping method.

Usage:
    python scripts/fix_source_column.py --chain near --dry-run
    python scripts/fix_source_column.py --chain near
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.csv_utils import load_csv, write_csv, find_main_csv


# Known mapping: chain → what page "Generic Scraper" was used on.
# This lets us give the correct source for historical data.
GENERIC_SOURCE_BY_CHAIN = {
    "near": "wallet.near.org",
}


def hostname_from_url(url: str) -> str:
    """Extract hostname from a URL, stripping www. prefix."""
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        domain = re.sub(r"^www\.", "", domain)
        domain = domain.split(":")[0]
        return domain
    except Exception:
        return ""


def fix_sources(
    csv_path: Path,
    chain: str,
    dry_run: bool = False,
) -> tuple:
    """
    Fix 'Generic Scraper' in the Source column.

    Returns (total_rows, fixed_count, already_ok_count).
    """
    print(f"Loading CSV: {csv_path}")
    rows = load_csv(csv_path)
    total = len(rows)
    print(f"  {total} rows loaded")

    # Determine what to replace "Generic Scraper" with
    default_source = GENERIC_SOURCE_BY_CHAIN.get(chain, "")

    fixed = 0
    ok = 0

    for i, row in enumerate(rows):
        source = row.get("Source", "").strip()
        if "Generic Scraper" not in source:
            ok += 1
            continue

        # Determine the replacement source name
        # Priority: known chain mapping → Website column hostname → keep original
        replacement = default_source
        if not replacement:
            website = row.get("Website", "").strip()
            replacement = hostname_from_url(website)

        if not replacement:
            # Can't determine source — leave as-is but log it
            name = row.get("Project Name", "Unknown")
            print(f"  [SKIP] Row {i+1} ({name}): no replacement available")
            ok += 1
            continue

        # Replace "Generic Scraper" in the Source string
        # It may appear alone or combined: "Generic Scraper; NEARCatalog"
        new_source = source.replace("Generic Scraper", replacement)

        # Deduplicate source entries (in case replacement matches another source)
        parts = [p.strip() for p in new_source.split(";")]
        seen = set()
        deduped = []
        for p in parts:
            p_lower = p.lower()
            if p_lower not in seen and p:
                seen.add(p_lower)
                deduped.append(p)
        new_source = "; ".join(deduped)

        if new_source != source:
            fixed += 1
            if dry_run:
                name = row.get("Project Name", "Unknown")
                print(f"  [{i+1}] {name}: \"{source}\" → \"{new_source}\"")
            else:
                row["Source"] = new_source

    if not dry_run and fixed > 0:
        write_csv(rows, csv_path)
        print(f"\nFixed CSV written to: {csv_path}")
    elif dry_run:
        print(f"\n[DRY RUN] No files written.")

    return total, fixed, ok


def main():
    parser = argparse.ArgumentParser(
        description="Fix 'Generic Scraper' in the Source column of ecosystem CSVs"
    )
    parser.add_argument("--chain", required=True, help="Chain ID (e.g., near)")
    parser.add_argument("--csv", help="Path to CSV (auto-detected if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing")
    args = parser.parse_args()

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

    total, fixed, ok = fix_sources(csv_path, args.chain, dry_run=args.dry_run)

    print(f"\n{'='*60}")
    print(f"SOURCE FIX SUMMARY")
    print(f"{'='*60}")
    print(f"Total rows:  {total}")
    print(f"Fixed:       {fixed}")
    print(f"Already OK:  {ok}")

    if args.dry_run:
        print(f"\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
