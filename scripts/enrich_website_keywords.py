#!/usr/bin/env python3
"""
Enrich ecosystem CSV with keyword signals from project websites.

Fetches homepage HTML for projects that have no asset intelligence from other
enrichment sources (Grid, DefiLlama, CoinGecko), strips it to plain text,
and scans for stablecoin/chain/DeFi keywords.

IMPORTANT: Website keyword matches are LOWER CONFIDENCE than API data.
Findings go to Notes only as [UNVERIFIED] hints — never to the boolean
columns (Suspect USDT support?, General Stablecoin Adoption) or Evidence.

Usage:
    python scripts/enrich_website_keywords.py --chain near --dry-run --limit 10
    python scripts/enrich_website_keywords.py --chain near
"""

import argparse
import json
import re
import ssl
import sys
import time
import urllib.request
import urllib.error
from html import unescape as html_unescape
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.csv_utils import load_csv, write_csv, find_main_csv


# ── Keyword dictionaries ────────────────────────────────────────────────

# Stablecoin keywords — keyed by target asset ticker
STABLECOIN_KEYWORDS: Dict[str, List[str]] = {
    "USDT": ["usdt", "tether"],
    "USDC": ["usdc", "usd coin"],
}

# Chain/asset keywords — keyed by target asset ticker
CHAIN_KEYWORDS: Dict[str, List[str]] = {
    "SOL": ["solana"],
    "STRK": ["starknet"],
    "ADA": ["cardano"],
    "APT": ["aptos"],
    "ETH": ["ethereum"],
    "BTC": ["bitcoin"],
}

# Generic stablecoin signal (not asset-specific)
GENERIC_STABLECOIN_KEYWORDS = ["stablecoin", "stablecoins", "stable coin"]

# Web3/DeFi signal keywords
WEB3_SIGNAL_KEYWORDS = [
    "swap", "bridge", "dex", "liquidity", "yield",
    "lending", "borrow", "staking", "farming", "amm",
    "defi", "decentralized exchange", "liquidity pool",
]

# ── HTTP settings ────────────────────────────────────────────────────────

USER_AGENT = "EcosystemResearch/1.0"
REQUEST_TIMEOUT = 10  # seconds
REQUEST_DELAY = 0.5   # seconds between requests
MAX_RETRIES = 1
MAX_HTML_BYTES = 500_000  # 500KB — plenty for keyword detection

# Incremental skip marker
SCAN_MARKER = "website-scan"


# ── URL validation ───────────────────────────────────────────────────────

def is_fetchable_url(url: str) -> bool:
    """Check if a URL is safe to fetch (HTTP/HTTPS, not localhost/IP)."""
    url = url.strip()
    if not url:
        return False
    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        # Skip localhost, IPs, empty hosts
        if not host or host in ("localhost", "127.0.0.1", "0.0.0.0"):
            return False
        if host.replace(".", "").isdigit():  # bare IPv4
            return False
        if parsed.scheme not in ("http", "https"):
            return False
        return True
    except Exception:
        return False


