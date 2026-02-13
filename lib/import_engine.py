"""
Import engine for merging external researcher CSVs into the ecosystem pipeline.

Pure logic module — no Flask dependencies. All functions are stateless and testable.
Handles: parsing, column mapping, ecosystem splitting, duplicate detection, merging.
"""

import csv
import io
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs

from .columns import CORRECT_COLUMNS, empty_row
from .matching import find_match, normalize_name, similarity


# ── Column Mapping ──────────────────────────────────────────────────────────

# Known aliases: incoming column name -> canonical column name
COLUMN_ALIASES = {
    "tags/categories": "Category",
    "description": "Notes",
    "ecosystem": "Ecosystem/Chain",
    "chain": "Ecosystem/Chain",
    "status": "The Grid Status",
    "twitter handle": "X Handle",
    "twitter": "X Link",
    "twitter link": "X Link",
    "twitter url": "X Link",
    "x": "X Handle",
    "x link": "X Link",
    "tg": "Telegram",
    "telegram link": "Telegram",
    "categories": "Category",
    "tags": "Category",
    "project": "Project Name",
    "name": "Project Name",
    "url": "Website",
    "site": "Website",
    "homepage": "Website",
}

# Known computed columns and their expected value sets
COMPUTED_COLUMN_PATTERNS = {
    "Final Status": {
        "Skipped",
        "Added",
        "Added Not Validated",
        "Validated",
        "To be added - Tether",
        "To be added - General",
        "Not Processed",
        "",
    }
}

# Grid match column groups (primary and secondary)
PRIMARY_GRID_COLS = {
    "profile": "Profile Name",
    "root_id": "Root ID",
    "url": "Matched URL",
    "via": "Matched via",
}
SECONDARY_GRID_COLS = {
    "profile": "Profile Name 2",
    "root_id": "Root ID 2",
    "url": "Matched URL 2",
    "via": "Matched via 2",
}


