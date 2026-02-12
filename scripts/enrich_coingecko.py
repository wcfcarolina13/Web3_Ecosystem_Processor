#!/usr/bin/env python3
"""
Enrich ecosystem CSV with chain deployment data from CoinGecko.

Uses the CoinGecko /coins/list?include_platform=true endpoint to batch-fetch
ALL tokens with their chain deployments in a single call. Then matches CSV
project names against the cached catalog for O(1) lookups per row.

This replaces the slow per-project search+detail approach (~10s/project)
with a fast batch strategy (~2-3 min total for any CSV size).

Detects:
- Platform deployments: token deployed on Solana/Starknet/Cardano → implies asset support

Usage:
    python scripts/enrich_coingecko.py --chain near
    python scripts/enrich_coingecko.py --chain near --dry-run --limit 20
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.columns import CORRECT_COLUMNS
from lib.csv_utils import load_csv, write_csv, find_main_csv


# ── CoinGecko API ────────────────────────────────────────────────────────

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
COINS_LIST_URL = f"{COINGECKO_BASE}/coins/list?include_platform=true"

# Rate limiting: CoinGecko free = 10-30 calls/min
REQUEST_DELAY = 3.0
MAX_RETRIES = 3
RETRY_BACKOFF = 5.0


# ── Platform name mapping ────────────────────────────────────────────────
# Maps CoinGecko platform keys to our target asset tickers

PLATFORM_TO_ASSET = {
    "solana": "SOL",
    "starknet": "STRK",
    "starknet-alpha": "STRK",
    "cardano": "ADA",
}

# Stablecoin asset keys
STABLECOIN_KEYS = {"USDT", "USDC"}


def fetch_json(url: str, retries: int = MAX_RETRIES) -> Optional[list]:
    """Fetch JSON from URL with retry and backoff."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "EcosystemResearch/1.0",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = RETRY_BACKOFF * (2 ** attempt)
                print(f"  [rate limited, waiting {wait:.0f}s]", flush=True)
                time.sleep(wait)
                continue
            elif e.code == 404:
                return None
            else:
                if attempt < retries - 1:
                    time.sleep(RETRY_BACKOFF)
                    continue
                print(f"  Error {e.code}: {e.reason}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(RETRY_BACKOFF)
                continue
            print(f"  Error: {e}")
            return None
    return None


# ── Batch catalog ────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """Normalize a project name for matching."""
    return re.sub(r"[^a-z0-9 ]", "", name.strip().lower().replace("-", " ").replace("_", " "))


def strip_suffixes(name: str) -> str:
    """Strip common suffixes for matching."""
    suffixes = {"dex", "protocol", "finance", "exchange", "network",
                "swap", "bridge", "labs", "dao", "wallet", "amm"}
    words = name.lower().split()
    if len(words) > 1 and words[-1] in suffixes:
        return " ".join(words[:-1])
    return name


def build_coin_catalog() -> Dict[str, dict]:
    """
    Fetch full CoinGecko coins list with platform data.
    Returns dict mapping normalized name/symbol → coin entry.
    """
    print("  Fetching CoinGecko coins list (this may take a moment)...", flush=True)
    data = fetch_json(COINS_LIST_URL)
    if not data:
        print("  ERROR: Failed to fetch CoinGecko coins list")
        return {}

    print(f"  Fetched {len(data)} coins from CoinGecko")

    # Build lookup by normalized name and symbol
    catalog = {}
    for coin in data:
        name = coin.get("name", "")
        symbol = coin.get("symbol", "")
        platforms = coin.get("platforms", {})

        # Skip coins with no platform data
        if not platforms or not any(v for v in platforms.values()):
            continue

        entry = {
            "id": coin.get("id", ""),
            "name": name,
            "symbol": symbol,
            "platforms": platforms,
        }

        # Index by normalized name
        norm = normalize_name(name)
        if norm and norm not in catalog:
            catalog[norm] = entry

        # Also index by stripped-suffix name
        stripped = normalize_name(strip_suffixes(name))
        if stripped and stripped != norm and stripped not in catalog:
            catalog[stripped] = entry

        # Index by symbol (lower priority — more ambiguous)
        sym_norm = symbol.strip().lower()
        if sym_norm and len(sym_norm) >= 3 and sym_norm not in catalog:
            catalog[sym_norm] = entry

    print(f"  Built catalog with {len(catalog)} lookup entries")
    return catalog


def find_coin_in_catalog(
    project_name: str,
    catalog: Dict[str, dict],
    catalog_keys: Optional[List[str]] = None,
    fuzzy_threshold: float = 0.90,
) -> Optional[tuple]:
    """
    Look up a project in the cached CoinGecko catalog.

    Returns (coin_dict, match_method) or None.
    match_method is "exact" for O(1) lookups, "fuzzy" for SequenceMatcher matches.
    """
    from difflib import get_close_matches

    # Try exact normalized name
    norm = normalize_name(project_name)
    if norm in catalog:
        return catalog[norm], "exact"

    # Try stripped suffix
    stripped = normalize_name(strip_suffixes(project_name))
    if stripped in catalog:
        return catalog[stripped], "exact"

    # Try first part before common separators (handles "RuneMine | Mine Labs")
    for sep in [" | ", " - ", " / "]:
        if sep in project_name:
            first_part = project_name.split(sep)[0].strip()
            first_norm = normalize_name(first_part)
            if first_norm and first_norm in catalog:
                return catalog[first_norm], "exact"

    # Fuzzy fallback — only if catalog_keys provided
    # Crypto names are notoriously similar (Bitget/Bitgert, Binance/bAInance)
    # so false positives are common. We use a high threshold and mark results
    # clearly as fuzzy so researchers can verify.
    if catalog_keys and norm and len(norm) >= 7:
        matches = get_close_matches(norm, catalog_keys, n=1, cutoff=max(fuzzy_threshold, 0.90))
        if matches:
            matched_key = matches[0]
            # Guard: require similar length
            len_ratio = min(len(norm), len(matched_key)) / max(len(norm), len(matched_key))
            if len_ratio >= 0.75:
                return catalog[matched_key], "fuzzy"

    return None


# ── Asset detection ──────────────────────────────────────────────────────

def detect_platform_assets(
    platforms: dict, target_assets: List[str]
) -> Dict[str, str]:
    """
    Check which target assets are implied by platform deployments.
    Returns dict of {asset: evidence_string}.
    """
    findings = {}
    for platform_key, contract in platforms.items():
        if not contract:
            continue
        platform_lower = platform_key.lower()
        asset = PLATFORM_TO_ASSET.get(platform_lower)
        if asset and asset in target_assets:
            findings[asset] = f"deployed on {platform_key}"
    return findings


# ── Enrichment ───────────────────────────────────────────────────────────

def load_chain_config(chain_id: str) -> dict:
    """Load chain config from chains.json."""
    config_path = Path(__file__).parent.parent / "config" / "chains.json"
    if not config_path.exists():
        return {}
    with open(config_path, "r") as f:
        data = json.load(f)
    for chain in data.get("chains", []):
        if chain["id"] == chain_id:
            return chain
    return {}


def enrich_csv(
    csv_path: Path,
    chain: str,
    target_assets: List[str],
    dry_run: bool = False,
    limit: int = 0,
) -> Tuple[int, int, int]:
    """
    Enrich an ecosystem CSV with CoinGecko platform data.
    Returns (total_rows, cg_matches, enriched_rows).
    """
    # Build catalog (single API call)
    catalog = build_coin_catalog()
    if not catalog:
        print("ERROR: Empty catalog, aborting.")
        return 0, 0, 0

    # Pre-compute catalog keys list for fuzzy matching
    catalog_keys = list(catalog.keys())

    # Load CSV
    print(f"\nLoading CSV: {csv_path}")
    rows = load_csv(csv_path)
    total = len(rows)
    process_rows = rows[:limit] if limit > 0 else rows
    print(f"  {total} rows total, processing {len(process_rows)}")

    cg_matched = 0
    enriched = 0
    skipped_incremental = 0

    for i, row in enumerate(process_rows):
        name = row.get("Project Name", "").strip()
        if not name:
            continue

        # Incremental: skip rows already enriched by CoinGecko
        if "CoinGecko" in row.get("Evidence & Source URLs", ""):
            skipped_incremental += 1
            continue

        # O(1) lookup (exact) or fuzzy fallback
        result = find_coin_in_catalog(name, catalog, catalog_keys=catalog_keys)
        if not result:
            continue

        coin, match_method = result
        cg_matched += 1

        # Detect platform assets
        platforms = coin.get("platforms", {})
        platform_findings = detect_platform_assets(platforms, target_assets)

        if not platform_findings:
            continue

        enriched += 1
        all_detected = set(platform_findings.keys())
        is_fuzzy = match_method == "fuzzy"

        # Build updates
        updates = {}

        if is_fuzzy:
            # ── FUZZY MATCH: write ONLY to Notes as unverified hint ──
            # Do NOT touch Evidence, asset columns, or Source.
            # Researchers can verify and promote to high-confidence data.
            asset_list = ", ".join(sorted(all_detected))
            fuzzy_hint = (
                f"[UNVERIFIED] CoinGecko fuzzy match: \"{coin['name']}\" "
                f"({coin['id']}) — {asset_list} deployment detected"
            )
            existing_notes = row.get("Notes", "").strip()
            if existing_notes:
                if "CoinGecko fuzzy" not in existing_notes:
                    updates["Notes"] = f"{existing_notes} | {fuzzy_hint}"
            else:
                updates["Notes"] = fuzzy_hint

        else:
            # ── EXACT MATCH: write to all high-confidence columns ──

            # Build evidence
            evidence_parts = []
            for asset in target_assets:
                if asset in platform_findings:
                    evidence_parts.append(f"{asset}: {platform_findings[asset]} (CoinGecko)")

            if evidence_parts:
                evidence = " | ".join(evidence_parts)
                existing = row.get("Evidence & Source URLs", "").strip()
                if existing:
                    if "CoinGecko" not in existing:
                        updates["Evidence & Source URLs"] = f"{existing} | {evidence}"
                else:
                    updates["Evidence & Source URLs"] = evidence

            # Build notes
            note_findings = []
            if "SOL" in all_detected:
                note_findings.append("Solana deployment (CoinGecko)")
            if "STRK" in all_detected:
                note_findings.append("Starknet deployment (CoinGecko)")
            if "ADA" in all_detected:
                note_findings.append("Cardano deployment (CoinGecko)")

            if note_findings:
                finding_text = "; ".join(note_findings)
                existing_notes = row.get("Notes", "").strip()
                if existing_notes:
                    if finding_text not in existing_notes and "CoinGecko" not in existing_notes:
                        updates["Notes"] = f"{existing_notes} | {finding_text}"
                else:
                    updates["Notes"] = finding_text

            # Update source to include CoinGecko (exact matches only)
            existing_source = row.get("Source", "").strip()
            if "CoinGecko" not in existing_source:
                if existing_source:
                    updates["Source"] = f"{existing_source}; CoinGecko"
                else:
                    updates["Source"] = "CoinGecko"

        match_label = f" [fuzzy]" if is_fuzzy else ""
        print(f"  {name} -> {coin['name']} ({coin['id']}): {', '.join(sorted(all_detected))}{match_label}")

        if not dry_run:
            row.update(updates)

    if skipped_incremental > 0:
        print(f"\n  Skipped {skipped_incremental} already-enriched rows (incremental)")

    # Write output (in-place for pipeline composability)
    if not dry_run and enriched > 0:
        write_csv(rows, csv_path)
        print(f"\nEnriched CSV written to: {csv_path}")
    elif dry_run:
        print("\n[DRY RUN] No files written.")

    return total, cg_matched, enriched


def main():
    parser = argparse.ArgumentParser(
        description="Enrich ecosystem CSV with CoinGecko platform deployment data"
    )
    parser.add_argument(
        "--chain", required=True, help="Chain ID (e.g., near, aptos)"
    )
    parser.add_argument(
        "--csv", help="Path to CSV (auto-detected from data/<chain>/ if omitted)"
    )
    parser.add_argument(
        "--assets", default=None,
        help="Comma-separated target assets (default: from chains.json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview enrichment without writing files",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Process only first N rows (for testing)",
    )
    args = parser.parse_args()

    # Resolve target assets
    chain_config = load_chain_config(args.chain)
    if args.assets:
        target_assets = [a.strip() for a in args.assets.split(",")]
    else:
        target_assets = chain_config.get("target_assets", ["USDT", "USDC", "SOL", "STRK", "ADA"])

    # Filter to chain-relevant assets for CoinGecko
    # CoinGecko platform detection is only useful for SOL/STRK/ADA (chain deployments)
    cg_targets = [a for a in target_assets if a in ("SOL", "STRK", "ADA")]
    if not cg_targets:
        print("No CoinGecko-detectable assets in target list (SOL, STRK, ADA)")
        sys.exit(0)

    print(f"Target assets (CoinGecko platform detection): {cg_targets}")
    print(f"Chain: {args.chain}")

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

    total, cg_matched, enriched = enrich_csv(
        csv_path, args.chain, cg_targets,
        dry_run=args.dry_run, limit=args.limit,
    )

    print(f"\n{'='*60}")
    print(f"COINGECKO ENRICHMENT SUMMARY")
    print(f"{'='*60}")
    print(f"Total rows:        {total}")
    print(f"CoinGecko matches: {cg_matched}")
    print(f"Enriched:          {enriched}")
    print(f"Target assets:     {', '.join(cg_targets)}")

    if args.dry_run:
        print("\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
