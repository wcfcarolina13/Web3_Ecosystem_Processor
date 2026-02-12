#!/usr/bin/env python3
"""
Expand Grid matching beyond the original name/URL search.

The initial Grid matcher (in compare.py / enrich_grid_assets.py) matched 150/791
NEAR projects. This script tries additional strategies on the 641 unmatched rows:

  Strategy 1 — Batch name match (profiles + products)
    Downloads all Grid profiles (2,986) and products (6,206), builds a local
    lookup table, and matches CSV project names against it using normalized
    name comparison. Catches name variants and product-level matches.

  Strategy 2 — URL domain match (batch)
    Compares CSV Website domains against all Grid root urlMain domains.
    Faster than per-row API calls and catches domain redirects.

  Strategy 3 — Slug-based lookup
    Generates candidate slugs from project name (lowercase, underscores)
    and queries Grid API directly. Catches projects where the slug matches
    but the name/URL don't.

  Strategy 4 — Twitter/X handle cross-reference
    For remaining unmatched rows with X Handle data, queries Grid socials
    to find matching Twitter handles.

Usage:
    python scripts/expand_grid_matches.py --chain near --dry-run
    python scripts/expand_grid_matches.py --chain near
    python scripts/expand_grid_matches.py --chain near --strategy batch-name,batch-url
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.columns import CORRECT_COLUMNS
from lib.csv_utils import load_csv, write_csv, find_main_csv
from lib.grid_client import GridAPIClient
from lib.matching import normalize_name, similarity

# ── Constants ──────────────────────────────────────────────────────────

BATCH_SIZE = 500          # Grid API pagination batch size
REQUEST_DELAY = 0.3       # seconds between individual API calls
CONFIDENCE_THRESHOLD = 0.85  # minimum confidence for auto-match
EXPAND_MARKER = "expanded-grid"  # Evidence marker for incremental skip

ALL_STRATEGIES = ["batch-name", "batch-url", "slug", "twitter"]

# Domains too generic for URL-based matching (social platforms, major chains, etc.)
EXCLUDED_DOMAINS = {
    "x.com", "twitter.com", "t.me", "telegram.org", "discord.gg", "discord.com",
    "github.com", "youtube.com", "reddit.com", "medium.com", "mirror.xyz",
    "linkedin.com", "facebook.com", "instagram.com",
    "near.org",  # NEAR Protocol's own domain — many community projects use it
    "aurora.dev",  # Aurora's domain
    "google.com", "apple.com",
}

# Normalized names too short/generic to safely match
MIN_NORMALIZED_LEN = 4  # e.g., "bee" (3 chars) is too risky, "near" (4) is borderline


# ── Grid Data Fetching ─────────────────────────────────────────────────

def fetch_all_profiles(client: GridAPIClient) -> List[Dict]:
    """Fetch all Grid profiles with batch pagination."""
    all_items = []
    offset = 0
    while True:
        data = client.raw_query(f"""
        query {{
          profileInfos(limit: {BATCH_SIZE}, offset: {offset}) {{
            id name
            profileStatus {{ name }}
            root {{ id slug urlMain }}
          }}
        }}
        """)
        batch = data.get("profileInfos", [])
        if not batch:
            break
        all_items.extend(batch)
        offset += BATCH_SIZE
    return all_items


def fetch_all_products(client: GridAPIClient) -> List[Dict]:
    """Fetch all Grid products with batch pagination."""
    all_items = []
    offset = 0
    while True:
        data = client.raw_query(f"""
        query {{
          products(limit: {BATCH_SIZE}, offset: {offset}) {{
            id name
            productType {{ name }}
            productStatus {{ name }}
            root {{ id slug urlMain }}
          }}
        }}
        """)
        batch = data.get("products", [])
        if not batch:
            break
        all_items.extend(batch)
        offset += BATCH_SIZE
    return all_items


def fetch_root_socials(client: GridAPIClient, root_id: str) -> List[Dict]:
    """Fetch socials for a specific root."""
    data = client.raw_query("""
    query($rootId: String!) {
      roots(where: { id: { _eq: $rootId } }, limit: 1) {
        socials { name socialType { name } }
      }
    }
    """, {"rootId": root_id})
    roots = data.get("roots", [])
    if roots:
        return roots[0].get("socials", [])
    return []


# ── Index Building ─────────────────────────────────────────────────────

def extract_domain(url: str) -> str:
    """Extract clean domain from URL (no www, no protocol)."""
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc or parsed.path.split("/")[0]
        domain = domain.lower().replace("www.", "")
        return domain
    except Exception:
        return ""


def build_name_index(profiles: List[Dict], products: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Build a normalized-name → [grid_entry] lookup.
    Each entry has: name, grid_type, grid_id, status, root_slug, root_url, root_id
    """
    index: Dict[str, List[Dict]] = {}

    for p in profiles:
        name = p.get("name", "").strip()
        if not name or len(name) < 2:
            continue
        root = p.get("root") or {}
        status = (p.get("profileStatus") or {}).get("name", "")
        entry = {
            "name": name,
            "grid_type": "profile",
            "grid_id": p.get("id", ""),
            "status": status,
            "root_slug": root.get("slug", ""),
            "root_url": root.get("urlMain", ""),
            "root_id": root.get("id", ""),
        }
        norm = normalize_name(name)
        if norm:
            index.setdefault(norm, []).append(entry)
        # Also index the raw lowered name (no suffix stripping)
        raw = re.sub(r"[^a-z0-9]", "", name.lower())
        if raw and raw != norm:
            index.setdefault(raw, []).append(entry)

    for p in products:
        name = p.get("name", "").strip()
        if not name or len(name) < 2:
            continue
        root = p.get("root") or {}
        ptype = (p.get("productType") or {}).get("name", "")
        status = (p.get("productStatus") or {}).get("name", "")
        entry = {
            "name": name,
            "grid_type": "product",
            "grid_id": p.get("id", ""),
            "status": status,
            "product_type": ptype,
            "root_slug": root.get("slug", ""),
            "root_url": root.get("urlMain", ""),
            "root_id": root.get("id", ""),
        }
        norm = normalize_name(name)
        if norm:
            index.setdefault(norm, []).append(entry)
        raw = re.sub(r"[^a-z0-9]", "", name.lower())
        if raw and raw != norm:
            index.setdefault(raw, []).append(entry)

    return index


