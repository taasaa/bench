"""Shared pytest helpers for Bench tests."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.resolve()


def run_verify_script(task_dir: str, input_text: str, sample_id: str | None = None) -> tuple[str, str, int]:
    """Run verify.sh in a task dir with input_text on stdin.

    Args:
        task_dir: Relative path from project root to the task directory.
        input_text: Text to pipe to verify.sh via stdin.
        sample_id: Optional SAMPLE_ID env var value.

    Returns:
        (stdout, stderr, returncode)
    """
    script = ROOT / task_dir / "verify.sh"
    assert script.is_file(), f"verify.sh not found: {script}"
    assert os.access(script, os.X_OK), f"verify.sh not executable: {script}"

    env = os.environ.copy()
    if sample_id is not None:
        env["SAMPLE_ID"] = sample_id

    proc = subprocess.run(
        [str(script)],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(ROOT / task_dir),
        env=env,
    )
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode


@pytest.fixture
def run_async():
    """Run an async coroutine in a sync context."""
    import asyncio

    def _runner(coro):
        return asyncio.run(coro)

    return _runner