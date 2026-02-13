#!/usr/bin/env python3
"""
Website health checker — HTTP HEAD check for all project websites.

Detects dead/stale projects by checking if their website returns a
successful HTTP response. Records the HTTP status code and flags
dead sites for data quality review.

Classification:
  - "alive"   : 2xx or 3xx response
  - "dead"    : 4xx or 5xx response (404, 403, 500, 502, 503, etc.)
  - "timeout" : no response within REQUEST_TIMEOUT seconds
  - "dns_fail": domain doesn't resolve
  - "error"   : SSL error, connection refused, or other failure
  - "no_url"  : no fetchable website URL in the row

Results are stored in the Notes column as [website-health] markers
and in Evidence as "health-check: <status>".

Usage:
    python scripts/check_websites.py --chain near --dry-run --limit 10
    python scripts/check_websites.py --chain near
    python scripts/check_websites.py --chain near --recheck-dead
"""

import argparse
import json
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.csv_utils import load_csv, write_csv, find_main_csv
from lib.logging_config import get_logger

logger = get_logger(__name__)

# ── HTTP settings ────────────────────────────────────────────────────────

USER_AGENT = "EcosystemResearch/1.0 (health-check)"
REQUEST_TIMEOUT = 8  # seconds — HEAD requests should be fast
REQUEST_DELAY = 0.3  # seconds between requests (polite crawling)
MAX_RETRIES = 1

# Incremental marker
HEALTH_MARKER = "health-check:"

# ── Status classification ────────────────────────────────────────────────

STATUS_ALIVE = "alive"
STATUS_DEAD = "dead"
STATUS_TIMEOUT = "timeout"
STATUS_DNS_FAIL = "dns_fail"
STATUS_ERROR = "error"
STATUS_NO_URL = "no_url"

DEAD_STATUSES = {STATUS_DEAD, STATUS_TIMEOUT, STATUS_DNS_FAIL, STATUS_ERROR}


def classify_status(code: Optional[int], error_type: str = "") -> str:
    """Classify an HTTP response into a health status."""
    if code is not None:
        if 200 <= code < 400:
            return STATUS_ALIVE
        else:
            return STATUS_DEAD
    # No code means an exception occurred
    if error_type == "timeout":
        return STATUS_TIMEOUT
    if error_type == "dns":
        return STATUS_DNS_FAIL
    return STATUS_ERROR


# ── URL helpers ──────────────────────────────────────────────────────────

def is_fetchable_url(url: str) -> bool:
    """Check if a URL is safe to health-check."""
    url = url.strip()
    if not url:
        return False
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host or host in ("localhost", "127.0.0.1", "0.0.0.0"):
            return False
        if host.replace(".", "").isdigit():
            return False
        if parsed.scheme not in ("http", "https"):
            return False
        return True
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """Ensure URL has a scheme."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


# ── HTTP health check ───────────────────────────────────────────────────

def check_website(url: str) -> Tuple[str, Optional[int], str]:
    """
    Check if a website is alive using HTTP HEAD (falls back to GET).

    Returns (status, http_code, detail_message).
    """
    url = normalize_url(url)

    # Relaxed SSL context (some project sites have expired certs)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for attempt in range(MAX_RETRIES + 1):
        try:
            # Try HEAD first (faster, less bandwidth)
            req = urllib.request.Request(url, method="HEAD", headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
            })
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
                code = resp.getcode()
                status = classify_status(code)
                return status, code, f"HTTP {code}"

        except urllib.error.HTTPError as e:
            code = e.code
            # Some servers return 405 Method Not Allowed for HEAD
            if code == 405 and attempt == 0:
                # Fall back to GET
                try:
                    req = urllib.request.Request(url, headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html,*/*",
                    })
                    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
                        code = resp.getcode()
                        status = classify_status(code)
                        return status, code, f"HTTP {code} (GET fallback)"
                except urllib.error.HTTPError as e2:
                    return classify_status(e2.code), e2.code, f"HTTP {e2.code}"
                except Exception:
                    pass  # Fall through to retry

            if code >= 500 and attempt < MAX_RETRIES:
                time.sleep(1)
                continue
            return classify_status(code), code, f"HTTP {code}"

        except socket.timeout:
            if attempt < MAX_RETRIES:
                time.sleep(1)
                continue
            return STATUS_TIMEOUT, None, "timeout"

        except urllib.error.URLError as e:
            reason = str(e.reason) if e.reason else str(e)
            # DNS resolution failure
            if "getaddrinfo" in reason or "Name or service not known" in reason or "nodename nor servname" in reason:
                return STATUS_DNS_FAIL, None, f"DNS: {reason[:80]}"
            if "timed out" in reason:
                if attempt < MAX_RETRIES:
                    time.sleep(1)
                    continue
                return STATUS_TIMEOUT, None, "timeout"
            if attempt < MAX_RETRIES:
                time.sleep(1)
                continue
            return STATUS_ERROR, None, reason[:100]

        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(1)
                continue
            return STATUS_ERROR, None, str(e)[:100]

    return STATUS_ERROR, None, "max retries exceeded"


# ── Row processing ──────────────────────────────────────────────────────

def get_existing_health(row: Dict) -> Optional[str]:
    """Extract existing health-check status from Evidence column."""
    evidence = row.get("Evidence & Source URLs", "")
    match = re.search(r"health-check:\s*(\w+)", evidence)
    if match:
        return match.group(1)
    return None


def should_check_row(row: Dict, recheck_dead: bool = False) -> bool:
    """Determine if a row needs a health check."""
    website = row.get("Website", "").strip()
    if not website or not is_fetchable_url(website):
        return False

    existing = get_existing_health(row)
    if existing is None:
        return True  # Never checked
    if recheck_dead and existing in DEAD_STATUSES:
        return True  # Re-check dead sites
    return False


def update_row_health(row: Dict, status: str, http_code: Optional[int], detail: str) -> None:
    """Update a row's Evidence and Notes with health check results."""
    evidence = row.get("Evidence & Source URLs", "").strip()
    code_str = str(http_code) if http_code else status

    # Remove old health-check marker if present
    evidence = re.sub(r"\s*\|?\s*health-check:\s*\S+(\s*\(\S+\))?", "", evidence).strip()
    evidence = re.sub(r"^\|\s*", "", evidence).strip()

    # Add new marker
    marker = f"health-check: {status} ({code_str})"
    if evidence:
        row["Evidence & Source URLs"] = f"{evidence} | {marker}"
    else:
        row["Evidence & Source URLs"] = marker

    # For dead sites, add a note
    if status in DEAD_STATUSES:
        notes = row.get("Notes", "").strip()
        # Remove old health note
        notes = re.sub(r"\s*\[website-health\][^|]*", "", notes).strip()
        notes = re.sub(r"^\|\s*", "", notes).strip()

        health_note = f"[website-health] DEAD: {detail}"
        if notes:
            row["Notes"] = f"{notes} | {health_note}"
        else:
            row["Notes"] = health_note