def build_url_index(profiles: List[Dict], products: List[Dict]) -> Dict[str, List[Dict]]:
    """Build a domain → [grid_entry] lookup from all roots."""
    index: Dict[str, List[Dict]] = {}
    seen_roots: Set[str] = set()

    for items, grid_type in [(profiles, "profile"), (products, "product")]:
        for p in items:
            root = p.get("root") or {}
            root_id = root.get("id", "")
            root_url = root.get("urlMain", "")
            if not root_url or root_id in seen_roots:
                continue
            seen_roots.add(root_id)

            domain = extract_domain(root_url)
            if not domain:
                continue

            name = p.get("name", "").strip()
            status_obj = p.get("profileStatus") or p.get("productStatus") or {}
            status = status_obj.get("name", "") if isinstance(status_obj, dict) else ""

            entry = {
                "name": name,
                "grid_type": grid_type,
                "grid_id": p.get("id", ""),
                "status": status,
                "root_slug": root.get("slug", ""),
                "root_url": root_url,
                "root_id": root_id,
            }
            index.setdefault(domain, []).append(entry)

    return index


# ── Matching Strategies ────────────────────────────────────────────────

def pick_best_entry(candidates: List[Dict], csv_name: str) -> Optional[Dict]:
    """
    From a list of Grid entries matching a normalized name, pick the best.
    Prefers: profiles > products, Active > other, highest name similarity.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    def score(entry):
        s = 0.0
        # Prefer profiles over products
        if entry.get("grid_type") == "profile":
            s += 2.0
        # Prefer Active status
        if entry.get("status") == "Active":
            s += 1.0
        elif entry.get("status") == "Live":
            s += 0.8
        # Name similarity bonus
        sim = similarity(
            re.sub(r"[^a-z0-9]", "", entry.get("name", "").lower()),
            re.sub(r"[^a-z0-9]", "", csv_name.lower()),
        )
        s += sim
        return s

    candidates.sort(key=score, reverse=True)
    return candidates[0]


def compute_confidence(csv_name: str, grid_name: str) -> float:
    """Compute match confidence between CSV name and Grid name."""
    norm_csv = normalize_name(csv_name)
    norm_grid = normalize_name(grid_name)

    if norm_csv == norm_grid:
        return 1.0

    # Raw alphanum comparison
    raw_csv = re.sub(r"[^a-z0-9]", "", csv_name.lower())
    raw_grid = re.sub(r"[^a-z0-9]", "", grid_name.lower())
    if raw_csv == raw_grid:
        return 0.98

    # Containment
    if raw_csv in raw_grid or raw_grid in raw_csv:
        return 0.90

    # Similarity
    return similarity(norm_csv, norm_grid)


def strategy_batch_name(
    unmatched: List[Tuple[int, Dict]],
    name_index: Dict[str, List[Dict]],
) -> List[Tuple[int, Dict, str, float]]:
    """
    Strategy 1: Match CSV names against batch-downloaded Grid profiles + products.
    Returns list of (row_idx, grid_entry, method, confidence).
    """
    results = []
    for row_idx, row in unmatched:
        csv_name = row.get("Project Name", "").strip()
        if not csv_name:
            continue

        # Try normalized name
        norm = normalize_name(csv_name)
        if len(norm) < MIN_NORMALIZED_LEN:
            continue  # Too short to match safely

        candidates = name_index.get(norm, [])

        # Also try raw alphanum
        if not candidates:
            raw = re.sub(r"[^a-z0-9]", "", csv_name.lower())
            if len(raw) >= MIN_NORMALIZED_LEN:
                candidates = name_index.get(raw, [])

        if not candidates:
            continue

        best = pick_best_entry(candidates, csv_name)
        if not best:
            continue

        # Extra validation: if the raw names differ significantly, skip
        conf = compute_confidence(csv_name, best["name"])
        if conf < CONFIDENCE_THRESHOLD:
            continue

        # Guard 1: if CSV name has extra meaningful words beyond the Grid name,
        # it might be a different project (e.g., "Moon Shot" != "Moonshot" if URLs differ)
        csv_words = set(re.sub(r"[^a-z0-9 ]", "", csv_name.lower()).split())
        grid_words = set(re.sub(r"[^a-z0-9 ]", "", best["name"].lower()).split())
        noise = {"the", "a", "an", "of", "and", "for", "on", "in", "by", "is"}
        csv_meaningful = csv_words - noise
        grid_meaningful = grid_words - noise
        if csv_meaningful and grid_meaningful:
            overlap = csv_meaningful & grid_meaningful
            if not overlap:
                continue  # No word overlap at all — likely different projects

        # Guard 2: If the raw (non-normalized) names differ AND both have URLs,
        # cross-check domains to catch false positives like "Flux Protocol" ≠ "Flux Finance"
        raw_csv = re.sub(r"[^a-z0-9]", "", csv_name.lower())
        raw_grid = re.sub(r"[^a-z0-9]", "", best["name"].lower())
        if raw_csv != raw_grid:
            csv_url = row.get("Website", "").strip()
            grid_url = best.get("root_url", "")
            if csv_url and grid_url:
                csv_domain = extract_domain(csv_url)
                grid_domain = extract_domain(grid_url)
                if csv_domain and grid_domain and csv_domain != grid_domain:
                    # Names differ AND URLs differ — high risk of false positive
                    # Only allow if the names are very similar (>= 0.90 raw)
                    raw_sim = similarity(raw_csv, raw_grid)
                    if raw_sim < 0.90:
                        continue

        # Guard 3: If normalization stripped important suffixes (wallet, protocol, etc.)
        # and the raw names differ, require higher confidence
        if norm != raw_csv and raw_csv != raw_grid:
            # Normalization removed something meaningful — be extra careful
            raw_sim = similarity(raw_csv, raw_grid)
            if raw_sim < 0.85:
                continue

        results.append((row_idx, best, "batch-name", conf))

    return results


def strategy_batch_url(
    unmatched: List[Tuple[int, Dict]],
    url_index: Dict[str, List[Dict]],
) -> List[Tuple[int, Dict, str, float]]:
    """
    Strategy 2: Match CSV Website domains against Grid root domains.
    Returns list of (row_idx, grid_entry, method, confidence).
    """
    results = []
    for row_idx, row in unmatched:
        website = row.get("Website", "").strip()
        if not website:
            continue

        domain = extract_domain(website)
        if not domain or len(domain) < 4:
            continue
        if domain in EXCLUDED_DOMAINS:
            continue

        candidates = url_index.get(domain, [])
        if not candidates:
            continue

        # URL match is high confidence — but verify it's not a huge org
        # where our CSV entry is a specific product of theirs
        csv_name = row.get("Project Name", "").strip()
        best = pick_best_entry(candidates, csv_name)
        if best:
            results.append((row_idx, best, "batch-url", 0.95))

    return results


def strategy_slug(
    unmatched: List[Tuple[int, Dict]],
    client: GridAPIClient,
    already_matched: Set[int],
) -> List[Tuple[int, Dict, str, float]]:
    """
    Strategy 3: Generate candidate slugs from name and query Grid directly.
    """
    results = []

    for row_idx, row in unmatched:
        if row_idx in already_matched:
            continue

        csv_name = row.get("Project Name", "").strip()
        if not csv_name:
            continue

        # Generate slug candidates
        slugs = _generate_slugs(csv_name, row.get("Website", ""))

        for slug in slugs:
            if len(slug) < 3:
                continue

            time.sleep(REQUEST_DELAY)
            root = client.get_root_with_support(slug)
            if not root:
                continue

            pis = root.get("profileInfos", [])
            name = pis[0].get("name", slug) if pis else slug
            status_obj = pis[0].get("profileStatus", {}) if pis else {}
            status = status_obj.get("name", "") if isinstance(status_obj, dict) else ""

            entry = {
                "name": name,
                "grid_type": "profile" if pis else "root",
                "grid_id": pis[0].get("id", "") if pis else root.get("id", ""),
                "status": status,
                "root_slug": root.get("slug", slug),
                "root_url": root.get("urlMain", ""),
                "root_id": root.get("id", ""),
            }

            conf = compute_confidence(csv_name, name)
            if conf >= 0.80:  # Slightly lower threshold for slug matches
                results.append((row_idx, entry, "slug", conf))
                break  # Found one, move to next row

    return results


def strategy_twitter(
    unmatched: List[Tuple[int, Dict]],
    profiles: List[Dict],
    client: GridAPIClient,
    already_matched: Set[int],
) -> List[Tuple[int, Dict, str, float]]:
    """
    Strategy 4: Cross-reference X/Twitter handles between CSV and Grid.
    This is the most expensive strategy — only runs on remaining unmatched rows.
    """
    # Build CSV handle → row_idx lookup
    handle_to_rows: Dict[str, List[Tuple[int, Dict]]] = {}
    for row_idx, row in unmatched:
        if row_idx in already_matched:
            continue
        handle = row.get("X Handle", "").strip().lower().lstrip("@")
        if handle and len(handle) > 1:
            handle_to_rows.setdefault(handle, []).append((row_idx, row))

    if not handle_to_rows:
        return []

    # Fetch Twitter socials for all Grid roots (paginated)
    # Only fetch roots that have profiles (not orphan products)
    results = []
    seen_roots: Set[str] = set()

    for profile in profiles:
        root = profile.get("root") or {}
        root_id = root.get("id", "")
        if not root_id or root_id in seen_roots:
            continue
        seen_roots.add(root_id)

        # Fetch socials
        time.sleep(REQUEST_DELAY)
        socials = fetch_root_socials(client, root_id)
        if not socials:
            continue

        for social in socials:
            stype = (social.get("socialType") or {}).get("name", "")
            if stype != "Twitter / X":
                continue
            grid_handle = social.get("name", "").lower().lstrip("@")
            if grid_handle in handle_to_rows:
                # Match!
                for row_idx, row in handle_to_rows[grid_handle]:
                    if row_idx in already_matched:
                        continue
                    status_obj = profile.get("profileStatus") or {}
                    status = status_obj.get("name", "") if isinstance(status_obj, dict) else ""
                    entry = {
                        "name": profile.get("name", ""),
                        "grid_type": "profile",
                        "grid_id": profile.get("id", ""),
                        "status": status,
                        "root_slug": root.get("slug", ""),
                        "root_url": root.get("urlMain", ""),
                        "root_id": root_id,
                    }
                    results.append((row_idx, entry, "twitter", 0.92))
                    already_matched.add(row_idx)

        # Early exit if all handles matched
        all_matched = all(
            all(ri in already_matched for ri, _ in rows)
            for rows in handle_to_rows.values()
        )
        if all_matched:
            break

    return results


def _generate_slugs(name: str, website: str = "") -> List[str]:
    """Generate candidate Grid slugs from project name and website."""
    slugs = []

    # From name: lowercase, replace spaces with underscores
    slug1 = re.sub(r"[^a-z0-9_]", "", name.lower().replace(" ", "_").replace("-", "_"))
    slug1 = re.sub(r"_+", "_", slug1).strip("_")
    if slug1:
        slugs.append(slug1)

    # From name: hyphenated
    slug2 = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-").replace("_", "-"))
    slug2 = re.sub(r"-+", "-", slug2).strip("-")
    if slug2 and slug2 != slug1:
        slugs.append(slug2)

    # From website domain
    if website:
        domain = extract_domain(website)
        if domain:
            # e.g., "ref.finance" → "ref_finance"
            slug3 = domain.replace(".", "_").replace("-", "_")
            slug3 = re.sub(r"_+", "_", slug3).strip("_")
            if slug3 and slug3 not in slugs:
                slugs.append(slug3)
            # Also try domain without TLD
            parts = domain.split(".")
            if len(parts) >= 2:
                slug4 = parts[0]
                if slug4 and slug4 not in slugs:
                    slugs.append(slug4)

    return slugs


# ── CSV Update ─────────────────────────────────────────────────────────

def apply_match(row: Dict, entry: Dict, method: str, confidence: float) -> Dict:
    """
    Apply a Grid match to a CSV row. Returns the dict of updates.
    Follows the same column pattern as the original Grid matching.
    """
    updates = {}

    # Grid status from profile/product status
    status = entry.get("status", "")
    if status in ("Active", "Inactive", "Acquired", "Announced", "Live"):
        grid_status = status
    elif status:
        grid_status = status
    else:
        grid_status = "Found"

    updates["The Grid Status"] = grid_status
    updates["Profile Name"] = entry.get("name", "")
    updates["Root ID"] = entry.get("root_id", "")
    updates["Matched URL"] = entry.get("root_url", "")
    updates["Matched via"] = method

    # Evidence
    evidence_parts = [f"Grid: {entry['name']} ({entry['grid_type']})"]
    if entry.get("product_type"):
        evidence_parts[0] += f" [{entry['product_type']}]"
    evidence_parts.append(f"{EXPAND_MARKER}")

    existing_evidence = row.get("Evidence & Source URLs", "").strip()
    evidence_str = " | ".join(evidence_parts)
    if existing_evidence:
        updates["Evidence & Source URLs"] = f"{existing_evidence} | {evidence_str}"
    else:
        updates["Evidence & Source URLs"] = evidence_str

    return updates


# ── Main ───────────────────────────────────────────────────────────────

def expand_matches(
    csv_path: Path,
    chain: str,
    strategies: List[str],
    dry_run: bool = False,
    limit: int = 0,
) -> Tuple[int, int, int, Dict[str, int]]:
    """
    Expand Grid matches using multiple strategies.

    Returns (total_rows, unmatched_before, newly_matched, strategy_counts).
    """
    client = GridAPIClient()

    print(f"\nLoading CSV: {csv_path}")
    rows = load_csv(csv_path)
    total = len(rows)

    # Identify unmatched rows (no Grid Status AND no expand marker)
    unmatched = []
    for i, row in enumerate(rows):
        if row.get("The Grid Status", "").strip():
            continue
        if EXPAND_MARKER in row.get("Evidence & Source URLs", ""):
            continue
        # Skip rows with cleared false positive markers
        notes = row.get("Notes", "").lower()
        if "false positive" in notes and "grid match cleared" in notes:
            continue
        unmatched.append((i, row))

    print(f"  {total} total rows, {total - len(unmatched)} already matched, {len(unmatched)} unmatched")

    if limit > 0:
        unmatched = unmatched[:limit]
        print(f"  Processing first {limit} unmatched")

    if not unmatched:
        print("  No unmatched rows to process.")
        return total, 0, 0, {}

    # Phase 1: Batch download Grid data (needed for strategies 1, 2, 4)
    profiles = []
    products = []
    name_index = {}
    url_index = {}

    needs_batch = bool(set(strategies) & {"batch-name", "batch-url", "twitter"})
    if needs_batch:
        print("\n  Downloading Grid data...")
        profiles = fetch_all_profiles(client)
        print(f"    {len(profiles)} profiles fetched")
        products = fetch_all_products(client)
        print(f"    {len(products)} products fetched")

        if "batch-name" in strategies:
            name_index = build_name_index(profiles, products)
            print(f"    Name index: {len(name_index)} normalized entries")
        if "batch-url" in strategies:
            url_index = build_url_index(profiles, products)
            print(f"    URL index: {len(url_index)} domains")

    # Phase 2: Run strategies in order
    all_results: List[Tuple[int, Dict, str, float]] = []
    already_matched: Set[int] = set()
    strategy_counts: Dict[str, int] = {}

    for strat in strategies:
        print(f"\n  Strategy: {strat}")

        if strat == "batch-name":
            results = strategy_batch_name(unmatched, name_index)
        elif strat == "batch-url":
            # Filter out rows already matched by batch-name
            remaining = [(i, r) for i, r in unmatched if i not in already_matched]
            results = strategy_batch_url(remaining, url_index)
        elif strat == "slug":
            results = strategy_slug(unmatched, client, already_matched)
        elif strat == "twitter":
            results = strategy_twitter(unmatched, profiles, client, already_matched)
        else:
            print(f"    Unknown strategy: {strat}")
            continue

        # Deduplicate: keep only first match per row
        new_results = []
        for row_idx, entry, method, conf in results:
            if row_idx not in already_matched:
                new_results.append((row_idx, entry, method, conf))
                already_matched.add(row_idx)

        strategy_counts[strat] = len(new_results)
        all_results.extend(new_results)
        print(f"    → {len(new_results)} new matches")

    # Phase 3: Apply matches
    newly_matched = 0
    for row_idx, entry, method, conf in all_results:
        csv_name = rows[row_idx].get("Project Name", "")
        grid_name = entry.get("name", "")
        grid_type = entry.get("grid_type", "")

        tag = f"[DRY] " if dry_run else ""
        print(f"  {tag}{csv_name} → {grid_name} ({grid_type}, {method}, conf={conf:.2f})")

        if not dry_run:
            updates = apply_match(rows[row_idx], entry, method, conf)
            rows[row_idx].update(updates)

        newly_matched += 1

    # Write output
    if not dry_run and newly_matched > 0:
        write_csv(rows, csv_path)
        print(f"\nEnriched CSV written to: {csv_path}")

    return total, len(unmatched), newly_matched, strategy_counts


def main():
    parser = argparse.ArgumentParser(
        description="Expand Grid matching with multiple strategies"
    )
    parser.add_argument("--chain", required=True, help="Chain ID (e.g., near)")
    parser.add_argument("--csv", help="Path to CSV (auto-detected if omitted)")
    parser.add_argument(
        "--strategy", default="batch-name,batch-url,slug",
        help=f"Comma-separated strategies to run (default: batch-name,batch-url,slug). "
             f"Available: {', '.join(ALL_STRATEGIES)}"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview matches without writing")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only first N unmatched rows (for testing)")
    args = parser.parse_args()

    # Resolve CSV
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

    strategies = [s.strip() for s in args.strategy.split(",")]
    for s in strategies:
        if s not in ALL_STRATEGIES:
            print(f"Error: Unknown strategy '{s}'. Available: {', '.join(ALL_STRATEGIES)}")
            sys.exit(1)

    total, unmatched, matched, counts = expand_matches(
        csv_path, args.chain, strategies,
        dry_run=args.dry_run, limit=args.limit,
    )

    print(f"\n{'='*60}")
    print(f"GRID MATCH EXPANSION SUMMARY")
    print(f"{'='*60}")
    print(f"Total rows:       {total}")
    print(f"Unmatched before: {unmatched}")
    print(f"Newly matched:    {matched}")
    for strat, count in counts.items():
        print(f"  {strat}: {count}")
    print(f"Match rate:       {(total - unmatched + matched)}/{total} "
          f"({100*(total - unmatched + matched)/total:.1f}%)")

    if args.dry_run:
        print(f"\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
