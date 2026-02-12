#!/usr/bin/env python3
"""
Promote high-confidence website-scan hints into boolean research columns.

Reads [UNVERIFIED website-scan] entries from the Notes column and applies
rule-based promotion strategies to set Suspect USDT support?,
General Stablecoin Adoption, and Web3 but no stablecoin columns.

This step is intentionally separate from website keyword scanning
(enrich_website_keywords.py) to maintain the scan/promote separation.

Usage:
    python scripts/promote_hints.py --chain near --dry-run
    python scripts/promote_hints.py --chain near
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.csv_utils import load_csv, write_csv, find_main_csv


# ── Constants ─────────────────────────────────────────────────

PROMOTE_MARKER = "promoted: website-scan"
UNVERIFIED_TAG = "[UNVERIFIED website-scan]"
PROMOTED_TAG = "[PROMOTED from website-scan]"

# Pattern matching scan-block segments
SCAN_PATTERNS = re.compile(
    r"(USDT|USDC|SOL|STRK|ADA|APT|ETH|BTC)\s+keywords|"
    r"stablecoin mentions|"
    r"web3\("
)


# ── Note Parsing ──────────────────────────────────────────────

def parse_scan_note(notes: str) -> Dict:
    """
    Parse [UNVERIFIED website-scan] content from a Notes field.

    Returns dict with scan findings: has_usdt, has_usdc,
    has_stablecoin_mention, has_web3_signal, asset_count.
    """
    result = {
        "has_scan": False,
        "has_usdt": False,
        "has_usdc": False,
        "has_stablecoin_mention": False,
        "has_web3_signal": False,
        "asset_count": 0,
    }

    if UNVERIFIED_TAG not in notes:
        return result

    result["has_scan"] = True

    # Split Notes on " | " and find the scan block
    parts = notes.split(" | ")
    scan_start = None
    for i, part in enumerate(parts):
        if UNVERIFIED_TAG in part:
            scan_start = i
            break

    if scan_start is None:
        return result

    # Collect scan-block segments (tag segment + subsequent matching segments)
    scan_parts = []
    for i in range(scan_start, len(parts)):
        part = parts[i].strip()
        if i == scan_start:
            scan_parts.append(part)
        elif SCAN_PATTERNS.search(part):
            scan_parts.append(part)
        else:
            break

    full_text = " | ".join(scan_parts)
    asset_types = set()

    if "USDT keywords" in full_text:
        result["has_usdt"] = True
        asset_types.add("USDT")
    if "USDC keywords" in full_text:
        result["has_usdc"] = True
        asset_types.add("USDC")
    if "stablecoin mentions" in full_text:
        result["has_stablecoin_mention"] = True
    if "web3(" in full_text.lower():
        result["has_web3_signal"] = True

    for asset in ("SOL", "STRK", "ADA", "APT", "ETH", "BTC"):
        if f"{asset} keywords" in full_text:
            asset_types.add(asset)

    result["asset_count"] = len(asset_types)
    return result


# ── Promotion Strategies ──────────────────────────────────────

def _is_true(val: str) -> bool:
    return val.strip().upper() in ("TRUE", "YES", "1")


def apply_strategy_usdt(row: Dict, scan: Dict) -> Tuple[Dict, str]:
    """
    Strategy 1: USDT keywords → Suspect USDT support? = TRUE

    If USDC also present, also set General Stablecoin Adoption.
    Clears Web3 but no stablecoin (matches Grid/DefiLlama pattern).
    """
    if not scan["has_usdt"]:
        return {}, ""
    if _is_true(row.get("Suspect USDT support?", "")):
        return {}, ""

    updates = {
        "Suspect USDT support?": "TRUE",
        "Web3 but no stablecoin": "",
    }
    label = "USDT → Suspect USDT"

    if scan["has_usdc"]:
        updates["General Stablecoin Adoption"] = "TRUE"
        label = "USDT+USDC → Suspect USDT + General Stablecoin"

    return updates, label


def apply_strategy_general_stablecoin(row: Dict, scan: Dict) -> Tuple[Dict, str]:
    """
    Strategy 2: USDC/stablecoin (no USDT) → General Stablecoin Adoption = TRUE

    Only fires when USDT keywords are absent.
    """
    if scan["has_usdt"]:
        return {}, ""

    if not (scan["has_usdc"] or scan["has_stablecoin_mention"]):
        return {}, ""

    if _is_true(row.get("Suspect USDT support?", "")):
        return {}, ""
    if _is_true(row.get("General Stablecoin Adoption", "")):
        return {}, ""

    updates = {
        "General Stablecoin Adoption": "TRUE",
        "Web3 but no stablecoin": "",
    }
    source = "USDC" if scan["has_usdc"] else "stablecoin"
    return updates, f"{source} → General Stablecoin"


def apply_strategy_web3(row: Dict, scan: Dict) -> Tuple[Dict, str]:
    """
    Strategy 3: Web3 signals only → Web3 but no stablecoin = TRUE

    Only fires when no stablecoin/USDT/USDC signals are present.
    """
    if scan["has_usdt"] or scan["has_usdc"] or scan["has_stablecoin_mention"]:
        return {}, ""
    if not scan["has_web3_signal"]:
        return {}, ""
    if _is_true(row.get("Web3 but no stablecoin", "")):
        return {}, ""
    if _is_true(row.get("Suspect USDT support?", "")):
        return {}, ""

    return {"Web3 but no stablecoin": "TRUE"}, "web3 → Web3 (no stablecoin)"


# ── Notes & Evidence helpers ──────────────────────────────────

def annotate_notes(row: Dict) -> None:
    """Replace [UNVERIFIED website-scan] with [PROMOTED from website-scan]."""
    notes = row.get("Notes", "")
    if UNVERIFIED_TAG in notes:
        row["Notes"] = notes.replace(UNVERIFIED_TAG, PROMOTED_TAG)


def add_promote_marker(row: Dict) -> None:
    """Add promotion marker to Evidence for incremental skip."""
    evidence = row.get("Evidence & Source URLs", "").strip()
    if PROMOTE_MARKER not in evidence:
        if evidence:
            row["Evidence & Source URLs"] = f"{evidence} | {PROMOTE_MARKER}"
        else:
            row["Evidence & Source URLs"] = PROMOTE_MARKER


# ── Main enrichment function ─────────────────────────────────

def promote_hints(
    csv_path: Path,
    chain: str,
    dry_run: bool = False,
) -> Tuple[int, int, int, int, int]:
    """
    Promote high-confidence website-scan hints to boolean columns.

    Returns (total_rows, candidates, promoted_usdt, promoted_stablecoin, promoted_web3).
    """
    rows = load_csv(csv_path)
    total = len(rows)

    strategies = [
        apply_strategy_usdt,
        apply_strategy_general_stablecoin,
        apply_strategy_web3,
    ]

    candidates = 0
    promoted_usdt = 0
    promoted_stablecoin = 0
    promoted_web3 = 0
    any_changes = False

    print(f"Scanning {total} rows for promotable website-scan hints...\n")

    for row in rows:
        notes = row.get("Notes", "")
        evidence = row.get("Evidence & Source URLs", "")

        # Skip: no unverified scan tag
        if UNVERIFIED_TAG not in notes:
            continue

        # Skip: already promoted
        if PROMOTE_MARKER in evidence:
            continue

        candidates += 1
        name = row.get("Project Name", "").strip()
        scan = parse_scan_note(notes)

        if not scan["has_scan"]:
            continue

        # Try strategies in order (first match wins)
        updates = {}
        label = ""
        for strategy in strategies:
            updates, label = strategy(row, scan)
            if updates:
                break

        confidence = "high" if scan["asset_count"] >= 2 else "standard"

        if updates:
            # Count by strategy type
            if "Suspect USDT support?" in updates:
                promoted_usdt += 1
            elif "General Stablecoin Adoption" in updates:
                promoted_stablecoin += 1
            elif "Web3 but no stablecoin" in updates:
                promoted_web3 += 1

            prefix = "[DRY] " if dry_run else ""
            print(f"  {prefix}{name} → {label} ({confidence} confidence, {scan['asset_count']} assets)")

            if not dry_run:
                row.update(updates)
                annotate_notes(row)
                add_promote_marker(row)
                any_changes = True
        else:
            # No strategy fired (columns already set), but still mark as processed
            if not dry_run:
                annotate_notes(row)
                add_promote_marker(row)
                any_changes = True

    if any_changes and not dry_run:
        write_csv(rows, csv_path)
        print(f"\nEnriched CSV written to: {csv_path}")

    return total, candidates, promoted_usdt, promoted_stablecoin, promoted_web3


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Promote high-confidence website-scan hints to boolean columns"
    )
    parser.add_argument("--chain", required=True, help="Chain ID (e.g., near)")
    parser.add_argument("--csv", help="Path to CSV (auto-detected if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview promotions without writing")
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

    total, candidates, usdt, stablecoin, web3 = promote_hints(
        csv_path, args.chain, dry_run=args.dry_run,
    )

    print(f"\n{'='*60}")
    print(f"HINT PROMOTION SUMMARY")
    print(f"{'='*60}")
    print(f"Total rows:              {total}")
    print(f"Candidates (unverified): {candidates}")
    print(f"Promoted (USDT):         {usdt}")
    print(f"Promoted (Stablecoin):   {stablecoin}")
    print(f"Promoted (Web3):         {web3}")
    print(f"Total promoted:          {usdt + stablecoin + web3}")

    if args.dry_run:
        print(f"\n[DRY RUN] Re-run without --dry-run to write results.")


if __name__ == "__main__":
    main()
