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
from urllib.parse import urlparse, urljoin

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.csv_utils import load_csv, write_csv, find_main_csv


# ── Dynamic stablecoin catalog ──────────────────────────────────────────

CATALOG_PATH = Path(__file__).parent.parent / "config" / "stablecoin_catalog.json"


def load_dynamic_stablecoins(catalog_path: Path = CATALOG_PATH) -> Dict[str, List[str]]:
    """
    Load dynamic stablecoin keywords from cached CoinGecko catalog.

    Returns dict like {"DAI": ["dai"], "FRAX": ["frax"], "TUSD": ["tusd", "trueusd"]}.
    USDT and USDC are excluded (they have their own hardcoded path).
    Returns empty dict if catalog is missing or corrupt.
    """
    if not catalog_path.exists():
        return {}
    try:
        with open(catalog_path) as f:
            catalog = json.load(f)
        result: Dict[str, List[str]] = {}
        for coin in catalog.get("stablecoins", []):
            symbol = coin["symbol"].upper()
            # NEVER include USDT or USDC here
            if symbol in ("USDT", "USDC"):
                continue
            keywords = coin.get("keywords", [])
            if keywords:
                result[symbol] = keywords
        return result
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


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

# ── Subpage crawling ────────────────────────────────────────────────────

# Common subpaths to try on every site (order = priority)
DEFAULT_SUBPATHS = [
    "/about", "/features", "/products", "/services",
    "/faq", "/docs", "/developers", "/about-us", "/how-it-works",
]

DEFAULT_MAX_SUBPAGES = 5   # Max subpages per site (homepage doesn't count)
DEFAULT_CRAWL_MODE = "both"  # "homepage" | "fixed" | "links" | "both"
MAX_EXTRACTED_LINKS = 20   # Max same-domain links to extract from homepage

# Regex to detect the crawled(N) marker variant
SCAN_MARKER_CRAWLED_RE = re.compile(r"website-scan: crawled\(\d+\)")


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


# ── Link extraction ─────────────────────────────────────────────────────

# Static asset extensions to skip when extracting links
_SKIP_EXTENSIONS = frozenset({
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".ico", ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".zip",
    ".mp4", ".webm", ".mp3", ".xml", ".json", ".rss",
})

_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


def extract_same_domain_links(
    html: str, base_url: str, max_links: int = MAX_EXTRACTED_LINKS,
) -> List[str]:
    """
    Extract unique same-domain links from HTML using regex.

    Returns absolute URLs on the same domain as base_url.
    Excludes fragment-only links, static assets, mailto/tel, and the homepage itself.
    """
    parsed_base = urlparse(base_url)
    base_domain = (parsed_base.hostname or "").lower()
    base_path = parsed_base.path.rstrip("/").lower() or "/"

    seen_paths: Set[str] = set()
    results: List[str] = []

    for match in _HREF_RE.finditer(html):
        href = match.group(1).strip()

        # Skip fragments, mailto, tel, javascript
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        # Resolve relative URLs
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)

        # Same domain only
        if (parsed.hostname or "").lower() != base_domain:
            continue

        # Skip static assets
        path_lower = parsed.path.lower()
        if any(path_lower.endswith(ext) for ext in _SKIP_EXTENSIONS):
            continue

        # Normalize: strip fragment and query, keep scheme + host + path
        clean_path = path_lower.rstrip("/") or "/"
        clean_url = f"{parsed.scheme}://{parsed.hostname}{parsed.path}"

        # Skip homepage itself
        if clean_path == base_path:
            continue

        if clean_path not in seen_paths:
            seen_paths.add(clean_path)
            results.append(clean_url)
            if len(results) >= max_links:
                break

    return results


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


# ── Site crawling ───────────────────────────────────────────────────────

