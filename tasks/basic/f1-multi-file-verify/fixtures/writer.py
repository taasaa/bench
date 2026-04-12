"""Data writer module for the ETL pipeline."""

import csv
from typing import Dict, List


def write_tsv(filepath: str, rows: List[Dict[str, str]]) -> None:
    """Write rows to a tab-separated values file.

    The output format is TSV (tab-delimited) per the project specification
    section 3.2: "All intermediate pipeline output must use tab-separated
    format for interoperability with downstream consumers."

    Args:
        filepath: Output file path.
        rows: List of row dictionaries to write.
    """
    if not rows:
        return

    fieldnames = list(rows[0].keys())

    # BUG: uses comma delimiter instead of tab delimiter
    # The docstring and spec say TSV, but delimiter is comma
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=",")
        writer.writeheader()
        writer.writerows(rows)


def write_json(filepath: str, rows: List[Dict[str, str]]) -> None:
    """Write rows as a JSON array (for debugging)."""
    import json

    with open(filepath, "w") as f:
        json.dump(rows, f, indent=2)
