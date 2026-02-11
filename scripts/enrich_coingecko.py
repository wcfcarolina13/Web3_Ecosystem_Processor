#!/usr/bin/env python3
"""
Enrich ecosystem CSV with asset support data from CoinGecko.

Uses the CoinGecko /search and /coins/{id} endpoints to determine:
1. Which chains a project's token is deployed on (platforms field)
2. Which assets it trades against on exchanges (tickers field)

This provides a different signal than DefiLlama's TVL-based token holdings:
- DefiLlama: "this protocol holds $X of USDT in its contracts"
- CoinGecko: "this project's token trades against USDT on exchanges"
                "this project is deployed on Solana/Starknet/Cardano"

Usage:
    python scripts/enrich_coingecko.py --chain avalanche --csv path/to/scrape.csv
    python scripts/enrich_coingecko.py --chain avalanche --csv path/to/scrape.csv --dry-run
    python scripts/enrich_coingecko.py --chain avalanche --csv path/to/scrape.csv --limit 20
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.columns import CORRECT_COLUMNS
from lib.csv_utils import load_csv, write_csv, find_main_csv, resolve_data_path


# ── CoinGecko API ────────────────────────────────────────────────────────

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
SEARCH_URL = f"{COINGECKO_BASE}/search?query={{query}}"
COIN_URL = f"{COINGECKO_BASE}/coins/{{id}}?tickers=true&market_data=false&community_data=false&developer_data=false&sparkline=false"

# Rate limiting: CoinGecko free = 5-15 calls/min (public), 30/min (demo)
# We use 5s between requests (~12 calls/min) for reliable free-tier usage
# Each project = 2 calls (search + detail), so ~6 projects/min
REQUEST_DELAY = 5.0
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

# Ticker symbols that indicate target asset trading pairs
TICKER_TARGETS = {
    "USDT": {"USDT"},
    "USDC": {"USDC"},
    "SOL": {"SOL", "WSOL"},
    "STRK": {"STRK"},
    "ADA": {"ADA", "WADA"},
}

# Stablecoin asset keys
STABLECOIN_KEYS = {"USDT", "USDC"}


def fetch_json(url: str, retries: int = MAX_RETRIES) -> Optional[dict]:
    """Fetch JSON from URL with retry and backoff."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "EcosystemResearch/1.0",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = RETRY_BACKOFF * (2 ** attempt)
                print(f" [rate limited, waiting {wait:.0f}s]", end="", flush=True)
                time.sleep(wait)
                continue
            elif e.code == 404:
                return None
            else:
                if attempt < retries - 1:
                    time.sleep(RETRY_BACKOFF)
                    continue
                print(f" Error {e.code}: {e.reason}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(RETRY_BACKOFF)
                continue
            print(f" Error: {e}")
            return None
    return None


# ── CoinGecko matching ───────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """Normalize a project name for matching."""
    return name.strip().lower().replace("-", " ").replace("_", " ")


def strip_suffixes(name: str) -> str:
    """Strip common suffixes like 'DEX', 'Protocol', 'Finance', 'Exchange' for search."""
    suffixes = ["dex", "protocol", "finance", "exchange", "network", "swap", "bridge", "labs"]
    words = name.lower().split()
    if len(words) > 1 and words[-1] in suffixes:
        return " ".join(words[:-1])
    return name


def find_coingecko_id(project_name: str) -> Optional[str]:
    """
    Search CoinGecko for a project and return the best matching coin ID.
    Returns None if no good match found.
    """
    query = project_name.strip()
    if len(query) < 2:
        return None

    url = SEARCH_URL.format(query=urllib.request.quote(query))
    data = fetch_json(url)
    if not data:
        return None

    coins = data.get("coins", [])
    if not coins:
        # Try again with stripped suffix (e.g., "Thorchain DEX" → "Thorchain")
        stripped = strip_suffixes(query)
        if stripped.lower() != query.lower():
            time.sleep(REQUEST_DELAY)
            url = SEARCH_URL.format(query=urllib.request.quote(stripped))
            data = fetch_json(url)
            if data:
                coins = data.get("coins", [])
        if not coins:
            return None

    # Try exact name match first (case-insensitive)
    norm_query = normalize_name(project_name)
    norm_stripped = normalize_name(strip_suffixes(project_name))
    for coin in coins:
        coin_norm = normalize_name(coin.get("name", ""))
        if coin_norm == norm_query or coin_norm == norm_stripped:
            return coin["id"]

    # Try first result only if it's a close match
    first = coins[0]
    first_norm = normalize_name(first.get("name", ""))

    # Require the core name to appear in the CoinGecko name or vice versa
    # AND the names should be similar length (avoid "Securitize" → "Apollo Securitize Fund")
    if first_norm == norm_query or first_norm == norm_stripped:
        return first["id"]

    # Accept if one contains the other AND lengths are close
    if (norm_stripped in first_norm or first_norm in norm_stripped):
        len_ratio = min(len(first_norm), len(norm_stripped)) / max(len(first_norm), len(norm_stripped), 1)
        if len_ratio > 0.5:
            return first["id"]

    return None


# ── Asset detection ──────────────────────────────────────────────────────

def detect_platform_assets(
    platforms: dict, target_assets: List[str]
) -> Dict[str, str]:
    """
    Check which target assets are implied by platform deployments.
    E.g., if deployed on "solana" → suggests SOL support.

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


def detect_ticker_assets(
    tickers: list, target_assets: List[str]
) -> Dict[str, Set[str]]:
    """
    Scan exchange tickers for trading pairs involving target assets.
    E.g., CAKE/USDT on Binance → USDT detected.

    Returns dict of {asset: set_of_exchange_names}.
    """
    findings: Dict[str, Set[str]] = {}
    for ticker in tickers:
        base = (ticker.get("base") or "").upper()
        target = (ticker.get("target") or "").upper()
        market_name = ticker.get("market", {}).get("name", "unknown")

        for asset, symbols in TICKER_TARGETS.items():
            if asset not in target_assets:
                continue
            if base in symbols or target in symbols:
                if asset not in findings:
                    findings[asset] = set()
                findings[asset].add(market_name)
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
    Enrich an ecosystem CSV with CoinGecko platform/ticker data.

    Returns (total_rows, cg_matches, enriched_rows).
    """
    # Load CSV
    print(f"\nLoading CSV: {csv_path}")
    rows = load_csv(csv_path)
    total = len(rows)
    if limit > 0:
        rows = rows[:limit]
        print(f"  Processing first {limit} of {total} rows")
    else:
        print(f"  {total} rows to process")

    cg_matched = 0
    enriched = 0
    output_rows = []

    for i, row in enumerate(rows):
        name = row.get("Project Name", "").strip()
        if not name:
            output_rows.append(row)
            continue

        print(f"  [{i+1}/{len(rows)}] {name}", end="", flush=True)

        # Rate limit
        if i > 0:
            time.sleep(REQUEST_DELAY)

        # Search CoinGecko
        coin_id = find_coingecko_id(name)
        if not coin_id:
            print(" → not found")
            output_rows.append(row)
            continue

        cg_matched += 1

        # Fetch coin detail (second API call = need another delay)
        time.sleep(REQUEST_DELAY)
        coin_data = fetch_json(COIN_URL.format(id=coin_id))
        if not coin_data:
            print(f" → {coin_id} (no detail)")
            output_rows.append(row)
            continue

        # Detect assets from platforms and tickers
        platforms = coin_data.get("platforms", {})
        tickers = coin_data.get("tickers", [])

        platform_findings = detect_platform_assets(platforms, target_assets)
        ticker_findings = detect_ticker_assets(tickers, target_assets)

        # Merge findings
        all_detected = set(platform_findings.keys()) | set(ticker_findings.keys())

        if not all_detected:
            print(f" → {coin_id} (no target assets)")
            output_rows.append(row)
            continue

        enriched += 1

        # Build updates
        updates = {}

        # Stablecoin heuristic columns
        has_usdt = "USDT" in all_detected
        has_usdc = "USDC" in all_detected
        has_any_stablecoin = has_usdt or has_usdc

        if has_any_stablecoin:
            updates["Suspect USDT support?"] = "TRUE"
            updates["Web3 but no stablecoin"] = ""
            if has_usdt and has_usdc:
                updates["General Stablecoin Adoption"] = "TRUE"
        else:
            if not row.get("Suspect USDT support?"):
                updates["Web3 but no stablecoin"] = "TRUE"

        # Build evidence: what we found and where
        evidence_parts = []
        for asset in target_assets:
            parts = []
            if asset in ticker_findings:
                exchanges = ticker_findings[asset]
                top_exchanges = sorted(exchanges)[:3]
                parts.append(f"traded on {', '.join(top_exchanges)}")
            if asset in platform_findings:
                parts.append(platform_findings[asset])
            if parts:
                evidence_parts.append(f"{asset}: {'; '.join(parts)}")

        if evidence_parts:
            evidence = " | ".join(evidence_parts)
            existing = row.get("Evidence URLs", "").strip()
            if existing:
                updates["Evidence URLs"] = f"{existing} | {evidence}"
            else:
                updates["Evidence URLs"] = evidence

        # Build notes
        note_findings = []
        if has_usdt and has_usdc:
            note_findings.append("Trades against USDT + USDC")
        elif has_usdt:
            note_findings.append("Trades against USDT")
        elif has_usdc:
            note_findings.append("Trades against USDC only")

        has_sol = "SOL" in all_detected
        has_strk = "STRK" in all_detected
        has_ada = "ADA" in all_detected

        if has_sol:
            note_findings.append("Solana presence")
        if has_strk:
            note_findings.append("Starknet presence")
        if has_ada:
            note_findings.append("Cardano presence")

        if note_findings:
            finding_text = "; ".join(note_findings)
            existing_notes = row.get("Notes", "").strip()
            if existing_notes:
                if finding_text not in existing_notes:
                    updates["Notes"] = f"{existing_notes} | {finding_text}"
            else:
                updates["Notes"] = finding_text

        # Update source to include CoinGecko
        existing_source = row.get("Source", "").strip()
        if "CoinGecko" not in existing_source:
            if existing_source:
                updates["Source"] = f"{existing_source}, CoinGecko"
            else:
                updates["Source"] = "CoinGecko"

        # Console output
        status_parts = []
        for asset in sorted(all_detected):
            if asset in ticker_findings:
                status_parts.append(f"{asset}(ticker)")
            elif asset in platform_findings:
                status_parts.append(f"{asset}(platform)")
        print(f" → {coin_id} ✓ {', '.join(status_parts)}")

        if not dry_run:
            row.update(updates)

        output_rows.append(row)

    # Write output
    if not dry_run and enriched > 0:
        suffix = "_cg_enriched" if "_enriched" not in csv_path.stem else "_cg"
        output_path = csv_path.with_name(csv_path.stem + suffix + ".csv")
        write_csv(output_rows, output_path)
        print(f"\nEnriched CSV written to: {output_path}")
    elif dry_run:
        print("\n[DRY RUN] No files written.")

    return total, cg_matched, enriched


def main():
    parser = argparse.ArgumentParser(
        description="Enrich ecosystem CSV with CoinGecko platform/ticker data"
    )
    parser.add_argument(
        "--chain", required=True, help="Chain ID (e.g., avalanche, aptos)"
    )
    parser.add_argument(
        "--csv", help="Path to CSV (auto-detected from data/<chain>/ if omitted)"
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Comma-separated target assets (default: from chains.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview enrichment without writing files",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process only first N rows (for testing)",
    )
    args = parser.parse_args()

    # Resolve target assets
    chain_config = load_chain_config(args.chain)
    if args.assets:
        target_assets = [a.strip() for a in args.assets.split(",")]
    else:
        target_assets = chain_config.get("target_assets", ["USDT", "USDC"])
    # Always include USDC for stablecoin detection
    if "USDC" not in target_assets:
        target_assets.append("USDC")

    # Exclude USDC from gap analysis targets (same as grid_match.py logic)
    gap_targets = [a for a in target_assets if a != "USDC"]
    print(f"Target assets: {gap_targets} (+ USDC for stablecoin detection)")
    print(f"Chain: {args.chain}")
    print(f"Rate: 1 request per {REQUEST_DELAY}s (~{60/REQUEST_DELAY:.0f} calls/min)")

    # Resolve CSV path
    if args.csv:
        csv_path = Path(args.csv)
    else:
        data_dir = resolve_data_path(args.chain)
        csv_path = find_main_csv(data_dir)
        if not csv_path:
            print(f"Error: No CSV found in {data_dir}")
            sys.exit(1)

    if not csv_path.exists():
        print(f"Error: CSV not found: {csv_path}")
        sys.exit(1)

    total, cg_matched, enriched = enrich_csv(
        csv_path, args.chain, target_assets,
        dry_run=args.dry_run, limit=args.limit,
    )

    print(f"\n{'='*60}")
    print(f"COINGECKO ENRICHMENT SUMMARY")
    print(f"{'='*60}")
    print(f"Total rows:       {total}")
    print(f"CoinGecko matches: {cg_matched}")
    print(f"Enriched:         {enriched}")
    print(f"Target assets:    {', '.join(gap_targets)}")


if __name__ == "__main__":
    main()
