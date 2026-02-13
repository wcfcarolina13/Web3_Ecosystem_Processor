#!/usr/bin/env python3
"""
Build a cached stablecoin catalog from CoinGecko's free API.

Fetches the stablecoins category, filters by market cap, and saves
a local catalog that enrich_website_keywords.py uses for dynamic
stablecoin detection beyond just USDT/USDC.

USDT and USDC are excluded from the catalog — they are hardcoded in the
website scanner and gated by target_assets. This catalog covers "other"
stablecoins: DAI, TUSD, FRAX, PYUSD, etc.

Usage:
    python scripts/build_stablecoin_catalog.py              # Fetch and save
    python scripts/build_stablecoin_catalog.py --force       # Force refresh
    python scripts/build_stablecoin_catalog.py --dry-run     # Preview only
    python scripts/build_stablecoin_catalog.py --min-market-cap 5000000
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# ── Constants ────────────────────────────────────────────────────────

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
STABLECOINS_URL = (
    f"{COINGECKO_BASE}/coins/markets"
    f"?vs_currency=usd&category=stablecoins&per_page=250&order=market_cap_desc"
)

DEFAULT_MIN_MARKET_CAP = 1_000_000  # $1M floor
DEFAULT_MAX_AGE_DAYS = 7
MIN_SYMBOL_LENGTH = 3  # Skip symbols < 3 chars (too many false positives)

# Exclude from catalog — these are hardcoded in enrich_website_keywords.py
EXCLUDED_SYMBOLS = {"USDT", "USDC"}

# Rate limiting
MAX_RETRIES = 3
RETRY_BACKOFF = 5.0

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "config" / "stablecoin_catalog.json"


# ── HTTP helper ──────────────────────────────────────────────────────

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


# ── Catalog building ─────────────────────────────────────────────────

def build_keywords_for_coin(symbol: str, name: str) -> List[str]:
    """
    Generate search keywords for a stablecoin.

    Rules:
    - Always include the symbol lowercased (e.g., "dai", "frax")
    - If the full name differs from the symbol and is >5 chars, include it lowercased
    - Skip symbols shorter than MIN_SYMBOL_LENGTH
    """
    if len(symbol) < MIN_SYMBOL_LENGTH:
        return []

    keywords = [symbol.lower()]

    # Add full name if it provides additional signal
    name_lower = name.lower()
    if name_lower != symbol.lower() and len(name_lower) > 5:
        keywords.append(name_lower)

    return keywords


def fetch_stablecoin_markets(min_market_cap: int = DEFAULT_MIN_MARKET_CAP) -> List[Dict]:
    """
    Fetch CoinGecko stablecoins category, filter, and return cleaned list.

    Returns list of dicts with: symbol, name, market_cap, keywords.
    """
    print(f"Fetching CoinGecko stablecoins category...")
    data = fetch_json(STABLECOINS_URL)

    if not data:
        print("  Failed to fetch stablecoin data from CoinGecko.")
        return []

    print(f"  Raw response: {len(data)} coins")

    results = []
    skipped_excluded = 0
    skipped_mcap = 0
    skipped_short = 0

    for coin in data:
        symbol = (coin.get("symbol") or "").upper()
        name = coin.get("name") or ""
        market_cap = coin.get("market_cap") or 0

        # Exclude USDT/USDC — they have their own hardcoded path
        if symbol in EXCLUDED_SYMBOLS:
            skipped_excluded += 1
            continue

        # Market cap floor
        if market_cap < min_market_cap:
            skipped_mcap += 1
            continue

        # Generate keywords
        keywords = build_keywords_for_coin(symbol, name)
        if not keywords:
            skipped_short += 1
            continue

        results.append({
            "symbol": symbol,
            "name": name,
            "market_cap": market_cap,
            "keywords": keywords,
        })

    print(f"  Filtered: {len(results)} stablecoins kept")
    if skipped_excluded:
        print(f"  Excluded: {skipped_excluded} (USDT/USDC)")
    if skipped_mcap:
        print(f"  Below ${min_market_cap:,} market cap: {skipped_mcap}")
    if skipped_short:
        print(f"  Symbol too short (<{MIN_SYMBOL_LENGTH} chars): {skipped_short}")

    return results


def build_catalog(min_market_cap: int = DEFAULT_MIN_MARKET_CAP) -> Optional[Dict]:
    """Fetch, filter, and structure the catalog dict."""
    stablecoins = fetch_stablecoin_markets(min_market_cap)

    if not stablecoins:
        return None

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "CoinGecko /coins/markets?category=stablecoins",
        "count": len(stablecoins),
        "min_market_cap_usd": min_market_cap,
        "stablecoins": stablecoins,
    }


def save_catalog(catalog: Dict, path: Path) -> None:
    """Write catalog JSON to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(catalog, f, indent=2)
    print(f"  Catalog saved: {path} ({catalog['count']} stablecoins)")


