"""Rich fixture loading for eval tasks with scenario-based directories.

Convention: tasks/{tier}/{task}/fixtures/{scenario_id}/
Each scenario directory contains files that the multi-shot solver can expose
to the model via read-only tools (read_file, list_directory).

This module handles:
1. Loading all files from a fixture scenario directory
2. Injecting fixture path into sample metadata via _resolve_task()
3. Listing available files for initial context injection
"""

from __future__ import annotations

from pathlib import Path


def load_fixtures(task_dir: str | Path, scenario_id: str | None) -> dict[str, str] | None:
    """Load all files from a fixture scenario directory.

    Args:
        task_dir: Absolute path to the task directory (containing task.py).
        scenario_id: Fixture scenario subdirectory name (e.g. "canonical").
            If None, returns None.

    Returns:
        Dict mapping filename to file content, or None if scenario not found.
    """
    if scenario_id is None:
        return None

    fixture_path = Path(task_dir).resolve() / "fixtures" / scenario_id
    if not fixture_path.is_dir():
        return None

    files: dict[str, str] = {}
    for fpath in sorted(fixture_path.rglob("*")):
        if fpath.is_file():
            try:
                rel = fpath.relative_to(fixture_path)
                files[str(rel)] = fpath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

    return files if files else None


def fixture_dir_for(task_dir: str | Path, scenario_id: str) -> Path | None:
    """Return absolute Path to a fixture scenario directory, or None if missing."""
    p = Path(task_dir).resolve() / "fixtures" / scenario_id
    return p if p.is_dir() else None


def list_fixture_files(task_dir: str | Path, scenario_id: str | None) -> list[str]:
    """List relative paths of all files in a fixture scenario directory.

    Returns empty list if scenario_id is None or directory doesn't exist.
    """
    if scenario_id is None:
        return []

    d = Path(task_dir).resolve() / "fixtures" / scenario_id
    if not d.is_dir():
        return []

    return sorted(str(f.relative_to(d)) for f in d.rglob("*") if f.is_file())
