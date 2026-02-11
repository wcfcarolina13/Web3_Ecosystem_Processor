#!/usr/bin/env python3
"""
Enrich ecosystem CSV with per-protocol asset support data from DefiLlama.

Queries the DefiLlama /protocol/{slug} endpoint for each project that has a
DefiLlama slug, extracts token holdings for target assets (USDT, USDC, SOL,
STRK, ADA, etc.), and populates stablecoin heuristic columns + notes.

Usage:
    python scripts/enrich_assets.py --chain aptos
    python scripts/enrich_assets.py --chain aptos --csv data/aptos/aptos_usdt_ecosystem_research.csv
    python scripts/enrich_assets.py --chain aptos --dry-run
    python scripts/enrich_assets.py --chain aptos --assets USDT,USDC,APT
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.columns import CORRECT_COLUMNS
from lib.csv_utils import load_csv, write_csv, find_main_csv, resolve_data_path


# ── DefiLlama API ──────────────────────────────────────────────────────────

DEFILLAMA_PROTOCOLS_URL = "https://api.llama.fi/protocols"
DEFILLAMA_PROTOCOL_URL = "https://api.llama.fi/protocol/{slug}"

# Rate limiting: polite 2 requests/sec with retry on 429
REQUEST_DELAY = 0.5  # seconds between requests
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # exponential backoff base


def fetch_json(url: str, retries: int = MAX_RETRIES) -> Optional[dict]:
    """Fetch JSON from URL with retry and backoff."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "EcosystemResearch/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = RETRY_BACKOFF ** (attempt + 1)
                print(f"  Rate limited (429), waiting {wait:.0f}s...")
                time.sleep(wait)
                continue
            elif e.code == 404:
                return None
            else:
                print(f"  HTTP {e.code} fetching {url}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(RETRY_BACKOFF)
                continue
            print(f"  Error fetching {url}: {e}")
            return None
    return None


# ── Token symbol matching ──────────────────────────────────────────────────

# Common aliases for target assets across different chains
TOKEN_ALIASES = {
    "USDT": {"USDT", "USDT.e", "USDt", "USDT.b", "BUSDT", "fUSDT", "ceUSDT",
             "axlUSDT", "multiUSDT", "whUSDT", "zUSDT", "madUSDT", "tUSDT"},
    "USDC": {"USDC", "USDC.e", "axlUSDC", "multiUSDC", "whUSDC", "ceUSDC",
             "madUSDC", "bridgedUSDC", "USDbC", "cUSDC", "fUSDC", "zUSDC"},
    "SOL":  {"SOL", "WSOL", "mSOL", "stSOL", "jitoSOL", "bSOL"},
    "STRK": {"STRK"},
    "ADA":  {"ADA", "WADA"},
    "APT":  {"APT", "stAPT", "amAPT", "tAPT"},
    "ETH":  {"ETH", "WETH", "WSTETH", "stETH", "rETH", "cbETH", "swETH",
             "weETH", "ezETH"},
    "BTC":  {"BTC", "WBTC", "tBTC", "cbBTC", "sBTC"},
}

# Stablecoin asset keys — used for "Suspect USDT support?" and related columns
STABLECOIN_KEYS = {"USDT", "USDC"}


def normalize_token(symbol: str) -> str:
    """Strip common prefixes/suffixes from token symbols."""
    return symbol.strip()


def match_token_to_asset(token_symbol: str, target_assets: List[str]) -> Optional[str]:
    """
    Check if a token symbol matches any of our target assets.
    Returns the canonical asset name if matched, None otherwise.
    """
    clean = normalize_token(token_symbol)
    for asset in target_assets:
        aliases = TOKEN_ALIASES.get(asset, {asset})
        if clean in aliases:
            return asset
    return None


# ── Protocol enrichment ────────────────────────────────────────────────────

def get_protocol_slug(project_name: str, website: str, protocols_index: dict) -> Optional[str]:
    """
    Try to find a DefiLlama slug for a project.
    Looks up by name in the pre-fetched protocols index.
    """
    # Try exact name match (case-insensitive)
    name_lower = project_name.strip().lower()
    if name_lower in protocols_index:
        return protocols_index[name_lower]["slug"]

    # Try matching by URL
    if website:
        website_clean = website.rstrip("/").lower()
        for _, proto in protocols_index.items():
            proto_url = (proto.get("url") or "").rstrip("/").lower()
            if proto_url and proto_url == website_clean:
                return proto["slug"]

    return None


def extract_token_holdings(
    protocol_data: dict, chain_name: str, target_assets: List[str]
) -> Dict[str, float]:
    """
    Extract current token holdings for target assets from protocol data.

    Looks at chainTvls[chain].tokensInUsd (last entry = current).
    Returns dict of {asset: usd_value}.
    """
    holdings = {}
    chain_tvls = protocol_data.get("chainTvls", {})

    # Try chain-specific first, then aggregate
    chain_data = chain_tvls.get(chain_name, {})
    tokens_usd_series = chain_data.get("tokensInUsd", [])

    # If no chain-specific data, try top-level aggregate
    if not tokens_usd_series:
        tokens_usd_series = protocol_data.get("tokensInUsd", [])

    if not tokens_usd_series:
        return holdings

    # Get the latest snapshot
    latest = tokens_usd_series[-1]
    token_map = latest.get("tokens", {})

    for symbol, usd_value in token_map.items():
        asset = match_token_to_asset(symbol, target_assets)
        if asset:
            # Accumulate (multiple aliases may resolve to same asset)
            holdings[asset] = holdings.get(asset, 0.0) + float(usd_value)

    return holdings


def classify_stablecoin_support(holdings: Dict[str, float]) -> dict:
    """
    Classify stablecoin support based on token holdings.

    Returns dict with column values for the heuristic columns.
    """
    has_usdt = holdings.get("USDT", 0) > 0
    has_usdc = holdings.get("USDC", 0) > 0
    has_any_stablecoin = has_usdt or has_usdc

    return {
        "has_usdt": has_usdt,
        "has_usdc": has_usdc,
        "has_any_stablecoin": has_any_stablecoin,
        "usdt_value": holdings.get("USDT", 0),
        "usdc_value": holdings.get("USDC", 0),
    }


# ── Main enrichment ───────────────────────────────────────────────────────

def build_protocols_index(chain_slug: str) -> dict:
    """
    Fetch all DefiLlama protocols and build a name→proto index,
    filtered to protocols active on the target chain.
    """
    print("Fetching DefiLlama protocols list...")
    all_protocols = fetch_json(DEFILLAMA_PROTOCOLS_URL)
    if not all_protocols:
        print("Error: Could not fetch protocols list")
        return {}

    # Filter to protocols that include this chain
    chain_lower = chain_slug.lower()
    index = {}
    for proto in all_protocols:
        chains = [c.lower() for c in proto.get("chains", [])]
        if chain_lower in chains or not chains:  # include chain-less protocols
            name_lower = proto.get("name", "").strip().lower()
            if name_lower:
                index[name_lower] = proto

    print(f"  Found {len(index)} protocols on {chain_slug}")
    return index


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
) -> Tuple[int, int, int]:
    """
    Enrich an ecosystem CSV with DefiLlama token data.

    Returns (total_rows, matched_slugs, enriched_rows).
    """
    # Load chain config for DefiLlama chain slug
    chain_config = load_chain_config(chain)
    defillama_config = chain_config.get("sources", {}).get("defillama", {})
    chain_slug = defillama_config.get("chain_slug", chain.capitalize())

    # Build protocols index
    protocols_index = build_protocols_index(chain_slug)
    if not protocols_index:
        return 0, 0, 0

    # Load CSV
    print(f"\nLoading CSV: {csv_path}")
    rows = load_csv(csv_path)
    total = len(rows)
    print(f"  {total} rows to process")

    matched = 0
    enriched = 0
    enriched_rows = []

    for i, row in enumerate(rows):
        name = row.get("Project Name", "").strip()
        website = row.get("Website", "").strip()

        if not name:
            enriched_rows.append(row)
            continue

        # Try to find DefiLlama slug
        slug = get_protocol_slug(name, website, protocols_index)

        if not slug:
            enriched_rows.append(row)
            continue

        matched += 1
        print(f"  [{i+1}/{total}] {name} → {slug}", end="")

        # Fetch protocol detail
        time.sleep(REQUEST_DELAY)
        proto_data = fetch_json(DEFILLAMA_PROTOCOL_URL.format(slug=slug))

        if not proto_data:
            print(" (no data)")
            enriched_rows.append(row)
            continue

        # Extract token holdings
        holdings = extract_token_holdings(proto_data, chain_slug, target_assets)

        if not holdings:
            print(" (no token breakdown)")
            enriched_rows.append(row)
            continue

        # Classify stablecoin support
        classification = classify_stablecoin_support(holdings)

        # Build enrichment updates
        updates = {}

        # Update stablecoin heuristic columns
        if classification["has_any_stablecoin"]:
            updates["Suspect USDT support?"] = "TRUE"
            updates["Web3 but no stablecoin"] = ""
            if classification["has_usdt"] and classification["has_usdc"]:
                updates["General Stablecoin Adoption"] = "TRUE"
        else:
            # Has a DeFi protocol but no stablecoins detected
            if not row.get("Suspect USDT support?"):
                updates["Web3 but no stablecoin"] = "TRUE"

        # Build evidence: structured asset totals (separate from notes)
        evidence_parts = []
        for asset in target_assets:
            if asset in holdings and holdings[asset] > 0:
                evidence_parts.append(f"{asset}: ${holdings[asset]:,.0f}")

        if evidence_parts:
            evidence = " | ".join(evidence_parts)
            existing_evidence = row.get("Evidence URLs", "").strip()
            if existing_evidence:
                updates["Evidence URLs"] = f"{existing_evidence} | {evidence}"
            else:
                updates["Evidence URLs"] = evidence

        # Build notes: clean human-readable findings about target support
        note_findings = []
        has_usdt = classification["has_usdt"]
        has_usdc = classification["has_usdc"]
        has_sol = holdings.get("SOL", 0) > 0
        has_strk = holdings.get("STRK", 0) > 0
        has_ada = holdings.get("ADA", 0) > 0

        if has_usdt and has_usdc:
            note_findings.append("Supports USDT + USDC")
        elif has_usdt:
            note_findings.append("Supports USDT")
        elif has_usdc:
            note_findings.append("Supports USDC only (no USDT)")

        if has_sol:
            note_findings.append("Solana token detected")
        if has_strk:
            note_findings.append("Starknet token detected")
        if has_ada:
            note_findings.append("Cardano token detected")

        if not evidence_parts and not note_findings:
            # Protocol found but no target assets at all
            note_findings.append("No target asset support detected")

        if note_findings:
            finding_text = "; ".join(note_findings)
            existing_notes = row.get("Notes", "").strip()
            if existing_notes:
                if finding_text not in existing_notes:
                    updates["Notes"] = f"{existing_notes} | {finding_text}"
            else:
                updates["Notes"] = finding_text

        if updates and (evidence_parts or note_findings):
            enriched += 1
            # Console output
            status_parts = []
            if has_usdt:
                status_parts.append(f"USDT=${classification['usdt_value']:,.0f}")
            if has_usdc:
                status_parts.append(f"USDC=${classification['usdc_value']:,.0f}")
            for asset in target_assets:
                if asset not in STABLECOIN_KEYS and asset in holdings and holdings[asset] > 0:
                    status_parts.append(f"{asset}=${holdings[asset]:,.0f}")
            if status_parts:
                print(f" ✓ {', '.join(status_parts)}")
            else:
                print(" ✓ no target assets")

            if not dry_run:
                row.update(updates)
        else:
            print(" (no target assets found)")

        enriched_rows.append(row)

    # Write output
    if not dry_run and enriched > 0:
        output_path = csv_path.with_name(csv_path.stem + "_enriched.csv")
        write_csv(enriched_rows, output_path)
        print(f"\nEnriched CSV written to: {output_path}")
    elif dry_run:
        print("\n[DRY RUN] No files written.")

    return total, matched, enriched