def normalize_url_for_fetch(url: str) -> str:
    """Ensure URL has a scheme for fetching."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


# ── HTML fetching ────────────────────────────────────────────────────────

def fetch_html(url: str) -> Optional[str]:
    """
    Fetch homepage HTML with retry on 5xx/timeout.
    Returns HTML string or None on failure.
    """
    url = normalize_url_for_fetch(url)

    # Create SSL context that doesn't verify (some project sites have bad certs)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
                # Check content type — skip non-HTML
                ct = resp.headers.get("Content-Type", "")
                if ct and "html" not in ct.lower() and "text" not in ct.lower():
                    return None
                return resp.read(MAX_HTML_BYTES).decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt < MAX_RETRIES:
                time.sleep(1)
                continue
            return None
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(1)
                continue
            return None
    return None


# ── HTML → text extraction ───────────────────────────────────────────────

# Regex to strip script/style/noscript blocks
BLOCK_STRIP_RE = re.compile(
    r"<\s*(script|style|noscript)[^>]*>.*?</\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Regex to strip all HTML tags
TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(html: str) -> str:
    """Strip HTML to plain text for keyword scanning."""
    # Remove script/style/noscript blocks
    text = BLOCK_STRIP_RE.sub(" ", html)
    # Remove all remaining HTML tags
    text = TAG_RE.sub(" ", text)
    # Decode HTML entities
    text = html_unescape(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


# ── Keyword matching ─────────────────────────────────────────────────────

def scan_keywords(
    text: str,
    target_assets: List[str],
) -> Dict:
    """
    Scan plain text for asset/stablecoin/DeFi keywords.

    Returns dict with:
        found_assets: {asset_key: [matched_keywords]}
        found_generic_stablecoin: bool
        found_web3_signal: [matched_keywords]
    """
    found_assets: Dict[str, List[str]] = {}
    found_web3: List[str] = []
    found_generic = False

    # Check stablecoin keywords
    for asset, keywords in STABLECOIN_KEYWORDS.items():
        if asset not in target_assets:
            continue
        matches = []
        for kw in keywords:
            # Word boundary match for short terms
            if len(kw) <= 5:
                if re.search(r"\b" + re.escape(kw) + r"\b", text):
                    matches.append(kw)
            else:
                if kw in text:
                    matches.append(kw)
        if matches:
            found_assets[asset] = matches

    # Check chain keywords
    for asset, keywords in CHAIN_KEYWORDS.items():
        if asset not in target_assets:
            continue
        matches = []
        for kw in keywords:
            if len(kw) <= 4:
                # Short terms like "sol", "ada" — require word boundary
                if re.search(r"\b" + re.escape(kw) + r"\b", text):
                    matches.append(kw)
            else:
                if kw in text:
                    matches.append(kw)
        if matches:
            found_assets[asset] = matches

    # Generic stablecoin mentions
    for kw in GENERIC_STABLECOIN_KEYWORDS:
        if kw in text:
            found_generic = True
            break

    # Web3/DeFi signal
    for kw in WEB3_SIGNAL_KEYWORDS:
        if len(kw) <= 4:
            if re.search(r"\b" + re.escape(kw) + r"\b", text):
                found_web3.append(kw)
        else:
            if kw in text:
                found_web3.append(kw)

    return {
        "found_assets": found_assets,
        "found_generic_stablecoin": found_generic,
        "found_web3_signal": found_web3,
    }


# ── Note formatting ──────────────────────────────────────────────────────

def format_scan_note(scan_result: Dict) -> str:
    """
    Format scan results into a [UNVERIFIED] note string.
    Returns empty string if no findings.
    """
    parts = []

    # Asset-specific findings
    for asset, keywords in scan_result["found_assets"].items():
        kw_str = "; ".join(keywords)
        parts.append(f"{asset} keywords ({kw_str})")

    # Generic stablecoin
    if scan_result["found_generic_stablecoin"]:
        parts.append("stablecoin mentions")

    # Web3 signal (only if no asset-specific findings — avoid noise)
    if not scan_result["found_assets"] and scan_result["found_web3_signal"]:
        web3_kws = "; ".join(scan_result["found_web3_signal"][:5])  # cap at 5
        parts.append(f"web3 signals ({web3_kws})")

    if not parts:
        return ""

    return "[UNVERIFIED website-scan] " + " | ".join(parts)


# ── Row eligibility ──────────────────────────────────────────────────────

def should_scan_row(row: Dict) -> bool:
    """
    Check if a row should be scanned.
    Only scan rows that have websites but NO enrichment from other sources.
    """
    # Must have a website
    website = row.get("Website", "").strip()
    if not website or not is_fetchable_url(website):
        return False

    # Skip if already scanned (incremental)
    evidence = row.get("Evidence & Source URLs", "")
    if SCAN_MARKER in evidence:
        return False

    # Skip if already enriched by stronger sources
    # (Grid, DefiLlama, CoinGecko put their markers in Evidence)
    if evidence.strip():
        # Has some evidence — check if it's from a verified source
        verified_markers = ["Grid confirms", "DefiLlama", "defillama.com",
                           "CoinGecko", "coingecko.com", "grid.id"]
        for marker in verified_markers:
            if marker in evidence:
                return False

    return True


# ── Main enrichment function ─────────────────────────────────────────────

def enrich_csv(
    csv_path: Path,
    chain: str,
    target_assets: List[str],
    dry_run: bool = False,
    limit: int = 0,
) -> Tuple[int, int, int, int]:
    """
    Enrich CSV with website keyword scan results.

    Returns (total_rows, scanned, keywords_found, fetch_errors).
    """
    print(f"Loading CSV: {csv_path}")
    rows = load_csv(csv_path)
    total = len(rows)
    print(f"  {total} rows loaded")
    print(f"  Target assets: {', '.join(target_assets)}")

    # Count eligible rows
    eligible = [i for i, r in enumerate(rows) if should_scan_row(r)]
    if limit > 0:
        eligible = eligible[:limit]
    print(f"  {len(eligible)} rows eligible for website scan")

    scanned = 0
    keywords_found = 0
    fetch_errors = 0
    skipped_incremental = sum(
        1 for r in rows
        if SCAN_MARKER in r.get("Evidence & Source URLs", "")
    )
    if skipped_incremental:
        print(f"  {skipped_incremental} rows skipped (already scanned)")

    for idx_num, row_idx in enumerate(eligible):
        row = rows[row_idx]
        name = row.get("Project Name", "").strip()
        website = row.get("Website", "").strip()

        print(f"  [{idx_num + 1}/{len(eligible)}] {name} → {website}", end="", flush=True)

        # Rate limiting
        if scanned > 0:
            time.sleep(REQUEST_DELAY)

        # Fetch HTML
        html = fetch_html(website)
        scanned += 1

        if not html:
            print(" ✗ fetch failed")
            fetch_errors += 1
            # Still mark as scanned to avoid re-trying dead sites
            if not dry_run:
                _add_scan_marker(row)
            continue

        # Extract text and scan
        text = html_to_text(html)

        if len(text) < 50:
            print(" ✗ too little text")
            if not dry_run:
                _add_scan_marker(row)
            continue

        # Scan for keywords
        result = scan_keywords(text, target_assets)
        note_text = format_scan_note(result)

        if note_text:
            keywords_found += 1
            # Show what we found
            asset_list = ", ".join(result["found_assets"].keys())
            extras = []
            if result["found_generic_stablecoin"]:
                extras.append("stablecoin")
            if result["found_web3_signal"]:
                extras.append(f"web3({len(result['found_web3_signal'])})")
            detail = asset_list
            if extras:
                detail += (" + " if detail else "") + ", ".join(extras)
            print(f" ✓ {detail}")

            # Update Notes (append)
            if not dry_run:
                existing_notes = row.get("Notes", "").strip()
                if existing_notes:
                    if note_text not in existing_notes:
                        row["Notes"] = f"{existing_notes} | {note_text}"
                else:
                    row["Notes"] = note_text
        else:
            print(" · no keywords")

        # Mark as scanned (regardless of findings)
        if not dry_run:
            _add_scan_marker(row)

    # Write CSV
    if not dry_run and scanned > 0:
        write_csv(rows, csv_path)
        print(f"\nEnriched CSV written to: {csv_path}")

    return total, scanned, keywords_found, fetch_errors


def _add_scan_marker(row: Dict) -> None:
    """Add the website-scan marker to Evidence for incremental skip."""
    evidence = row.get("Evidence & Source URLs", "").strip()
    marker = f"{SCAN_MARKER}: scanned"
    if marker not in evidence:
        if evidence:
            row["Evidence & Source URLs"] = f"{evidence} | {marker}"
        else:
            row["Evidence & Source URLs"] = marker


# ── CLI ──────────────────────────────────────────────────────────────────

def load_chain_config(chain: str) -> dict:
    """Load chain config from config/chains.json."""
    config_path = Path(__file__).parent.parent / "config" / "chains.json"
    with open(config_path) as f:
        config = json.load(f)
    for c in config["chains"]:
        if c["id"] == chain:
            return c
    print(f"Error: Chain '{chain}' not found in config/chains.json")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Enrich ecosystem CSV with website keyword scan"
    )
    parser.add_argument("--chain", required=True, help="Chain ID (e.g., near)")
    parser.add_argument("--csv", help="Path to CSV (auto-detected if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only first N eligible rows")
    parser.add_argument("--assets",
                        help="Override target assets (comma-separated)")
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

    # Load chain config for target assets
    chain_config = load_chain_config(args.chain)
    target_assets = (
        args.assets.split(",") if args.assets
        else chain_config.get("target_assets", ["USDT", "USDC"])
    )

    total, scanned, found, errors = enrich_csv(
        csv_path, args.chain, target_assets,
        dry_run=args.dry_run, limit=args.limit,
    )

    print(f"\n{'='*60}")
    print(f"WEBSITE KEYWORD SCAN SUMMARY")
    print(f"{'='*60}")
    print(f"Total rows:       {total}")
    print(f"Rows scanned:     {scanned}")
    print(f"Keywords found:   {found}")
    print(f"Fetch errors:     {errors}")
    hit_rate = f"{found/scanned*100:.1f}%" if scanned > 0 else "N/A"
    print(f"Hit rate:         {hit_rate}")

    if args.dry_run:
        print(f"\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
