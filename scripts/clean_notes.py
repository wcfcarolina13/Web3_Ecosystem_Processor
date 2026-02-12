#!/usr/bin/env python3
"""
Clean up the Notes column in ecosystem CSVs.

Removes:
- Redundant "CATEGORIES from SOURCE - " prefixes (categories + source already have own columns)
- Emojis and Unicode decorative characters
- Marketing fluff and trailing whitespace

Preserves:
- Enrichment findings after " | " separators (e.g., "Grid confirms: USDT")
- Meaningful descriptions (the part after " - " in the old format)

Usage:
    python scripts/clean_notes.py --chain near --dry-run
    python scripts/clean_notes.py --chain near
    python scripts/clean_notes.py --chain near --limit 20
"""

import argparse
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.csv_utils import load_csv, write_csv, find_main_csv


# ── Emoji regex ─────────────────────────────────────────────────────────────
# Comprehensive Unicode emoji/symbol removal pattern
EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F700-\U0001F77F"  # alchemical symbols
    "\U0001F780-\U0001F7FF"  # geometric shapes extended
    "\U0001F800-\U0001F8FF"  # supplemental arrows-C
    "\U0001F900-\U0001F9FF"  # supplemental symbols & pictographs
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols & pictographs extended-A
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"  # enclosed characters
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # zero width joiner
    "\U00002764"             # heart
    "\U0000FE0F"             # variation selector-16
    "\U00003030"             # wavy dash
    "\U000000A9"             # copyright
    "\U000000AE"             # registered
    "\U00002122"             # trademark
    "\U000023CF"             # eject symbol
    "\U000023E9-\U000023F3"  # various symbols
    "\U000023F8-\U000023FA"  # various symbols
    "\U0000231A-\U0000231B"  # watch/hourglass
    "\U00002934-\U00002935"  # arrows
    "\U00002B05-\U00002B07"  # arrows
    "\U00002B1B-\U00002B1C"  # squares
    "\U00002B50"             # star
    "\U00002B55"             # circle
    "\U00003297"             # congratulations
    "\U00003299"             # secret
    "\U0000203C"             # double exclamation
    "\U00002049"             # exclamation question
    "]+",
    flags=re.UNICODE,
)

# ── Source prefix regex ────────────────────────────────────────────────────
# Matches: "CATEGORIES from SOURCE - description"
# Captures everything up to and including " from SOURCE - "
SOURCE_PREFIX_RE = re.compile(
    r"^.+?\s+from\s+(?:NEARCatalog|AwesomeNEAR|Generic Scraper)\s*-\s*",
    re.IGNORECASE,
)

# Matches bare prefix without description: "CATEGORIES from SOURCE" (no dash)
SOURCE_BARE_RE = re.compile(
    r"^.+?\s+from\s+(?:NEARCatalog|AwesomeNEAR|Generic Scraper)\s*$",
    re.IGNORECASE,
)


def clean_note(note: str) -> str:
    """
    Clean a single Notes value.

    Strategy:
    1. Split on " | " to separate original note from enrichment findings
    2. Clean only the first segment (original scraper note)
    3. Rejoin with enrichment findings intact
    """
    if not note or not note.strip():
        return ""

    parts = note.split(" | ")
    first_part = parts[0].strip()
    enrichment_parts = [p.strip() for p in parts[1:] if p.strip()]

    # Clean the first part (scraper-generated note)
    cleaned = first_part

    # Step 1: Strip "CATEGORIES from SOURCE - " prefix
    cleaned = SOURCE_PREFIX_RE.sub("", cleaned)

    # Step 2: If entire first part is bare "CATEGORIES from SOURCE" (no description), clear it
    if SOURCE_BARE_RE.match(cleaned):
        cleaned = ""

    # Step 3: Strip emojis
    cleaned = EMOJI_RE.sub("", cleaned)

    # Step 4: Collapse whitespace and trim
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Step 5: Strip trailing punctuation artifacts
    cleaned = cleaned.strip(" -;|,.")

    # Rejoin with enrichment parts
    all_parts = [p for p in [cleaned] + enrichment_parts if p]
    return " | ".join(all_parts)


def run_cleanup(
    csv_path: Path,
    dry_run: bool = False,
    limit: int = 0,
) -> tuple:
    """
    Clean Notes column in the CSV.
    Returns (total_rows, notes_cleaned, notes_unchanged).
    """
    print(f"Loading CSV: {csv_path}")
    rows = load_csv(csv_path)
    total = len(rows)
    process_rows = rows[:limit] if limit > 0 else rows
    print(f"  {total} rows total, processing {len(process_rows)}")

    cleaned_count = 0
    unchanged_count = 0

    for i, row in enumerate(process_rows):
        original = row.get("Notes", "").strip()
        if not original:
            continue

        cleaned = clean_note(original)

        if cleaned != original:
            cleaned_count += 1
            if dry_run and cleaned_count <= 30:
                # Show before/after for dry run
                orig_display = original[:100] + ("..." if len(original) > 100 else "")
                clean_display = cleaned[:100] + ("..." if len(cleaned) > 100 else "")
                print(f"  [{i+1}] BEFORE: {orig_display}")
                print(f"        AFTER:  {clean_display}")
                print()

            if not dry_run:
                row["Notes"] = cleaned
        else:
            unchanged_count += 1

    # Write output
    if not dry_run and cleaned_count > 0:
        write_csv(rows, csv_path)
        print(f"\nCleaned CSV written to: {csv_path}")
    elif dry_run:
        print(f"\n[DRY RUN] No files written.")

    return total, cleaned_count, unchanged_count


def main():
    parser = argparse.ArgumentParser(
        description="Clean up Notes column in ecosystem CSV"
    )
    parser.add_argument(
        "--chain", required=True, help="Chain ID (e.g., near, aptos)"
    )
    parser.add_argument(
        "--csv", help="Path to CSV (auto-detected from data/<chain>/ if omitted)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview cleanup without writing files",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Process only first N rows (for testing)",
    )
    args = parser.parse_args()

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

    total, cleaned, unchanged = run_cleanup(
        csv_path, dry_run=args.dry_run, limit=args.limit,
    )

    print(f"\n{'='*60}")
    print(f"NOTES CLEANUP SUMMARY")
    print(f"{'='*60}")
    print(f"Total rows:     {total}")
    print(f"Notes cleaned:  {cleaned}")
    print(f"Notes unchanged: {unchanged}")

    if args.dry_run:
        print(f"\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
