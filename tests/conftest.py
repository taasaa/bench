"""Shared pytest helpers for Bench tests."""

import asyncio
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()


def run_verify_script(
    task_dir: str, input_text: str, sample_id: str | None = None
) -> tuple[str, str, int]:
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


def run_async(coro):
    """Run an async coroutine in a sync context."""
    return asyncio.run(coro)


def make_task_state(
    completion: str = "test output",
    messages: list | None = None,
    target: str = "expected",
    bench_task_dir: str | None = None,
):
    """Factory for TaskState objects for scorer testing.

    Usage:
        state = make_task_state("my output")
        state = make_task_state("my output", target="expected")
        state = make_task_state("my output", bench_task_dir="/path/to/task")
    """
    from inspect_ai.model import ChatMessageAssistant, ModelOutput
    from inspect_ai.scorer import Target
    from inspect_ai.solver import TaskState

    output = ModelOutput.from_content(model="test-model", content=completion)
    metadata = {"bench_task_dir": bench_task_dir} if bench_task_dir else None
    return TaskState(
        model="test-model",
        sample_id="test-sample",
        epoch=0,
        input="test input",
        messages=messages or [ChatMessageAssistant(content=completion)],
        target=Target(target),
        output=output,
        metadata=metadata,
    )
