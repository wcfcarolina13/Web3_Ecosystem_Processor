"""
CSV utilities for ecosystem research data.
"""

import csv
from pathlib import Path
from typing import List, Dict, Optional

from .columns import CORRECT_COLUMNS


def sanitize_csv_field(value) -> str:
    """Sanitize a field value for CSV -- replace commas with semicolons."""
    if isinstance(value, str):
        return value.replace(",", ";")
    return str(value) if value is not None else ""


def load_csv(csv_path: Path) -> List[Dict]:
    """Load a CSV file and return list of dicts."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def get_names_from_csv(csv_path: Path) -> List[str]:
    """Load just the Project Name column from a CSV."""
    return [row["Project Name"] for row in load_csv(csv_path)]


def write_csv(
    rows: List[Dict],
    output_path: Path,
    columns: Optional[List[str]] = None,
):
    """Write rows to CSV with correct column order."""
    cols = columns or CORRECT_COLUMNS
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            clean_row = {k: row.get(k, "") for k in cols}
            writer.writerow(clean_row)


def append_csv(
    rows: List[Dict],
    csv_path: Path,
    columns: Optional[List[str]] = None,
):
    """Append rows to an existing CSV."""
    cols = columns or CORRECT_COLUMNS
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        for row in rows:
            clean_row = {k: row.get(k, "") for k in cols}
            writer.writerow(clean_row)


def resolve_data_path(chain: str, filename: Optional[str] = None) -> Path:
    """
    Resolve path to a chain's data directory.

    Returns data/<chain>/ or data/<chain>/<filename> if filename is given.
    """
    base = Path(__file__).parent.parent / "data" / chain.lower()
    if filename:
        return base / filename
    return base


def find_main_csv(chain: str) -> Optional[Path]:
    """
    Find the main ecosystem research CSV for a chain.

    Looks for *_ecosystem_research.csv in data/<chain>/.
    Returns the path if found, None otherwise.
    """
    data_dir = resolve_data_path(chain)
    if not data_dir.exists():
        return None
    csvs = list(data_dir.glob("*_ecosystem_research.csv"))
    return csvs[0] if csvs else None
