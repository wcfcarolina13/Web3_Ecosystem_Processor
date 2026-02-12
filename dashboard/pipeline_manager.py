"""
Thread-safe background pipeline executor with progress tracking.

Runs the enrichment pipeline in a daemon thread so the Flask server
stays responsive. Progress is polled via the API.

Usage:
    from dashboard.pipeline_manager import pipeline_manager

    job_id = pipeline_manager.start_pipeline(
        chain="near",
        csv_path=Path("data/near/near_ecosystem_research.csv"),
        target_assets=["USDT", "USDC"],
        steps=["dedup", "grid", "coingecko"],
    )

    job = pipeline_manager.get_job(job_id)
    print(job["status"], job["steps"])
"""

import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.csv_utils import backup_csv
from lib.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class StepResult:
    """Status of a single pipeline step."""

    name: str
    description: str
    status: str = "pending"  # pending | running | completed | failed | skipped
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    elapsed: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PipelineJob:
    """State of a pipeline run."""

    job_id: str
    chain: str
    status: str = "pending"  # pending | running | completed | failed
    steps: List[StepResult] = field(default_factory=list)
    current_step: Optional[str] = None
    total_elapsed: Optional[float] = None
    error: Optional[str] = None
    started_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "chain": self.chain,
            "status": self.status,
            "current_step": self.current_step,
            "steps": [s.to_dict() for s in self.steps],
            "total_elapsed": round(self.total_elapsed, 1) if self.total_elapsed else None,
            "error": self.error,
        }


class PipelineManager:
    """
    Manages background pipeline execution.

    Thread-safe: all state reads/writes go through self._lock.
    Only one pipeline can run at a time (self._running flag).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._jobs: Dict[str, PipelineJob] = {}

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start_pipeline(
        self,
        chain: str,
        csv_path: Path,
        target_assets: List[str],
        steps: List[str],
    ) -> str:
        """
        Start the pipeline in a background thread.

        Returns the job_id. Raises RuntimeError if a pipeline is already running.
        """
        # Lazy import to avoid circular imports at module load time
        from scripts.enrich_all import STEP_RUNNERS, STEP_DESCRIPTIONS

        with self._lock:
            if self._running:
                raise RuntimeError("A pipeline is already running")
            self._running = True

        job_id = uuid.uuid4().hex[:8]
        job = PipelineJob(
            job_id=job_id,
            chain=chain,
            steps=[
                StepResult(name=s, description=STEP_DESCRIPTIONS.get(s, s))
                for s in steps
            ],
        )

        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(job, csv_path, chain, target_assets, steps, STEP_RUNNERS),
            daemon=True,
            name=f"pipeline-{job_id}",
        )
        thread.start()
        logger.info("Pipeline %s started for chain=%s, steps=%s", job_id, chain, steps)
        return job_id

    def get_job(self, job_id: str) -> Optional[dict]:
        """Get job status as a dict (thread-safe snapshot)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return job.to_dict()

    def _run_pipeline(
        self,
        job: PipelineJob,
        csv_path: Path,
        chain: str,
        target_assets: List[str],
        steps: List[str],
        step_runners: dict,
    ):
        """Execute pipeline steps sequentially in a background thread."""
        total_start = time.time()

        with self._lock:
            job.status = "running"
            job.started_at = total_start

        # Pre-pipeline backup
        try:
            backup_csv(csv_path, suffix="pre-pipeline")
        except Exception as e:
            logger.warning("Could not create pre-pipeline backup: %s", e)

        failed = False

        for i, step_name in enumerate(steps):
            if failed:
                # Mark remaining steps as skipped
                with self._lock:
                    job.steps[i].status = "skipped"
                continue

            with self._lock:
                job.steps[i].status = "running"
                job.current_step = step_name
                job.total_elapsed = time.time() - total_start

            runner = step_runners.get(step_name)
            if not runner:
                with self._lock:
                    job.steps[i].status = "failed"
                    job.steps[i].error = f"Unknown step: {step_name}"
                failed = True
                continue

            step_start = time.time()
            try:
                result = runner(
                    csv_path=csv_path,
                    chain=chain,
                    target_assets=target_assets,
                    dry_run=False,
                )
                elapsed = time.time() - step_start

                with self._lock:
                    job.steps[i].status = "completed"
                    job.steps[i].result = result
                    job.steps[i].elapsed = round(elapsed, 1)
                    job.total_elapsed = time.time() - total_start

                logger.info("Step %s completed in %.1fs", step_name, elapsed)

            except Exception as e:
                elapsed = time.time() - step_start
                logger.error("Step %s failed: %s", step_name, e, exc_info=True)

                with self._lock:
                    job.steps[i].status = "failed"
                    job.steps[i].error = str(e)
                    job.steps[i].elapsed = round(elapsed, 1)
                    job.error = f"Step '{step_name}' failed: {e}"
                    job.total_elapsed = time.time() - total_start

                failed = True

        # Finalize
        with self._lock:
            job.status = "failed" if failed else "completed"
            job.current_step = None
            job.total_elapsed = round(time.time() - total_start, 1)
            self._running = False

        logger.info(
            "Pipeline %s %s in %.1fs",
            job.job_id,
            job.status,
            job.total_elapsed,
        )


# Singleton instance — shared across Flask requests
pipeline_manager = PipelineManager()
