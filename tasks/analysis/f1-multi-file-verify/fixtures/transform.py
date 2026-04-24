"""Data transformation module for the ETL pipeline."""

from typing import Dict, List


def normalize_names(row: dict[str, str]) -> dict[str, str]:
    """Normalize field names to lowercase with underscores."""
    return {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items()}


def filter_empty(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Remove rows where all values are empty strings."""
    return [row for row in rows if any(v for v in row.values())]


def transform(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Apply all transformations to a list of rows.

    1. Normalize field names
    2. Remove empty rows
    """
    normalized = [normalize_names(row) for row in rows]
    return filter_empty(normalized)
