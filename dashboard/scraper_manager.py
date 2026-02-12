"""
Thread-safe background discovery job executor.

Mirrors pipeline_manager.py: runs discovery in a daemon thread,
exposes progress via get_job() for API polling.

Usage:
    from dashboard.scraper_manager import scraper_manager

    job_id = scraper_manager.start_discovery(
        chain="solana",
        sources=["defillama"],
    )

    job = scraper_manager.get_job(job_id)
    print(job["status"], job["progress_message"])
"""

import json
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.csv_utils import find_main_csv, load_csv, write_csv
from lib.columns import CORRECT_COLUMNS
from lib.logging_config import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "chains.json"


@dataclass
class DiscoveryJob:
    """State of a discovery run."""

    job_id: str
    chain: str
    sources: List[str]
    status: str = "pending"  # pending | running | completed | failed
    progress: int = 0
    progress_total: int = 0
    progress_message: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    total_elapsed: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "chain": self.chain,
            "sources": self.sources,
            "status": self.status,
            "progress": self.progress,
            "progress_total": self.progress_total,
            "progress_message": self.progress_message,
            "result": self.result,
            "error": self.error,
            "total_elapsed": (
                round(self.total_elapsed, 1) if self.total_elapsed else None
            ),
        }


class ScraperManager:
    """
    Manages background discovery execution.

    Thread-safe: all state reads/writes go through self._lock.
    Only one discovery can run at a time (self._running flag).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._jobs: Dict[str, DiscoveryJob] = {}

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start_discovery(self, chain: str, sources: List[str]) -> str:
        """
        Start discovery in a background thread.

        Returns job_id. Raises RuntimeError if already running.
        """
        with self._lock:
            if self._running:
                raise RuntimeError("A discovery job is already running")
            self._running = True

        job_id = uuid.uuid4().hex[:8]
        job = DiscoveryJob(
            job_id=job_id,
            chain=chain,
            sources=sources,
        )

        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_discovery,
            args=(job,),
            daemon=True,
            name=f"discovery-{job_id}",
        )
        thread.start()
        logger.info(
            "Discovery %s started for chain=%s, sources=%s",
            job_id,
            chain,
            sources,
        )
        return job_id

    def get_job(self, job_id: str) -> Optional[dict]:
        """Get job status as a dict (thread-safe snapshot)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return job.to_dict()

    def _run_discovery(self, job: DiscoveryJob):
        """Execute discovery for each source, merge into CSV."""
        from .scraper import discover_defillama, merge_discovered_rows

        total_start = time.time()

        with self._lock:
            job.status = "running"
            job.started_at = total_start

        # Load chain config for DefiLlama slug
        chain_config = self._load_chain_config(job.chain)
        if not chain_config:
            with self._lock:
                job.status = "failed"
                job.error = f"Chain '{job.chain}' not found in config"
                job.total_elapsed = time.time() - total_start
                self._running = False
            return

        # Load existing rows (or start empty)
        csv_path = find_main_csv(job.chain)
        existing_rows = []
        if csv_path and csv_path.exists():
            try:
                existing_rows = load_csv(csv_path, validate=False)
            except Exception as e:
                logger.warning("Could not load existing CSV: %s", e)

        total_added = 0
        total_dupes = 0

        try:
            for source in job.sources:
                if source == "defillama":
                    # Get chain slug from config
                    dl_config = chain_config.get("sources", {}).get("defillama", {})
                    chain_slug = dl_config.get(
                        "chain_slug", chain_config["name"].title()
                    )

                    def progress_cb(current, total, message):
                        with self._lock:
                            job.progress = current
                            job.progress_total = total
                            job.progress_message = message
                            job.total_elapsed = time.time() - total_start

                    with self._lock:
                        job.progress_message = f"Discovering from DefiLlama ({chain_slug})..."

                    new_rows = discover_defillama(
                        chain_slug=chain_slug,
                        chain_id=job.chain,
                        progress_cb=progress_cb,
                    )

                    existing_rows, added, dupes = merge_discovered_rows(
                        existing_rows, new_rows
                    )
                    total_added += added
                    total_dupes += dupes

                    logger.info(
                        "DefiLlama discovery for %s: +%d added, %d dupes",
                        job.chain,
                        added,
                        dupes,
                    )
                else:
                    logger.warning("Unknown discovery source: %s", source)

            # Write merged CSV
            if total_added > 0:
                data_dir = PROJECT_ROOT / "data" / job.chain.lower()
                data_dir.mkdir(parents=True, exist_ok=True)
                output_path = (
                    data_dir / f"{job.chain.lower()}_ecosystem_research.csv"
                )
                write_csv(existing_rows, output_path, columns=CORRECT_COLUMNS)
                logger.info(
                    "Wrote %d rows to %s (+%d new)",
                    len(existing_rows),
                    output_path,
                    total_added,
                )

            with self._lock:
                job.status = "completed"
                job.result = {
                    "added": total_added,
                    "duplicates": total_dupes,
                    "total_rows": len(existing_rows),
                }
                job.progress_message = (
                    f"Done! Added {total_added} projects"
                    f" ({total_dupes} duplicates skipped)"
                )
                job.total_elapsed = round(time.time() - total_start, 1)
                self._running = False

        except Exception as e:
            logger.error("Discovery failed: %s", e, exc_info=True)
            with self._lock:
                job.status = "failed"
                job.error = str(e)
                job.total_elapsed = round(time.time() - total_start, 1)
                self._running = False

    @staticmethod
    def _load_chain_config(chain_id: str) -> Optional[dict]:
        """Load a specific chain config from chains.json."""
        try:
            with open(CONFIG_PATH) as f:
                config = json.load(f)
            for c in config["chains"]:
                if c["id"] == chain_id:
                    return c
        except Exception as e:
            logger.error("Error loading chains.json: %s", e)
        return None


# Singleton instance
scraper_manager = ScraperManager()
