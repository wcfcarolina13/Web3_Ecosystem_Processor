"""
Server-side project discovery scrapers.

Fetches project data from public REST APIs and produces rows
in the standard 27-column CSV format. Currently supports:
  - DefiLlama (any chain they track)

Usage:
    from dashboard.scraper import discover_defillama, merge_discovered_rows

    rows = discover_defillama("Solana", "solana")
    merged, added, dupes = merge_discovered_rows(existing_rows, rows)
"""

import json
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from lib.columns import empty_row
from lib.logging_config import get_logger
from lib.matching import normalize_name

logger = get_logger(__name__)

# ── HTTP fetching ──

RETRY_BACKOFF = 2.0
USER_AGENT = "EcosystemResearch/1.0"


def fetch_json(url: str, retries: int = 3) -> Optional[dict]:
    """Fetch JSON from URL with retry and backoff."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = RETRY_BACKOFF ** (attempt + 1)
                logger.warning("Rate limited (429), waiting %.0fs...", wait)
                time.sleep(wait)
                continue
            elif e.code == 404:
                return None
            else:
                logger.error("HTTP %d fetching %s", e.code, url)
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(RETRY_BACKOFF)
                continue
            logger.error("Error fetching %s: %s", url, e)
            return None
    return None


# ── Twitter handle normalization ──


def normalize_twitter(raw: str) -> str:
    """Normalize a Twitter/X handle: strip URL prefix, ensure @ prefix."""
    if not raw:
        return ""
    handle = str(raw).strip()
    for prefix in (
        "https://twitter.com/",
        "https://x.com/",
        "http://twitter.com/",
        "http://x.com/",
        "https://www.twitter.com/",
    ):
        if handle.lower().startswith(prefix):
            handle = handle[len(prefix):].rstrip("/")
            break
    # Strip query params
    if "?" in handle:
        handle = handle.split("?")[0]
    if handle and not handle.startswith("@"):
        handle = "@" + handle
    return handle


# ── Domain extraction ──


def extract_domain(url: str) -> str:
    """Extract domain from URL for dedup. Strips www. prefix."""
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.hostname or ""
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return ""


# ── DefiLlama Discovery ──

DEFILLAMA_PROTOCOLS_URL = "https://api.llama.fi/protocols"


def discover_defillama(
    chain_slug: str,
    chain_id: str,
    progress_cb: Optional[Callable] = None,
) -> List[Dict]:
    """
    Discover projects from DefiLlama for a given chain.

    Args:
        chain_slug: DefiLlama chain name (e.g., "Solana", "Ethereum", "Polygon").
        chain_id: Our internal chain ID (e.g., "solana").
        progress_cb: Optional callback(current, total, message) for UI updates.

    Returns:
        List of row dicts in CORRECT_COLUMNS format.
    """
    if progress_cb:
        progress_cb(0, 0, "Fetching DefiLlama protocols...")

    protocols = fetch_json(DEFILLAMA_PROTOCOLS_URL)
    if not protocols:
        raise RuntimeError("Failed to fetch DefiLlama protocols API")

    if not isinstance(protocols, list):
        raise RuntimeError(f"Unexpected DefiLlama response format: {type(protocols)}")

    # Filter protocols that list this chain
    matching = []
    for p in protocols:
        chains = p.get("chains", [])
        if chain_slug in chains:
            matching.append(p)

    total = len(matching)
    logger.info("DefiLlama: %d/%d protocols match chain '%s'", total, len(protocols), chain_slug)

    if progress_cb:
        progress_cb(0, total, f"Found {total} protocols for {chain_slug}")

    rows = []
    for i, p in enumerate(matching):
        row = empty_row(chain=chain_id.upper())
        row["Project Name"] = p.get("name", "").strip()
        row["Website"] = p.get("url", "").strip()
        row["X Handle"] = normalize_twitter(p.get("twitter", ""))
        row["Category"] = p.get("category", "").strip()
        row["Source"] = "DefiLlama"
        row["Notes"] = f"TVL: ${p.get('tvl', 0):,.0f}" if p.get("tvl") else ""
        row["Evidence & Source URLs"] = (
            f"https://defillama.com/protocol/{p.get('slug', '')}"
            if p.get("slug")
            else ""
        )

        # Skip entries with no name
        if row["Project Name"]:
            rows.append(row)

        if progress_cb and (i + 1) % 50 == 0:
            progress_cb(i + 1, total, f"Processing {i + 1}/{total} protocols...")

    if progress_cb:
        progress_cb(total, total, f"Discovered {len(rows)} projects from DefiLlama")

    logger.info("DefiLlama discovery: %d projects for chain '%s'", len(rows), chain_id)
    return rows


# ── Merge Logic ──


def merge_discovered_rows(
    existing_rows: List[Dict],
    new_rows: List[Dict],
) -> Tuple[List[Dict], int, int]:
    """
    Smart merge: add new projects, skip duplicates.

    Duplicate detection:
      1. Exact normalized name match
      2. Exact website domain match

    Returns:
        (merged_rows, added_count, duplicate_count)
    """
    # Build lookup sets from existing data
    name_set = set()
    domain_set = set()

    for row in existing_rows:
        name = normalize_name(row.get("Project Name", ""))
        if name:
            name_set.add(name)
        domain = extract_domain(row.get("Website", ""))
        if domain:
            domain_set.add(domain)

    added = 0
    duplicates = 0

    for row in new_rows:
        name = normalize_name(row.get("Project Name", ""))
        domain = extract_domain(row.get("Website", ""))

        is_dupe = False
        if name and name in name_set:
            is_dupe = True
        elif domain and domain in domain_set:
            is_dupe = True

        if is_dupe:
            duplicates += 1
        else:
            existing_rows.append(row)
            if name:
                name_set.add(name)
            if domain:
                domain_set.add(domain)
            added += 1

    return existing_rows, added, duplicates