# ── Main enrichment function ────────────────────────────────────────────

def check_all_websites(
    csv_path: Path,
    chain: str,
    dry_run: bool = False,
    limit: int = 0,
    recheck_dead: bool = False,
) -> Dict:
    """
    Run health checks on all project websites.

    Returns dict with counts: total, checked, alive, dead, timeout,
    dns_fail, error, no_url, skipped.
    """
    rows = load_csv(csv_path)
    total = len(rows)

    # Count eligible rows
    eligible = [(i, rows[i]) for i in range(total) if should_check_row(rows[i], recheck_dead)]
    no_url = sum(1 for r in rows if not is_fetchable_url(r.get("Website", "").strip()))

    if limit > 0:
        eligible = eligible[:limit]

    already_checked = sum(1 for r in rows if get_existing_health(r) is not None)

    print(f"Loading CSV: {csv_path}")
    print(f"  {total} rows, {already_checked} already checked, {len(eligible)} to check, {no_url} no URL")

    counts = {
        "alive": 0, "dead": 0, "timeout": 0,
        "dns_fail": 0, "error": 0,
    }
    checked = 0

    for idx_num, (row_idx, row) in enumerate(eligible):
        name = row.get("Project Name", "").strip()
        website = row.get("Website", "").strip()

        print(f"  [{idx_num + 1}/{len(eligible)}] {name} → {website}", end="", flush=True)

        if checked > 0:
            time.sleep(REQUEST_DELAY)

        status, http_code, detail = check_website(website)
        checked += 1
        counts[status] = counts.get(status, 0) + 1

        # Display result
        if status == STATUS_ALIVE:
            print(f" ✓ {detail}")
        else:
            print(f" ✗ {status}: {detail}")

        # Update row
        if not dry_run:
            update_row_health(row, status, http_code, detail)

    # Write CSV
    if not dry_run and checked > 0:
        write_csv(rows, csv_path)
        print(f"\nCSV updated: {csv_path}")

    result = {
        "total": total,
        "checked": checked,
        "alive": counts.get("alive", 0),
        "dead": counts.get("dead", 0),
        "timeout": counts.get("timeout", 0),
        "dns_fail": counts.get("dns_fail", 0),
        "error": counts.get("error", 0),
        "no_url": no_url,
        "skipped": already_checked,
    }

    return result


# ── Pipeline integration ────────────────────────────────────────────────

def run_health_check(csv_path: Path, chain: str, dry_run: bool = False,
                     **kwargs) -> Dict:
    """Pipeline-compatible wrapper for check_all_websites."""
    return check_all_websites(csv_path, chain, dry_run=dry_run)


# ── CLI ─────────────────────────────────────────────────────────────────

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
        description="Check project website health (HTTP HEAD)"
    )
    parser.add_argument("--chain", required=True, help="Chain ID (e.g., near)")
    parser.add_argument("--csv", help="Path to CSV (auto-detected if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only first N eligible rows")
    parser.add_argument("--recheck-dead", action="store_true",
                        help="Re-check sites previously flagged as dead")
    args = parser.parse_args()

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

    result = check_all_websites(
        csv_path, args.chain,
        dry_run=args.dry_run,
        limit=args.limit,
        recheck_dead=args.recheck_dead,
    )

    print(f"\n{'='*60}")
    print(f"WEBSITE HEALTH CHECK SUMMARY")
    print(f"{'='*60}")
    print(f"Total rows:     {result['total']}")
    print(f"Checked:        {result['checked']}")
    print(f"  Alive:        {result['alive']}")
    print(f"  Dead:         {result['dead']}")
    print(f"  Timeout:      {result['timeout']}")
    print(f"  DNS Fail:     {result['dns_fail']}")
    print(f"  Error:        {result['error']}")
    print(f"No URL:         {result['no_url']}")
    print(f"Already checked:{result['skipped']}")

    dead_total = result['dead'] + result['timeout'] + result['dns_fail'] + result['error']
    if result['checked'] > 0:
        print(f"Dead rate:      {dead_total}/{result['checked']} ({dead_total/result['checked']*100:.1f}%)")

    if args.dry_run:
        print(f"\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