def main():
    parser = argparse.ArgumentParser(
        description="Enrich ecosystem CSV with DefiLlama per-protocol token data"
    )
    parser.add_argument(
        "--chain", required=True, help="Chain ID (e.g., aptos, tron)"
    )
    parser.add_argument(
        "--csv", help="Path to CSV (auto-detected from data/<chain>/ if omitted)"
    )
    parser.add_argument(
        "--assets",
        default=None,
        help="Comma-separated target assets (default: from chains.json target_assets, or USDT,USDC)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview enrichment without writing files",
    )
    args = parser.parse_args()

    # Resolve CSV
    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_path = find_main_csv(args.chain)
        if not csv_path:
            print(f"Error: No CSV found in data/{args.chain}/")
            print("Use --csv to specify the path, or run init_chain.sh first.")
            sys.exit(1)

    if not csv_path.exists():
        print(f"Error: CSV not found: {csv_path}")
        sys.exit(1)

    # Parse target assets: CLI flag > chains.json > default
    if args.assets:
        target_assets = [a.strip().upper() for a in args.assets.split(",") if a.strip()]
    else:
        chain_config = load_chain_config(args.chain)
        target_assets = chain_config.get("target_assets", ["USDT", "USDC"])
    print(f"Target assets: {target_assets}")
    print(f"Chain: {args.chain}")
    print()

    # Run enrichment
    total, matched, enriched = enrich_csv(csv_path, args.chain, target_assets, args.dry_run)

    # Summary
    print("\n" + "=" * 60)
    print("ENRICHMENT SUMMARY")
    print("=" * 60)
    print(f"Total rows:        {total}")
    print(f"Slugs matched:     {matched} ({matched/total*100:.0f}%)" if total else "")
    print(f"Rows enriched:     {enriched} ({enriched/matched*100:.0f}% of matched)" if matched else "")
    print(f"Target assets:     {', '.join(target_assets)}")
    if args.dry_run:
        print("\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