def crawl_site(
    homepage_url: str,
    crawl_mode: str = DEFAULT_CRAWL_MODE,
    max_subpages: int = DEFAULT_MAX_SUBPAGES,
) -> Tuple[Optional[str], int, int]:
    """
    Crawl a site's homepage and subpages, returning aggregated text.

    Args:
        homepage_url: The project's main website URL.
        crawl_mode: "homepage", "fixed", "links", or "both".
        max_subpages: Maximum number of subpages to fetch beyond homepage.

    Returns:
        (aggregated_text, pages_fetched, pages_failed)
        aggregated_text is None if even the homepage fails.
    """
    homepage_url = normalize_url_for_fetch(homepage_url)
    pages_fetched = 0
    pages_failed = 0
    all_texts: List[str] = []

    # ── Step 1: Fetch homepage ──
    homepage_html = fetch_html(homepage_url)
    if not homepage_html:
        return None, 0, 1

    pages_fetched += 1
    homepage_text = html_to_text(homepage_html)
    if len(homepage_text) >= 50:
        all_texts.append(homepage_text)

    # If homepage-only mode, return immediately
    if crawl_mode == "homepage" or max_subpages <= 0:
        combined = " ".join(all_texts) if all_texts else None
        return combined, pages_fetched, pages_failed

    # ── Step 2: Build candidate subpage URLs ──
    candidate_urls: List[str] = []

    # Fixed common paths
    if crawl_mode in ("fixed", "both"):
        for subpath in DEFAULT_SUBPATHS:
            candidate_urls.append(urljoin(homepage_url, subpath))

    # Links extracted from homepage HTML
    if crawl_mode in ("links", "both"):
        extracted = extract_same_domain_links(homepage_html, homepage_url)
        for link_url in extracted:
            if link_url not in candidate_urls:
                candidate_urls.append(link_url)

    # Deduplicate by normalized path and cap at max_subpages
    seen_paths: Set[str] = set()
    unique_candidates: List[str] = []
    for url in candidate_urls:
        parsed = urlparse(url)
        path_key = (parsed.path or "/").rstrip("/").lower()
        if path_key and path_key != "/" and path_key not in seen_paths:
            seen_paths.add(path_key)
            unique_candidates.append(url)

    unique_candidates = unique_candidates[:max_subpages]

    # ── Step 3: Fetch subpages ──
    for subpage_url in unique_candidates:
        time.sleep(REQUEST_DELAY)  # Rate limiting between ALL requests

        sub_html = fetch_html(subpage_url)
        if not sub_html:
            pages_failed += 1
            continue

        pages_fetched += 1
        sub_text = html_to_text(sub_html)
        if len(sub_text) >= 50:
            all_texts.append(sub_text)

    combined = " ".join(all_texts) if all_texts else None
    return combined, pages_fetched, pages_failed


# ── Keyword matching ─────────────────────────────────────────────────────

def scan_keywords(
    text: str,
    target_assets: List[str],
    dynamic_stablecoins: Optional[Dict[str, List[str]]] = None,
) -> Dict:
    """
    Scan plain text for asset/stablecoin/DeFi keywords.

    Returns dict with:
        found_assets: {asset_key: [matched_keywords]}
        found_dynamic_stablecoins: {symbol: [matched_keywords]}
        found_generic_stablecoin: bool
        found_web3_signal: [matched_keywords]
    """
    found_assets: Dict[str, List[str]] = {}
    found_dynamic: Dict[str, List[str]] = {}
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

    # Check dynamic stablecoin keywords (NOT gated by target_assets)
    if dynamic_stablecoins:
        for symbol, keywords in dynamic_stablecoins.items():
            matches = []
            for kw in keywords:
                if len(kw) <= 5:
                    if re.search(r"\b" + re.escape(kw) + r"\b", text):
                        matches.append(kw)
                else:
                    if kw in text:
                        matches.append(kw)
            if matches:
                found_dynamic[symbol] = matches

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
        "found_dynamic_stablecoins": found_dynamic,
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

    # Dynamic stablecoin findings (same format for promote_hints.py compatibility)
    for symbol, keywords in scan_result.get("found_dynamic_stablecoins", {}).items():
        kw_str = "; ".join(keywords)
        parts.append(f"{symbol} keywords ({kw_str})")

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

