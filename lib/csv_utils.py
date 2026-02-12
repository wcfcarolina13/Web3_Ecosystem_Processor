"""
CSV utilities for ecosystem research data.
"""

import csv
import re
from pathlib import Path
from typing import List, Dict, Optional

from .columns import CORRECT_COLUMNS


def sanitize_csv_field(value) -> str:
    """
    Sanitize a field value for clean CSV output.

    Rules (shared with extension popup.js toCSV):
    1. Strip newlines / carriage returns → single space
    2. Collapse whitespace
    3. Decode common HTML entities
    4. Replace commas with semicolons (avoids quoting issues in Google Sheets)
    """
    if value is None:
        return ""
    val = str(value)
    # Strip newlines, collapse whitespace
    val = val.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    val = re.sub(r"\s+", " ", val).strip()
    # Decode common HTML entities
    val = (
        val.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    # Replace commas with semicolons to avoid CSV quoting issues
    val = val.replace(",", ";")
    return val


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
            clean_row = {k: sanitize_csv_field(row.get(k, "")) for k in cols}
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
            clean_row = {k: sanitize_csv_field(row.get(k, "")) for k in cols}
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