def parse_input(content: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """
    Parse CSV or TSV text into headers and rows.

    Auto-detects delimiter: if the first line contains tabs, treats as TSV.
    Returns (headers, rows) where rows is a list of dicts.
    """
    if not content or not content.strip():
        return [], []

    # Auto-detect delimiter
    first_line = content.split("\n", 1)[0]
    delimiter = "\t" if "\t" in first_line else ","

    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    headers = list(reader.fieldnames or [])
    rows = list(reader)
    return headers, rows


def detect_ecosystems(
    rows: List[Dict[str, str]], ecosystem_col: str = "Ecosystem"
) -> Dict[str, int]:
    """
    Scan rows for ecosystem values and return counts.

    Returns {ecosystem_name: row_count}. If the ecosystem column doesn't
    exist, all rows get counted under "".
    """
    counts: Dict[str, int] = {}
    for row in rows:
        eco = row.get(ecosystem_col, "").strip()
        counts[eco] = counts.get(eco, 0) + 1
    return counts


def auto_map_columns(
    incoming_headers: List[str],
    canonical_columns: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Auto-map incoming column names to canonical columns.

    Uses three-tier matching:
      1. Exact match (case-insensitive)
      2. Known aliases
      3. Fuzzy similarity (threshold 0.7)

    Returns list of dicts: {incoming, mapped_to, confidence, type}
    where type is: "matched", "suggested", "unmapped", "extra"
    """
    canonical = canonical_columns or list(CORRECT_COLUMNS)
    canonical_lower = {c.lower(): c for c in canonical}
    used_canonical = set()
    mappings = []

    for incoming in incoming_headers:
        incoming_lower = incoming.lower().strip()
        mapping = {
            "incoming": incoming,
            "mapped_to": None,
            "confidence": None,
            "type": "unmapped",
        }

        # Priority 1: Exact match (case-insensitive)
        if incoming_lower in canonical_lower:
            target = canonical_lower[incoming_lower]
            if target not in used_canonical:
                mapping["mapped_to"] = target
                mapping["confidence"] = "exact"
                mapping["type"] = "matched"
                used_canonical.add(target)
                mappings.append(mapping)
                continue

        # Priority 2: Known aliases
        if incoming_lower in COLUMN_ALIASES:
            target = COLUMN_ALIASES[incoming_lower]
            if target not in used_canonical:
                mapping["mapped_to"] = target
                mapping["confidence"] = "alias"
                mapping["type"] = "suggested"
                used_canonical.add(target)
                mappings.append(mapping)
                continue

        # Priority 3: Fuzzy similarity
        best_score = 0.0
        best_target = None
        for canon in canonical:
            if canon in used_canonical:
                continue
            score = similarity(incoming_lower, canon.lower())
            if score > 0.7 and score > best_score:
                best_score = score
                best_target = canon

        if best_target:
            mapping["mapped_to"] = best_target
            mapping["confidence"] = f"fuzzy ({best_score:.0%})"
            mapping["type"] = "suggested"
            used_canonical.add(best_target)
        else:
            mapping["type"] = "extra"

        mappings.append(mapping)

    return mappings


def detect_computed_columns(rows: List[Dict[str, str]]) -> List[str]:
    """
    Detect columns whose values match known formula-output patterns.

    Returns list of column names that appear to be computed/formula-derived.
    """
    computed = []
    for col_name, expected_values in COMPUTED_COLUMN_PATTERNS.items():
        # Check if this column exists in the data
        if not rows or col_name not in rows[0]:
            continue
        # Check if ALL non-empty values match the expected set
        all_match = all(
            row.get(col_name, "").strip() in expected_values for row in rows
        )
        if all_match:
            computed.append(col_name)
    return computed


def resolve_grid_matches(row: Dict[str, str]) -> Dict[str, str]:
    """
    Pick the best Grid match from primary and secondary match columns.

    Prefers the set that has a non-empty Root ID. If both have Root IDs,
    prefers primary. Returns canonical Grid column values.
    """
    primary = {
        key: row.get(col, "").strip() for key, col in PRIMARY_GRID_COLS.items()
    }
    secondary = {
        key: row.get(col, "").strip() for key, col in SECONDARY_GRID_COLS.items()
    }

    # Pick the set with a Root ID; prefer primary if tied
    use_secondary = (
        not primary["root_id"] and secondary["root_id"]
    )
    chosen = secondary if use_secondary else primary

    return {
        "Profile Name": chosen["profile"],
        "Root ID": chosen["root_id"],
        "Matched URL": chosen["url"],
        "Matched via": chosen["via"],
    }


def apply_column_mapping(
    rows: List[Dict[str, str]],
    mapping: Dict[str, str],
    computed_cols: List[str],
) -> List[Dict[str, str]]:
    """
    Transform rows from incoming schema to canonical schema.

    Args:
        rows: Original rows with incoming column names.
        mapping: Dict of {incoming_col: canonical_col} or "__skip__" to drop.
        computed_cols: Columns detected as formula-derived (carried as-is).

    Returns list of rows with canonical column names.
    """
    has_secondary_grid = False
    if rows:
        has_secondary_grid = any(
            col in rows[0] for col in SECONDARY_GRID_COLS.values()
        )

    mapped_rows = []
    for row in rows:
        new_row: Dict[str, str] = {}

        # Apply direct mappings
        for incoming, canonical in mapping.items():
            if canonical == "__skip__":
                continue
            # Skip Grid columns that will be resolved separately
            if has_secondary_grid and canonical in PRIMARY_GRID_COLS.values():
                continue
            new_row[canonical] = row.get(incoming, "").strip()

        # Resolve Grid matches if secondary columns present
        if has_secondary_grid:
            grid_values = resolve_grid_matches(row)
            new_row.update(grid_values)

        mapped_rows.append(new_row)

    return mapped_rows


# ── Ecosystem Splitting ─────────────────────────────────────────────────────


def map_ecosystem_to_chain(
    ecosystem: str, chains_config: List[Dict]
) -> Optional[str]:
    """
    Map an ecosystem name to a chain ID from chains.json.

    Tries: exact ID match, case-insensitive name match, containment.
    Returns chain ID or None.
    """
    eco_lower = ecosystem.lower().strip()
    if not eco_lower:
        return None

    for chain in chains_config:
        chain_id = chain["id"].lower()
        chain_name = chain["name"].lower()

        # Exact ID match
        if eco_lower == chain_id:
            return chain["id"]
        # Exact name match
        if eco_lower == chain_name:
            return chain["id"]

    # Containment: ecosystem contains chain name or vice versa
    for chain in chains_config:
        chain_name = chain["name"].lower()
        if eco_lower in chain_name or chain_name in eco_lower:
            return chain["id"]

    return None


def split_by_ecosystem(
    rows: List[Dict[str, str]],
    chains_config: List[Dict],
) -> Tuple[Dict[str, List[Dict[str, str]]], List[str]]:
    """
    Group rows by Chain column and map to known chain IDs.

    Returns ({chain_id: rows}, unmatched_ecosystem_names).
    """
    groups: Dict[str, List[Dict[str, str]]] = {}
    unmatched: List[str] = []
    seen_unmatched = set()

    for row in rows:
        eco = row.get("Ecosystem/Chain", "").strip()
        chain_id = map_ecosystem_to_chain(eco, chains_config)

        if chain_id:
            row["Ecosystem/Chain"] = chain_id
            groups.setdefault(chain_id, []).append(row)
        else:
            if eco and eco not in seen_unmatched:
                unmatched.append(eco)
                seen_unmatched.add(eco)
            # Still group them under the raw ecosystem name
            groups.setdefault(eco or "__unknown__", []).append(row)

    return groups, unmatched


# ── Duplicate Detection ─────────────────────────────────────────────────────


def normalize_url(url: str) -> str:
    """
    Normalize a URL for comparison.

    Strips protocol, www prefix, trailing slash, and common tracking params.
    """
    if not url:
        return ""
    url = url.strip().lower()
    # Strip protocol
    url = re.sub(r"^https?://", "", url)
    # Strip www prefix
    url = re.sub(r"^www\.", "", url)
    # Strip trailing slash
    url = url.rstrip("/")
    # Strip common tracking params
    url = re.sub(r"\?.*$", "", url)
    return url


def find_duplicates(
    incoming_rows: List[Dict[str, str]],
    existing_rows: List[Dict[str, str]],
    threshold: float = 0.8,
) -> Tuple[List[Dict], List[Dict[str, str]]]:
    """
    Find duplicates between incoming and existing rows.

    Checks both Project Name (fuzzy) and Website URL (normalized exact).

    Returns (duplicate_matches, new_rows) where duplicate_matches is a list
    of {incoming, existing, score, method} dicts.
    """
    existing_names = [r.get("Project Name", "") for r in existing_rows]
    existing_urls = {
        normalize_url(r.get("Website", "")): i
        for i, r in enumerate(existing_rows)
        if r.get("Website", "").strip()
    }

    duplicates = []
    new_rows = []

    for incoming in incoming_rows:
        name = incoming.get("Project Name", "")
        url = normalize_url(incoming.get("Website", ""))
        matched = False

        # Check name match
        if name:
            match_name, score = find_match(name, existing_names, threshold)
            if match_name:
                # Find the existing row
                for existing in existing_rows:
                    if existing.get("Project Name", "") == match_name:
                        duplicates.append({
                            "incoming": incoming,
                            "existing": existing,
                            "score": score,
                            "method": "name",
                        })
                        matched = True
                        break

        # Check URL match (if not already matched by name)
        if not matched and url and url in existing_urls:
            idx = existing_urls[url]
            duplicates.append({
                "incoming": incoming,
                "existing": existing_rows[idx],
                "score": 1.0,
                "method": "url",
            })
            matched = True

        if not matched:
            new_rows.append(incoming)

    return duplicates, new_rows


# ── Merge Logic ─────────────────────────────────────────────────────────────


def compute_field_diffs(
    incoming: Dict[str, str],
    existing: Dict[str, str],
    computed_cols: List[str],
) -> List[Dict]:
    """
    Compare values column-by-column between incoming and existing rows.

    Skips: empty-on-both, identical values, computed columns.
    Returns list of {column, ours, theirs, is_computed} dicts.
    """
    diffs = []
    all_cols = set(list(incoming.keys()) + list(existing.keys()))

    for col in all_cols:
        ours = existing.get(col, "").strip()
        theirs = incoming.get(col, "").strip()
        is_computed = col in computed_cols

        # Skip if both empty or identical
        if ours == theirs:
            continue
        # Skip if both are empty-ish
        if not ours and not theirs:
            continue

        diffs.append({
            "column": col,
            "ours": ours,
            "theirs": theirs,
            "is_computed": is_computed,
        })

    return diffs


def apply_merge_strategy(ours: str, theirs: str, strategy: str) -> str:
    """
    Apply a merge strategy to resolve conflicting values.

    Strategies:
        "append"     — Combine with "; " separator (default)
        "keep_ours"  — Keep existing value
        "keep_theirs"— Use incoming value
        "skip"       — No change (same as keep_ours)
    """
    if strategy == "keep_theirs":
        return theirs if theirs else ours
    if strategy in ("keep_ours", "skip"):
        return ours if ours else theirs
    # Default: append
    if ours and theirs and ours != theirs:
        # Don't duplicate if theirs is already contained in ours
        if theirs in ours:
            return ours
        return f"{ours}; {theirs}"
    return ours or theirs


def generate_merge_preview(
    duplicates: List[Dict],
    new_rows: List[Dict[str, str]],
    strategies: Dict[str, str],
    computed_cols: List[str],
) -> Dict:
    """
    Generate a preview of what the merge will produce.

    Args:
        duplicates: List of {incoming, existing, score, method} dicts.
        new_rows: Rows that are genuinely new (no duplicate found).
        strategies: {column_name: strategy_string} overrides.
        computed_cols: Read-only columns to skip during merge.

    Returns preview dict with diffs, counts, and resolved values.
    """
    merge_items = []
    skip_count = 0

    for dup in duplicates:
        diffs = compute_field_diffs(
            dup["incoming"], dup["existing"], computed_cols
        )

        # Filter out computed diffs (they're informational only)
        actionable_diffs = [d for d in diffs if not d["is_computed"]]

        if not actionable_diffs:
            skip_count += 1
            continue

        resolved_diffs = []
        for diff in actionable_diffs:
            col = diff["column"]
            strategy = strategies.get(col, "append")
            resolved = apply_merge_strategy(diff["ours"], diff["theirs"], strategy)
            resolved_diffs.append({
                **diff,
                "strategy": strategy,
                "resolved": resolved,
            })

        merge_items.append({
            "project_name": dup["existing"].get("Project Name", ""),
            "match_score": dup["score"],
            "match_method": dup["method"],
            "conflicts": resolved_diffs,
        })

    return {
        "new_count": len(new_rows),
        "merge_count": len(merge_items),
        "skip_count": skip_count,
        "diffs": merge_items,
    }


def execute_merge(
    chain: str,
    existing_rows: List[Dict[str, str]],
    new_rows: List[Dict[str, str]],
    duplicates: List[Dict],
    strategies: Dict[str, str],
    computed_cols: List[str],
) -> Tuple[List[Dict[str, str]], int, int, int]:
    """
    Execute the merge: update duplicates and append new rows.

    Returns (merged_rows, added_count, updated_count, skipped_count).
    """
    # Build lookup for existing rows by Project Name
    existing_by_name = {}
    for i, row in enumerate(existing_rows):
        name = row.get("Project Name", "").strip().lower()
        if name:
            existing_by_name[name] = i

    updated_count = 0
    skipped_count = 0

    # Apply duplicate merges
    for dup in duplicates:
        existing_name = dup["existing"].get("Project Name", "").strip().lower()
        idx = existing_by_name.get(existing_name)
        if idx is None:
            skipped_count += 1
            continue

        diffs = compute_field_diffs(
            dup["incoming"], existing_rows[idx], computed_cols
        )
        actionable = [d for d in diffs if not d["is_computed"]]

        if not actionable:
            skipped_count += 1
            continue

        for diff in actionable:
            col = diff["column"]
            strategy = strategies.get(col, "append")
            existing_rows[idx][col] = apply_merge_strategy(
                diff["ours"], diff["theirs"], strategy
            )
        updated_count += 1

    # Append new rows
    added_count = 0
    for incoming in new_rows:
        new = empty_row(chain)
        for col in new:
            if col in incoming and incoming[col]:
                new[col] = incoming[col]
        # Also carry over any extra columns not in canonical set
        for col, val in incoming.items():
            if col not in new and val:
                new[col] = val
        existing_rows.append(new)
        added_count += 1

    # Post-merge normalization: extract Root ID from admin URLs where missing
    _normalize_admin_urls(existing_rows)

    return existing_rows, added_count, updated_count, skipped_count


def _normalize_admin_urls(rows: List[Dict[str, str]]) -> int:
    """
    For rows with admin-style Matched URLs (admin.thegrid.id/?rootId=...),
    extract the Root ID into the Root ID column if not already set.
    Returns count of rows normalized.
    """
    count = 0
    for row in rows:
        matched_url = row.get("Matched URL", "")
        root_id = row.get("Root ID", "").strip()
        if not root_id and "admin.thegrid.id" in matched_url and "rootId=" in matched_url:
            try:
                parsed = urlparse(matched_url)
                extracted_id = parse_qs(parsed.query).get("rootId", [""])[0]
                if extracted_id:
                    row["Root ID"] = extracted_id
                    count += 1
            except Exception:
                pass
    return count
