#!/usr/bin/env python3
"""
Unified enrichment runner — runs all enrichment + cleanup steps in sequence.

Orchestrates:
  1. Dedup (remove duplicate rows)
  2. Expand Grid matching (batch name + URL against all profiles/products)
  3. Grid asset enrichment (query Grid API for matched rows)
  4. DefiLlama enrichment (token holdings + chain presence)
  4. CoinGecko enrichment (batch platform deployments)
  5. Website keyword scan (homepage HTML for asset/stablecoin keywords)
  6. Hint promotion (promote website-scan findings to boolean columns)
  7. Notes cleanup (strip prefixes, emojis, fluff)

Each step reads the same CSV, enriches in place, and writes back.
Use --skip to skip specific steps. Use --dry-run to preview all steps.

Safety features:
  - Pre-pipeline backup (never deleted — ultimate safety net)
  - Per-step checkpoints (deleted on success, available for rollback)
  - --stop-on-error: halt pipeline on first step failure
  - --rollback-on-error: restore CSV from checkpoint when a step fails
  - Structured logging to data/<chain>/pipeline.log

Usage:
    python scripts/enrich_all.py --chain near
    python scripts/enrich_all.py --chain near --dry-run
    python scripts/enrich_all.py --chain near --skip dedup,notes
    python scripts/enrich_all.py --chain near --only grid,coingecko
    python scripts/enrich_all.py --chain near --stop-on-error --rollback-on-error
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import shutil

from lib.csv_utils import find_main_csv, load_csv, backup_csv
from lib.logging_config import get_logger, configure_logging

logger = get_logger(__name__)

# Lazy imports — only import each module when its step runs,
# so a broken step doesn't block the others.

STEPS = ["dedup", "expand-grid", "grid", "defillama", "coingecko", "website", "promote", "notes", "sources"]

STEP_DESCRIPTIONS = {
    "dedup": "Deduplicate rows (normalized name + website domain)",
    "expand-grid": "Expand Grid matching (batch name + URL against all profiles/products)",
    "grid": "Grid API asset enrichment (matched rows only)",
    "defillama": "DefiLlama token holdings + chain presence",
    "coingecko": "CoinGecko batch platform deployments",
    "website": "Website keyword scan (homepage HTML for asset/stablecoin keywords)",
    "promote": "Promote high-confidence website-scan hints to boolean columns",
    "notes": "Notes cleanup (strip prefixes, emojis, fluff)",
    "sources": "Fix Source column (replace 'Generic Scraper' with actual source)",
}


def load_chain_config(chain: str) -> dict:
    """Load chain config from config/chains.json."""
    config_path = Path(__file__).parent.parent / "config" / "chains.json"
    with open(config_path) as f:
        config = json.load(f)
    for c in config["chains"]:
        if c["id"] == chain:
            return c
    logger.error("Chain '%s' not found in config/chains.json", chain)
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


def run_step_expand_grid(csv_path: Path, chain: str, dry_run: bool, **kwargs) -> dict:
    """Expand Grid matching with batch name + URL strategies."""
    from scripts.expand_grid_matches import expand_matches
    total, unmatched, matched, counts = expand_matches(
        csv_path, chain,
        strategies=["batch-name", "batch-url"],
        dry_run=dry_run,
    )
    return {
        "total": total, "unmatched_before": unmatched,
        "newly_matched": matched,
        **{f"via_{k}": v for k, v in counts.items()},
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


def run_step_website(csv_path: Path, chain: str, target_assets: list,
                     dry_run: bool, **kwargs) -> dict:
    """Run website keyword scan enrichment."""
    from scripts.enrich_website_keywords import enrich_csv
    total, scanned, found, errors = enrich_csv(
        csv_path, chain, target_assets, dry_run=dry_run,
    )
    return {
        "total": total, "scanned": scanned,
        "keywords_found": found, "fetch_errors": errors,
    }


def run_step_promote(csv_path: Path, chain: str, dry_run: bool, **kwargs) -> dict:
    """Promote high-confidence website-scan hints to boolean columns."""
    from scripts.promote_hints import promote_hints
    total, candidates, usdt, stablecoin, web3 = promote_hints(
        csv_path, chain, dry_run=dry_run,
    )
    return {
        "total": total, "candidates": candidates,
        "promoted_usdt": usdt, "promoted_stablecoin": stablecoin,
        "promoted_web3": web3,
    }


def run_step_notes(csv_path: Path, dry_run: bool, **kwargs) -> dict:
    """Run Notes cleanup."""
    from scripts.clean_notes import run_cleanup
    total, cleaned, unchanged = run_cleanup(csv_path, dry_run=dry_run)
    return {"total": total, "cleaned": cleaned, "unchanged": unchanged}


def run_step_sources(csv_path: Path, chain: str, dry_run: bool, **kwargs) -> dict:
    """Fix 'Generic Scraper' in Source column."""
    from scripts.fix_source_column import fix_sources
    total, fixed, ok = fix_sources(csv_path, chain, dry_run=dry_run)
    return {"total": total, "fixed": fixed, "already_ok": ok}


STEP_RUNNERS = {
    "dedup": run_step_dedup,
    "expand-grid": run_step_expand_grid,
    "grid": run_step_grid,
    "defillama": run_step_defillama,
    "coingecko": run_step_coingecko,
    "website": run_step_website,
    "promote": run_step_promote,
    "notes": run_step_notes,
    "sources": run_step_sources,
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
    parser.add_argument("--stop-on-error", action="store_true",
                        help="Stop pipeline on first step failure")
    parser.add_argument("--rollback-on-error", action="store_true",
                        help="Restore CSV from checkpoint when a step fails")
    args = parser.parse_args()

    # Configure logging (file logging only when not dry-run)
    log_file = None
    if not args.dry_run:
        data_dir = Path(__file__).parent.parent / "data" / args.chain.lower()
        if data_dir.exists():
            log_file = data_dir / "pipeline.log"
    configure_logging(log_file=log_file)

    # Resolve CSV path
    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_path = find_main_csv(args.chain)
        if not csv_path:
            logger.error("No CSV found in data/%s/", args.chain)
            sys.exit(1)

    if not csv_path.exists():
        logger.error("CSV not found: %s", csv_path)
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
                logger.error("Unknown step '%s'. Valid: %s", s, ", ".join(STEPS))
                sys.exit(1)
    else:
        skip = set(s.strip() for s in args.skip.split(",") if s.strip())
        steps_to_run = [s for s in STEPS if s not in skip]

    # Show plan
    rows = load_csv(csv_path)
    logger.info("=" * 60)
    logger.info("ENRICHMENT PIPELINE — %s", args.chain.upper())
    logger.info("=" * 60)
    logger.info("CSV: %s (%d rows)", csv_path, len(rows))
    logger.info("Target assets: %s", ", ".join(target_assets))
    logger.info("Steps: %s", " → ".join(steps_to_run))
    if args.dry_run:
        logger.info("Mode: DRY RUN (no files written)")
    if args.stop_on_error:
        logger.info("Mode: --stop-on-error (halt on first failure)")
    if args.rollback_on_error:
        logger.info("Mode: --rollback-on-error (restore checkpoint on failure)")

    # Pre-pipeline backup (safety net — never deleted)
    if not args.dry_run:
        pipeline_backup = backup_csv(csv_path, suffix="pre-pipeline")
        logger.info("Backup: %s", pipeline_backup.name)
    else:
        pipeline_backup = None

    # Run each step
    results = {}
    total_start = time.time()
    pipeline_halted = False

    for step in steps_to_run:
        desc = STEP_DESCRIPTIONS[step]
        logger.info("─" * 60)
        logger.info("STEP: %s — %s", step, desc)
        logger.info("─" * 60)

        # Per-step checkpoint (deleted on success, used for rollback on failure)
        checkpoint = None
        if not args.dry_run:
            checkpoint = backup_csv(csv_path, suffix=f"pre-{step}")

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
            logger.info("  ✓ %s completed in %.1fs", step, elapsed)

            # Delete checkpoint on success (keeps disk tidy)
            if checkpoint and checkpoint.exists():
                checkpoint.unlink()

        except Exception as e:
            elapsed = time.time() - step_start
            results[step] = {"error": str(e), "elapsed": f"{elapsed:.1f}s"}
            logger.error("  ✗ %s FAILED in %.1fs: %s", step, elapsed, e, exc_info=True)

            # Rollback: restore CSV from checkpoint
            if args.rollback_on_error and checkpoint and checkpoint.exists():
                shutil.copy2(checkpoint, csv_path)
                logger.warning("  ↩ Rolled back CSV to pre-%s checkpoint", step)

            # Stop: halt pipeline on first failure
            if args.stop_on_error:
                logger.warning("  ⛔ Pipeline halted (--stop-on-error)")
                pipeline_halted = True
                break

    # Summary
    total_elapsed = time.time() - total_start
    logger.info("=" * 60)
    logger.info("PIPELINE SUMMARY — %.1fs total", total_elapsed)
    logger.info("=" * 60)

    for step in steps_to_run:
        r = results.get(step, {})
        if "error" in r:
            logger.info("  %s: FAILED — %s", step, r["error"])
        else:
            parts = [f"{k}={v}" for k, v in r.items() if k != "elapsed"]
            logger.info("  %s: %s (%s)", step, ", ".join(parts), r.get("elapsed", "?"))

    if pipeline_halted:
        logger.warning("Pipeline was halted early due to step failure.")
    if pipeline_backup:
        logger.info("Pre-pipeline backup: %s", pipeline_backup)
    if args.dry_run:
        logger.info("[DRY RUN] No files were written. Re-run without --dry-run.")


if __name__ == "__main__":
    main()
