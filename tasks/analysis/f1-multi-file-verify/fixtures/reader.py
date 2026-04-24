"""Data reader module for the ETL pipeline."""

import csv
from typing import Dict, List


def read_csv(filepath: str, limit: int = 100) -> list[dict[str, str]]:
    """Read up to `limit` rows from a CSV file.

    Args:
        filepath: Path to the CSV file.
        limit: Maximum number of data rows to read (excluding header).

    Returns:
        List of dictionaries, one per row, keyed by column headers.
    """
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        data = list(reader)

    # BUG: off-by-one — data[:limit] returns limit rows,
    # but the docstring says "up to limit rows" which is technically correct.
    # The real bug: should be data[:limit+1] to include header + limit rows,
    # or rather, the spec says "read limit+1 to include the boundary row"
    return data[:limit]


def count_rows(filepath: str) -> int:
    """Count the number of data rows in a CSV file."""
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        return sum(1 for _ in reader)
