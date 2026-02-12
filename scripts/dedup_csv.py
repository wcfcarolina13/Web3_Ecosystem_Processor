#!/usr/bin/env python3
"""
Deduplicate rows in ecosystem CSV by normalized name + website URL.

Strategy:
1. Group rows by normalized project name (lib/matching.normalize_name)
2. Within each group, sub-group by normalized website URL domain
   - Same domain (or both empty) → true duplicates → merge into one row
   - Different domains → different projects → keep all
3. For true duplicate groups, merge fields: keep richest row as base,
   fill in any empty fields from other rows
4. Fuzzy-matched groups (different original names) get "(fuzzy dedup)" appended
   to Notes so researchers know the merge was automated

Usage:
    python scripts/dedup_csv.py --chain near --dry-run
    python scripts/dedup_csv.py --chain near
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.csv_utils import load_csv, write_csv, find_main_csv
from lib.matching import normalize_name


# ── URL normalization ──────────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """
    Extract and normalize the domain from a URL for comparison.
    Returns empty string if no valid URL.

    Examples:
        "https://aurora.dev"    → "aurora.dev"
        "https://www.aurora.dev/" → "aurora.dev"
        "https://aurora.plus/"  → "aurora.plus"
        "https://auroraswap.net" → "auroraswap.net"
    """
    url = url.strip()
    if not url:
        return ""
    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Strip www prefix
        domain = re.sub(r"^www\.", "", domain)
        # Strip port
        domain = domain.split(":")[0]
        return domain
    except Exception:
        return ""


# ── Data richness scoring ─────────────────────────────────────────────────

# Fields weighted by importance for choosing the "best" row
FIELD_WEIGHTS = {
    "Matched URL": 10,
    "Root ID": 10,
    "Profile Name": 10,
    "Website": 5,
    "X Link": 3,
    "X Handle": 3,
    "Telegram": 2,
    "Suspect USDT support?": 5,
    "General Stablecoin Adoption": 3,
    "Evidence & Source URLs": 3,
    "Category": 1,
    "Notes": 1,
}


def data_richness(row: Dict) -> int:
    """Score a row by how many important fields are populated."""
    score = 0
    for field, weight in FIELD_WEIGHTS.items():
        val = row.get(field, "").strip()
        if val and val != "FALSE":
            if field == "Suspect USDT support?" and val == "TRUE":
                score += weight
            elif field == "General Stablecoin Adoption" and val == "TRUE":
                score += weight
            elif field not in ("Suspect USDT support?", "General Stablecoin Adoption"):
                score += weight
    return score


# ── Merge logic ───────────────────────────────────────────────────────────

# Fields that should be merged by taking the longest/richest value
MERGE_FIELDS = [
    "Website", "X Link", "X Handle", "Telegram",
    "Category",
    "Profile Name", "Root ID", "Matched URL", "Matched via",
    "The Grid Status",
    "Suspect USDT support?", "General Stablecoin Adoption",
    "Web3 but no stablecoin",
    "Evidence & Source URLs",
]

# Boolean-like fields where TRUE wins
BOOL_TRUE_FIELDS = {
    "Suspect USDT support?", "General Stablecoin Adoption",
    "Web3 but no stablecoin",
}


def merge_rows(group: List[Dict], is_fuzzy: bool = False) -> Dict:
    """
    Merge a group of duplicate rows into one.

    - Start with the richest row as base
    - Fill in empty fields from other rows
    - For boolean fields, TRUE wins
    - For Notes, combine unique parts
    - If fuzzy match (different original names), annotate Notes
    """
    if len(group) == 1:
        return group[0]

    # Sort by richness (highest first)
    scored = sorted(group, key=data_richness, reverse=True)
    base = dict(scored[0])  # Copy the richest row

    # Collect all original names for the fuzzy annotation
    original_names = list(dict.fromkeys(
        r.get("Project Name", "").strip() for r in group
        if r.get("Project Name", "").strip()
    ))

    # Collect sources
    sources = list(dict.fromkeys(
        r.get("Source", "").strip() for r in group
        if r.get("Source", "").strip()
    ))

    for other in scored[1:]:
        for field in MERGE_FIELDS:
            base_val = base.get(field, "").strip()
            other_val = other.get(field, "").strip()

            if field in BOOL_TRUE_FIELDS:
                # TRUE wins
                if other_val == "TRUE":
                    base[field] = "TRUE"
            elif not base_val and other_val:
                # Fill empty field from other row
                base[field] = other_val

    # Merge Notes: combine unique notes, preserving enrichment
    all_notes = []
    seen_notes = set()
    for r in scored:
        note = r.get("Notes", "").strip()
        if note and note not in seen_notes:
            all_notes.append(note)
            seen_notes.add(note)

    # Take the richest note as primary, add unique enrichment from others
    if all_notes:
        primary_note = all_notes[0]
        # Extract enrichment parts (after " | ") from other notes
        extra_enrichments = []
        for note in all_notes[1:]:
            parts = note.split(" | ")
            for part in parts[1:]:
                part = part.strip()
                if part and part not in primary_note:
                    extra_enrichments.append(part)

        if extra_enrichments:
            primary_note = primary_note + " | " + " | ".join(extra_enrichments)

        base["Notes"] = primary_note

    # Merge Evidence & Source URLs (combine unique entries)
    all_evidence = []
    seen_evidence = set()
    for r in scored:
        ev = r.get("Evidence & Source URLs", "").strip()
        if ev:
            for part in ev.split(" | "):
                part = part.strip()
                if part and part not in seen_evidence:
                    all_evidence.append(part)
                    seen_evidence.add(part)
    if all_evidence:
        base["Evidence & Source URLs"] = " | ".join(all_evidence)

    # Merge Source field (combine)
    if len(sources) > 1:
        base["Source"] = "; ".join(sources)

    # Annotate fuzzy matches
    if is_fuzzy and len(original_names) > 1:
        fuzzy_note = f"(fuzzy dedup: merged from {'; '.join(original_names)})"
        existing_notes = base.get("Notes", "").strip()
        if existing_notes:
            base["Notes"] = existing_notes + " | " + fuzzy_note
        else:
            base["Notes"] = fuzzy_note

    return base


# ── Main dedup logic ──────────────────────────────────────────────────────

def dedup_csv(
    csv_path: Path,
    dry_run: bool = False,
) -> Tuple[int, int, int, int]:
    """
    Deduplicate rows in the CSV.

    Returns (total_rows, unique_rows, exact_dupes_removed, fuzzy_dupes_removed).
    """
    print(f"Loading CSV: {csv_path}")
    rows = load_csv(csv_path)
    total = len(rows)
    print(f"  {total} rows loaded")

    # Phase 1: Group by normalized name
    norm_groups: Dict[str, List[int]] = {}
    for i, r in enumerate(rows):
        name = r.get("Project Name", "").strip()
        if not name:
            continue
        norm = normalize_name(name)
        if norm not in norm_groups:
            norm_groups[norm] = []
        norm_groups[norm].append(i)

    # Phase 2: Sub-group by website domain within each name group
    result_rows = []
    exact_dupes = 0
    fuzzy_dupes = 0
    seen_indices = set()

    # Track singleton groups (no dupes)
    for norm, indices in norm_groups.items():
        if len(indices) == 1:
            result_rows.append((indices[0], rows[indices[0]]))
            seen_indices.add(indices[0])
            continue

        # Multiple rows with same normalized name — check URLs
        url_subgroups: Dict[str, List[int]] = {}
        for idx in indices:
            domain = normalize_url(rows[idx].get("Website", ""))
            # Group empty URLs together (they're likely the same project)
            key = domain if domain else "__empty__"
            if key not in url_subgroups:
                url_subgroups[key] = []
            url_subgroups[key].append(idx)

        # If all rows have different domains, they might be different projects
        # But also check: if one has empty URL and another has a URL, merge them
        # (empty URL is just missing data, not a different project)

        # Merge strategy:
        # 1. If only one domain (or all empty): merge all as one group
        # 2. If multiple domains: merge rows within each domain subgroup separately
        #    But also merge "empty URL" rows into the largest subgroup

        if len(url_subgroups) == 1:
            # All same domain (or all empty) — straightforward merge
            group_rows = [rows[i] for i in indices]
            original_names = set(r.get("Project Name", "") for r in group_rows)
            is_fuzzy = len(original_names) > 1
            merged = merge_rows(group_rows, is_fuzzy=is_fuzzy)
            result_rows.append((indices[0], merged))
            removed = len(indices) - 1
            if is_fuzzy:
                fuzzy_dupes += removed
            else:
                exact_dupes += removed

            if dry_run and removed > 0:
                names = [f'"{rows[i].get("Project Name", "")}"' for i in indices]
                tag = "FUZZY" if is_fuzzy else "EXACT"
                print(f"  [{tag}] Merged {len(indices)} rows → {names}")

        else:
            # Multiple domains — check for empty URL group to absorb
            empty_indices = url_subgroups.pop("__empty__", [])

            for domain, dom_indices in url_subgroups.items():
                # Absorb any empty-URL rows into this domain group
                # (only if there's exactly one domain group besides empty)
                all_in_group = list(dom_indices)
                if len(url_subgroups) == 1 and empty_indices:
                    all_in_group.extend(empty_indices)
                    empty_indices = []  # consumed

                if len(all_in_group) == 1:
                    result_rows.append((all_in_group[0], rows[all_in_group[0]]))
                else:
                    group_rows = [rows[i] for i in all_in_group]
                    original_names = set(r.get("Project Name", "") for r in group_rows)
                    is_fuzzy = len(original_names) > 1
                    merged = merge_rows(group_rows, is_fuzzy=is_fuzzy)
                    result_rows.append((all_in_group[0], merged))
                    removed = len(all_in_group) - 1
                    if is_fuzzy:
                        fuzzy_dupes += removed
                    else:
                        exact_dupes += removed

                    if dry_run and removed > 0:
                        names = [f'"{rows[i].get("Project Name", "")}"' for i in all_in_group]
                        tag = "FUZZY" if is_fuzzy else "EXACT"
                        print(f"  [{tag}] Merged {len(all_in_group)} rows ({domain}) → {names}")

            # Any remaining empty-URL rows that weren't absorbed
            for idx in empty_indices:
                result_rows.append((idx, rows[idx]))

            # Rows that were split by domain = kept as separate projects
            if dry_run and len(url_subgroups) > 1:
                all_names = []
                for domain, dom_indices in url_subgroups.items():
                    for idx in dom_indices:
                        all_names.append(f'"{rows[idx].get("Project Name", "")}" ({domain})')
                print(f"  [SPLIT] Different domains, kept separate: {'; '.join(all_names)}")

    # Also include rows with empty project name (shouldn't happen, but safe)
    for i, r in enumerate(rows):
        if not r.get("Project Name", "").strip() and i not in seen_indices:
            result_rows.append((i, r))

    # Sort by original row order (preserve CSV ordering)
    result_rows.sort(key=lambda x: x[0])
    final_rows = [r for _, r in result_rows]

    unique_count = len(final_rows)

    if not dry_run and (exact_dupes > 0 or fuzzy_dupes > 0):
        write_csv(final_rows, csv_path)
        print(f"\nDeduplicated CSV written to: {csv_path}")

    return total, unique_count, exact_dupes, fuzzy_dupes


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate ecosystem CSV rows by normalized name + URL"
    )
    parser.add_argument("--chain", required=True, help="Chain ID (e.g., near)")
    parser.add_argument("--csv", help="Path to CSV (auto-detected if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview dedup without writing")
    args = parser.parse_args()

    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_path = find_main_csv(args.chain)
        if not csv_path:
            print(f"Error: No CSV found in data/{args.chain}/")
            sys.exit(1)

    total, unique, exact, fuzzy = dedup_csv(csv_path, dry_run=args.dry_run)

    print(f"\n{'='*60}")
    print(f"DEDUP SUMMARY")
    print(f"{'='*60}")
    print(f"Total rows:           {total}")
    print(f"Unique rows:          {unique}")
    print(f"Exact dupes removed:  {exact}")
    print(f"Fuzzy dupes removed:  {fuzzy}")
    print(f"Total removed:        {exact + fuzzy}")
    if args.dry_run:
        print(f"\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
