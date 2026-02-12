#!/usr/bin/env python3
"""
Unified enrichment runner — runs all enrichment + cleanup steps in sequence.

Orchestrates:
  1. Dedup (remove duplicate rows)
  2. Grid asset enrichment (query Grid API for matched rows)
  3. DefiLlama enrichment (token holdings + chain presence)
  4. CoinGecko enrichment (batch platform deployments)
  5. Notes cleanup (strip prefixes, emojis, fluff)

Each step reads the same CSV, enriches in place, and writes back.
Use --skip to skip specific steps. Use --dry-run to preview all steps.

Usage:
    python scripts/enrich_all.py --chain near
    python scripts/enrich_all.py --chain near --dry-run
    python scripts/enrich_all.py --chain near --skip dedup,notes
    python scripts/enrich_all.py --chain near --only grid,coingecko
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.csv_utils import find_main_csv, load_csv

# Lazy imports — only import each module when its step runs,
# so a broken step doesn't block the others.

STEPS = ["dedup", "grid", "defillama", "coingecko", "notes"]

STEP_DESCRIPTIONS = {
    "dedup": "Deduplicate rows (normalized name + website domain)",
    "grid": "Grid API asset enrichment (matched rows only)",
    "defillama": "DefiLlama token holdings + chain presence",
    "coingecko": "CoinGecko batch platform deployments",
    "notes": "Notes cleanup (strip prefixes, emojis, fluff)",
}


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


def run_step_dedup(csv_path: Path, dry_run: bool, **kwargs) -> dict:
    """Run deduplication step."""
    from scripts.dedup_csv import dedup_csv
    total, unique, exact, fuzzy = dedup_csv(csv_path, dry_run=dry_run)
    return {
        "total": total,
        "unique": unique,
        "exact_removed": exact,
        "fuzzy_removed": fuzzy,
    }


def run_step_grid(csv_path: Path, chain: str, target_assets: list,
                  dry_run: bool, **kwargs) -> dict:
    """Run Grid API asset enrichment."""
    from scripts.enrich_grid_assets import enrich_from_grid
    total, enriched, skipped = enrich_from_grid(
        csv_path, chain, target_assets, dry_run=dry_run,
    )
    return {"total": total, "enriched": enriched, "skipped": skipped}


def run_step_defillama(csv_path: Path, chain: str, target_assets: list,
                       dry_run: bool, **kwargs) -> dict:
    """Run DefiLlama enrichment."""
    from scripts.enrich_assets import enrich_csv
    total, matched, enriched = enrich_csv(
        csv_path, chain, target_assets, dry_run=dry_run,
    )
    return {"total": total, "matched": matched, "enriched": enriched}


def run_step_coingecko(csv_path: Path, chain: str, target_assets: list,
                       dry_run: bool, **kwargs) -> dict:
    """Run CoinGecko batch enrichment."""
    from scripts.enrich_coingecko import enrich_csv
    total, matched, enriched = enrich_csv(
        csv_path, chain, target_assets, dry_run=dry_run,
    )
    return {"total": total, "matched": matched, "enriched": enriched}


def run_step_notes(csv_path: Path, dry_run: bool, **kwargs) -> dict:
    """Run Notes cleanup."""
    from scripts.clean_notes import run_cleanup
    total, cleaned, unchanged = run_cleanup(csv_path, dry_run=dry_run)
    return {"total": total, "cleaned": cleaned, "unchanged": unchanged}


STEP_RUNNERS = {
    "dedup": run_step_dedup,
    "grid": run_step_grid,
    "defillama": run_step_defillama,
    "coingecko": run_step_coingecko,
    "notes": run_step_notes,
}


def main():
    parser = argparse.ArgumentParser(
        description="Run all enrichment + cleanup steps in sequence"
    )
    parser.add_argument("--chain", required=True, help="Chain ID (e.g., near)")
    parser.add_argument("--csv", help="Path to CSV (auto-detected if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview all steps without writing")
    parser.add_argument("--skip", default="",
                        help="Comma-separated steps to skip (e.g., dedup,notes)")
    parser.add_argument("--only", default="",
                        help="Comma-separated steps to run (overrides --skip)")
    parser.add_argument("--assets",
                        help="Override target assets (comma-separated, e.g., USDT,USDC)")
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

    # Load chain config
    chain_config = load_chain_config(args.chain)
    target_assets = (
        args.assets.split(",") if args.assets
        else chain_config.get("target_assets", ["USDT", "USDC"])
    )

    # Determine which steps to run
    if args.only:
        steps_to_run = [s.strip() for s in args.only.split(",")]
        for s in steps_to_run:
            if s not in STEPS:
                print(f"Error: Unknown step '{s}'. Valid: {', '.join(STEPS)}")
                sys.exit(1)
    else:
        skip = set(s.strip() for s in args.skip.split(",") if s.strip())
        steps_to_run = [s for s in STEPS if s not in skip]

    # Show plan
    rows = load_csv(csv_path)
    print(f"{'='*60}")
    print(f"ENRICHMENT PIPELINE — {args.chain.upper()}")
    print(f"{'='*60}")
    print(f"CSV: {csv_path} ({len(rows)} rows)")
    print(f"Target assets: {', '.join(target_assets)}")
    print(f"Steps: {' → '.join(steps_to_run)}")
    if args.dry_run:
        print(f"Mode: DRY RUN (no files written)")
    print()

    # Run each step
    results = {}
    total_start = time.time()

    for step in steps_to_run:
        desc = STEP_DESCRIPTIONS[step]
        print(f"{'─'*60}")
        print(f"STEP: {step} — {desc}")
        print(f"{'─'*60}")

        step_start = time.time()
        runner = STEP_RUNNERS[step]

        try:
            result = runner(
                csv_path=csv_path,
                chain=args.chain,
                target_assets=target_assets,
                dry_run=args.dry_run,
            )
            elapsed = time.time() - step_start
            result["elapsed"] = f"{elapsed:.1f}s"
            results[step] = result
            print(f"  ✓ {step} completed in {elapsed:.1f}s")
        except Exception as e:
            elapsed = time.time() - step_start
            results[step] = {"error": str(e), "elapsed": f"{elapsed:.1f}s"}
            print(f"  ✗ {step} FAILED in {elapsed:.1f}s: {e}")
            import traceback
            traceback.print_exc()

        print()

    # Summary
    total_elapsed = time.time() - total_start
    print(f"{'='*60}")
    print(f"PIPELINE SUMMARY — {total_elapsed:.1f}s total")
    print(f"{'='*60}")

    for step in steps_to_run:
        r = results.get(step, {})
        if "error" in r:
            print(f"  {step}: FAILED — {r['error']}")
        else:
            # Format result nicely
            parts = [f"{k}={v}" for k, v in r.items() if k != "elapsed"]
            print(f"  {step}: {', '.join(parts)} ({r.get('elapsed', '?')})")

    if args.dry_run:
        print(f"\n[DRY RUN] No files were written. Re-run without --dry-run.")


if __name__ == "__main__":
    main()
