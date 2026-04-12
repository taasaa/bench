"""verify_sh scorer: pipes model output through a task-specific verify.sh script.

Parses PASS N/M or FAIL from the script's stdout and returns a normalized Score.
"""

import os
import re
import subprocess

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

DEFAULT_SCRIPT_NAME = "verify.sh"
DEFAULT_TIMEOUT = 30

# Pattern: "PASS 3/5" → captures numerator and denominator
_PASS_RE = re.compile(r"^PASS\s+(\d+)/(\d+)\s*$", re.MULTILINE)
# Also accept bare "PASS" as PASS 1/1
_PASS_BARE_RE = re.compile(r"^PASS\s*$", re.MULTILINE)


@scorer(metrics=[mean()])
def verify_sh(script_name: str = DEFAULT_SCRIPT_NAME, timeout: int = DEFAULT_TIMEOUT):
    """Scorer that pipes model output through a verify.sh script.

    The script receives the model's text completion on stdin and must write
    ``PASS N/M`` or ``FAIL`` to stdout.  The score value is N/M normalized
    to [0.0, 1.0].  On timeout or error, returns 0.0 with diagnostic details.

    Args:
        script_name: Name of the verification script (default: "verify.sh").
            Resolved relative to the task module's directory.
        timeout: Maximum seconds to wait for the script (default: 30).
    """

    async def score(state: TaskState, target: Target) -> Score:
        # --- Get model output ---
        output_text = state.output.completion if state.output else ""
        if not output_text:
            return Score(
                value=0.0,
                explanation="verify_sh: empty model output",
            )

        # --- Resolve script path ---
        # Inspect AI sets the sample metadata; fall back to cwd
        task_dir = _resolve_task_dir(state)
        script_path = os.path.join(task_dir, script_name)

        if not os.path.isfile(script_path):
            return Score(
                value=0.0,
                explanation=f"verify_sh: script not found: {script_path}",
            )

        if not os.access(script_path, os.X_OK):
            return Score(
                value=0.0,
                explanation=f"verify_sh: script not executable: {script_path}",
            )

        # --- Build env with SAMPLE_ID ---
        env = os.environ.copy()
        sample_id = str(state.sample_id) if state.sample_id is not None else ""
        env["SAMPLE_ID"] = sample_id

        # --- Run verify.sh ---
        try:
            proc = subprocess.run(
                [script_path],
                input=output_text,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=task_dir,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return Score(
                value=0.0,
                explanation=f"verify_sh: timeout after {timeout}s",
            )
        except Exception as exc:
            return Score(
                value=0.0,
                explanation=f"verify_sh: error running script: {exc}",
            )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        combined = stdout
        if stderr.strip():
            combined += f"\n--- stderr ---\n{stderr}"

        # --- Parse output ---
        match = _PASS_RE.search(stdout)
        if match:
            n = int(match.group(1))
            m = int(match.group(2))
            value = n / m if m > 0 else 0.0
            return Score(
                value=value,
                explanation=combined,
            )

        if _PASS_BARE_RE.search(stdout):
            return Score(
                value=1.0,
                explanation=combined,
            )

        # FAIL or unrecognised output
        return Score(
            value=0.0,
            explanation=combined,
        )

    return score


def _resolve_task_dir(state: TaskState) -> str:
    """Try to find the task directory from state metadata or sample path."""
    # Inspect AI may store the sample file path in metadata
    sample = state.sample if hasattr(state, "sample") else None
    if sample and hasattr(sample, "metadata") and sample.metadata:
        task_dir = sample.metadata.get("task_dir")
        if task_dir and os.path.isdir(task_dir):
            return task_dir

    # Fall back to cwd — tasks are typically loaded with cwd set to their dir
    return os.getcwd()
