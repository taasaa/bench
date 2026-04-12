"""Fixture loading utilities for eval tasks.

Tasks can include a fixtures/ subdirectory alongside their task.py.
These functions let task authors and scorers reference fixture files
by name without manual path construction.
"""

from functools import lru_cache
from pathlib import Path

# Sentinel for type clarity — we accept str | Path but always return Path


@lru_cache(maxsize=64)
def _fixtures_dir_cached(resolved: str) -> Path:
    return Path(resolved)


def fixtures_dir(task_file: str | Path) -> Path:
    """Return the fixtures/ directory for a task given its task.py path.

    Args:
        task_file: Path to a task file (e.g. "tasks/code_gen/my-task/task.py").

    Returns:
        Path to the fixtures/ sibling directory
        (e.g. "tasks/code_gen/my-task/fixtures").

    Raises:
        FileNotFoundError: If the fixtures directory does not exist.
    """
    resolved = str(Path(task_file).resolve())
    fixtures = _fixtures_dir_cached(resolved).parent / "fixtures"
    if not fixtures.is_dir():
        raise FileNotFoundError(
            f"Fixtures directory not found: {fixtures}\n"
            f"Expected a 'fixtures/' directory next to {task_file}"
        )
    return fixtures


def load_fixture(task_file: str | Path, name: str) -> str:
    """Load a fixture file by name and return its content as a string.

    Args:
        task_file: Path to the task file (e.g. "tasks/code_gen/my-task/task.py").
        name: Fixture filename relative to the fixtures/ directory
              (e.g. "input.py", "data/config.json").

    Returns:
        File contents as a UTF-8 string.

    Raises:
        FileNotFoundError: If the fixture file does not exist.
    """
    path = fixtures_dir(task_file) / name
    if not path.is_file():
        available = (
            sorted(p.name for p in path.parent.iterdir())
            if path.parent.is_dir()
            else "(directory missing)"
        )
        raise FileNotFoundError(
            f"Fixture file not found: {path}\n"
            f"Available fixtures in {path.parent}: {available}"
        )
    return path.read_text(encoding="utf-8")


def load_fixture_bytes(task_file: str | Path, name: str) -> bytes:
    """Load a fixture file as raw bytes (for binary fixtures).

    Args:
        task_file: Path to the task file.
        name: Fixture filename relative to the fixtures/ directory.

    Returns:
        File contents as raw bytes.

    Raises:
        FileNotFoundError: If the fixture file does not exist.
    """
    path = fixtures_dir(task_file) / name
    if not path.is_file():
        available = (
            sorted(p.name for p in path.parent.iterdir())
            if path.parent.is_dir()
            else "(directory missing)"
        )
        raise FileNotFoundError(
            f"Fixture file not found: {path}\n"
            f"Available fixtures in {path.parent}: {available}"
        )
    return path.read_bytes()