def load_catalog(
    path: Path,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> Optional[Dict]:
    """
    Load catalog from disk. Returns None if missing or stale.

    Args:
        path: Path to the catalog JSON file.
        max_age_days: Maximum age in days before catalog is considered stale.
            Use 0 to always consider stale (force refresh).
    """
    if not path.exists():
        return None

    try:
        with open(path) as f:
            catalog = json.load(f)
    except (json.JSONDecodeError, KeyError):
        return None

    # Check freshness
    fetched_at = catalog.get("fetched_at", "")
    if not fetched_at:
        return None

    try:
        fetched_dt = datetime.fromisoformat(fetched_at)
        age_days = (datetime.now(timezone.utc) - fetched_dt).days
        if max_age_days > 0 and age_days <= max_age_days:
            return catalog
        else:
            print(f"  Catalog is {age_days} days old (max: {max_age_days})")
            return None
    except (ValueError, TypeError):
        return None


def ensure_catalog(
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    min_market_cap: int = DEFAULT_MIN_MARKET_CAP,
) -> Dict:
    """
    Load catalog if fresh, else fetch and save. Main entry point for other scripts.

    Returns the catalog dict. Returns empty catalog structure if fetch fails
    and no cached version exists.
    """
    cached = load_catalog(catalog_path, max_age_days)
    if cached:
        print(f"  Stablecoin catalog: {cached['count']} entries (cached)")
        return cached

    catalog = build_catalog(min_market_cap)
    if catalog:
        save_catalog(catalog, catalog_path)
        return catalog

    # Fallback: try loading stale cache
    if catalog_path.exists():
        try:
            with open(catalog_path) as f:
                stale = json.load(f)
            print(f"  Using stale catalog: {stale.get('count', 0)} entries")
            return stale
        except (json.JSONDecodeError, KeyError):
            pass

    # No catalog available at all
    return {"fetched_at": "", "source": "", "count": 0, "stablecoins": []}


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build stablecoin catalog from CoinGecko API"
    )
    parser.add_argument("--force", action="store_true",
                        help="Force refresh regardless of cache age")
    parser.add_argument("--min-market-cap", type=int,
                        default=DEFAULT_MIN_MARKET_CAP,
                        help=f"Minimum market cap in USD (default: ${DEFAULT_MIN_MARKET_CAP:,})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview catalog without saving")
    parser.add_argument("--catalog-path", type=str,
                        default=str(DEFAULT_CATALOG_PATH),
                        help="Path to catalog file")
    args = parser.parse_args()

    catalog_path = Path(args.catalog_path)

    if not args.force and not args.dry_run:
        cached = load_catalog(catalog_path)
        if cached:
            print(f"Catalog is fresh ({cached['count']} stablecoins, "
                  f"fetched {cached['fetched_at']})")
            print("Use --force to refresh.")
            return

    print("Building stablecoin catalog from CoinGecko...")
    catalog = build_catalog(args.min_market_cap)

    if not catalog:
        print("Failed to build catalog.")
        sys.exit(1)

    print(f"\nCatalog: {catalog['count']} stablecoins")
    print(f"Top 20 by market cap:")
    for coin in catalog["stablecoins"][:20]:
        mcap = coin["market_cap"]
        kws = ", ".join(coin["keywords"])
        print(f"  {coin['symbol']:>10s}  ${mcap:>15,.0f}  keywords: [{kws}]")

    remaining = catalog["count"] - 20
    if remaining > 0:
        print(f"  ... and {remaining} more")

    if not args.dry_run:
        save_catalog(catalog, catalog_path)
    else:
        print("\n[DRY RUN] Catalog not saved.")


if __name__ == "__main__":
    main()