def should_scan_row(row: Dict, rescan_homepage_only: bool = False) -> bool:
    """
    Check if a row should be scanned.
    Only scan rows that have websites but NO enrichment from other sources.

    Args:
        rescan_homepage_only: If True, rows previously scanned homepage-only
            (marker "website-scan: scanned") become eligible for re-scanning
            with subpage crawling. Rows marked "website-scan: crawled(N)"
            are still skipped.
    """
    # Must have a website
    website = row.get("Website", "").strip()
    if not website or not is_fetchable_url(website):
        return False

    # Skip if already scanned (incremental)
    evidence = row.get("Evidence & Source URLs", "")
    if SCAN_MARKER in evidence:
        if rescan_homepage_only:
            # Re-scan only if it was homepage-only ("scanned"), not "crawled(N)"
            if SCAN_MARKER_CRAWLED_RE.search(evidence):
                return False  # Already crawled with subpages — skip
            # "website-scan: scanned" → eligible for re-scan, fall through
        else:
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
    crawl_mode: str = DEFAULT_CRAWL_MODE,
    max_subpages: int = DEFAULT_MAX_SUBPAGES,
    rescan_homepage_only: bool = False,
) -> Tuple[int, int, int, int]:
    """
    Enrich CSV with website keyword scan results.

    Args:
        crawl_mode: Subpage crawling strategy ("homepage", "fixed", "links", "both").
        max_subpages: Maximum subpages to fetch per site (beyond homepage).
        rescan_homepage_only: Re-scan rows that were only homepage-scanned previously.

    Returns (total_rows, scanned, keywords_found, fetch_errors).
    """
    print(f"Loading CSV: {csv_path}")
    rows = load_csv(csv_path)
    total = len(rows)
    print(f"  {total} rows loaded")
    print(f"  Target assets: {', '.join(target_assets)}")
    print(f"  Crawl mode: {crawl_mode} (max {max_subpages} subpages)")

    # Load dynamic stablecoin catalog (beyond USDT/USDC)
    dynamic_stablecoins = load_dynamic_stablecoins()
    if dynamic_stablecoins:
        print(f"  Dynamic stablecoin catalog: {len(dynamic_stablecoins)} entries loaded")
    else:
        print(f"  Dynamic stablecoin catalog: not available (scanning USDT/USDC only)")

    # Count eligible rows
    eligible = [i for i, r in enumerate(rows)
                if should_scan_row(r, rescan_homepage_only=rescan_homepage_only)]
    if limit > 0:
        eligible = eligible[:limit]
    print(f"  {len(eligible)} rows eligible for website scan")

    scanned = 0
    keywords_found = 0
    fetch_errors = 0
    skipped_incremental = sum(
        1 for r in rows
        if SCAN_MARKER in r.get("Evidence & Source URLs", "")
        and not (rescan_homepage_only
                 and f"{SCAN_MARKER}: scanned" in r.get("Evidence & Source URLs", "")
                 and not SCAN_MARKER_CRAWLED_RE.search(r.get("Evidence & Source URLs", "")))
    )
    if skipped_incremental:
        print(f"  {skipped_incremental} rows skipped (already scanned)")

    for idx_num, row_idx in enumerate(eligible):
        row = rows[row_idx]
        name = row.get("Project Name", "").strip()
        website = row.get("Website", "").strip()

        print(f"  [{idx_num + 1}/{len(eligible)}] {name} → {website}", end="", flush=True)

        # Rate limiting (between sites; crawl_site handles inter-page delays)
        if scanned > 0:
            time.sleep(REQUEST_DELAY)

        # Crawl site (homepage + subpages)
        text, pages_fetched, pages_failed = crawl_site(
            website, crawl_mode=crawl_mode, max_subpages=max_subpages,
        )
        scanned += 1

        if text is None:
            print(" ✗ fetch failed")
            fetch_errors += 1
            # Still mark as scanned to avoid re-trying dead sites
            if not dry_run:
                _add_scan_marker(row, pages_fetched=0)
            continue

        if len(text) < 50:
            print(" ✗ too little text")
            if not dry_run:
                _add_scan_marker(row, pages_fetched=pages_fetched)
            continue

        # Scan aggregated text for keywords
        result = scan_keywords(text, target_assets, dynamic_stablecoins=dynamic_stablecoins)
        note_text = format_scan_note(result)

        if note_text:
            keywords_found += 1
            # Show what we found (include dynamic stablecoins)
            all_asset_keys = list(result["found_assets"].keys()) + list(result.get("found_dynamic_stablecoins", {}).keys())
            asset_list = ", ".join(all_asset_keys)
            extras = []
            if result["found_generic_stablecoin"]:
                extras.append("stablecoin")
            if result["found_web3_signal"]:
                extras.append(f"web3({len(result['found_web3_signal'])})")
            detail = asset_list
            if extras:
                detail += (" + " if detail else "") + ", ".join(extras)
            page_info = f" [{pages_fetched}pg]" if pages_fetched > 1 else ""
            print(f" ✓ {detail}{page_info}")

            # Update Notes (append, remove old scan note on re-scan)
            if not dry_run:
                existing_notes = row.get("Notes", "").strip()
                # On re-scan, remove old website-scan note to avoid duplicates
                if rescan_homepage_only and "[UNVERIFIED website-scan]" in existing_notes:
                    parts = existing_notes.split(" | ")
                    parts = [p for p in parts if "[UNVERIFIED website-scan]" not in p]
                    existing_notes = " | ".join(p for p in parts if p.strip())
                if existing_notes:
                    if note_text not in existing_notes:
                        row["Notes"] = f"{existing_notes} | {note_text}"
                else:
                    row["Notes"] = note_text
        else:
            page_info = f" [{pages_fetched}pg]" if pages_fetched > 1 else ""
            print(f" · no keywords{page_info}")

        # Mark as scanned (regardless of findings)
        if not dry_run:
            _add_scan_marker(row, pages_fetched=pages_fetched)

    # Write CSV
    if not dry_run and scanned > 0:
        write_csv(rows, csv_path)
        print(f"\nEnriched CSV written to: {csv_path}")

    return total, scanned, keywords_found, fetch_errors


