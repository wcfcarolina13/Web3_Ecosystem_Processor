"""
Shared logging configuration for ecosystem research scripts.

Usage:
    from lib.logging_config import get_logger, configure_logging

    # In script entry point (e.g., main()):
    configure_logging(log_file=Path("data/near/pipeline.log"))

    # In any module:
    logger = get_logger(__name__)
    logger.info("Processing %d rows", count)
    logger.warning("Rate limited, retrying in %ds", delay)
    logger.error("Failed to fetch %s: %s", url, err)
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def get_logger(name: str) -> logging.Logger:
    """Get a named logger. Use __name__ for module-level loggers."""
    return logging.getLogger(name)


def configure_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    quiet: bool = False,
) -> None:
    """
    Configure the root logger with console and optional file handlers.

    Args:
        level: Logging level (default: INFO).
        log_file: If provided, also write logs to this file.
        quiet: If True, console only shows WARNING and above (file gets everything).
    """
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # Console handler (stderr)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING if quiet else level)
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-5s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(console)

    # File handler (optional)
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-5s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root.addHandler(fh)