def _add_scan_marker(row: Dict, pages_fetched: int = 1) -> None:
    """
    Add the website-scan marker to Evidence for incremental skip.

    Args:
        pages_fetched: Number of pages fetched (1 = homepage only).
            1 -> "website-scan: scanned" (backward compat with old runs)
            >1 -> "website-scan: crawled(N)"
    """
    evidence = row.get("Evidence & Source URLs", "").strip()

    # Remove any existing scan markers first (supports re-scan)
    if SCAN_MARKER in evidence:
        parts = [p.strip() for p in evidence.split("|")]
        parts = [p for p in parts if not p.startswith(SCAN_MARKER)]
        evidence = " | ".join(p for p in parts if p)

    if pages_fetched <= 1:
        marker = f"{SCAN_MARKER}: scanned"
    else:
        marker = f"{SCAN_MARKER}: crawled({pages_fetched})"

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
    parser.add_argument("--refresh-catalog", action="store_true",
                        help="Force refresh stablecoin catalog from CoinGecko before scanning")
    parser.add_argument("--crawl-mode",
                        choices=["homepage", "fixed", "links", "both"],
                        default=DEFAULT_CRAWL_MODE,
                        help=f"Subpage crawling strategy (default: {DEFAULT_CRAWL_MODE})")
    parser.add_argument("--max-subpages", type=int, default=DEFAULT_MAX_SUBPAGES,
                        help=f"Max subpages per site (default: {DEFAULT_MAX_SUBPAGES})")
    parser.add_argument("--no-subpages", action="store_true",
                        help="Shortcut for --crawl-mode homepage (disable subpage crawling)")
    parser.add_argument("--rescan-homepage-only", action="store_true",
                        help="Re-scan rows that were only homepage-scanned in a previous run")
    args = parser.parse_args()

    # Resolve crawl mode
    crawl_mode = "homepage" if args.no_subpages else args.crawl_mode

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

    # Refresh stablecoin catalog if requested
    if args.refresh_catalog:
        from scripts.build_stablecoin_catalog import ensure_catalog
        print("Refreshing stablecoin catalog...")
        ensure_catalog(CATALOG_PATH, max_age_days=0)

    total, scanned, found, errors = enrich_csv(
        csv_path, args.chain, target_assets,
        dry_run=args.dry_run, limit=args.limit,
        crawl_mode=crawl_mode, max_subpages=args.max_subpages,
        rescan_homepage_only=args.rescan_homepage_only,
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
    print(f"Crawl mode:       {crawl_mode} (max {args.max_subpages} subpages)")

    if args.dry_run:
        print(f"\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
