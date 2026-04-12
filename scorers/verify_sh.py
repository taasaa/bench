"""verify_sh scorer: pipes model output through a task-specific verify.sh script.

Parses PASS N/M or FAIL from the script's stdout and returns a normalized Score.
"""

import inspect
import os
import re
import subprocess
from functools import lru_cache

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

DEFAULT_SCRIPT_NAME = "verify.sh"
DEFAULT_TIMEOUT = 30

# Pattern: "PASS 3/5" → captures numerator and denominator
_PASS_RE = re.compile(r"^PASS\s+(\d+)/(\d+)\s*$", re.MULTILINE)
# Also accept bare "PASS" as PASS 1/1
_PASS_BARE_RE = re.compile(r"^PASS\s*$", re.MULTILINE)


def _find_task_dir() -> str:
    """Walk the call stack to find the task module's directory.

    inspect_ai does not expose the task module path to scorers via any
    API, so we walk stack frames until we find a .py file under tasks/.
    This works because the scorer is called synchronously from the task
    module during evaluation.
    """
    for frame_info in inspect.getouterframes(inspect.currentframe(), context=2):
        path = frame_info.filename
        # Match task module paths like:
        #   /Users/rut/dev/bench/tasks/competence/f12-surgical-fix/task.py
        #   tasks/competence/f12-surgical-fix/task.py
        if "/tasks/" in path or "\\tasks\\" in path:
            task_dir = os.path.dirname(path)
            if os.path.isdir(task_dir):
                return task_dir
        elif path.endswith("/tasks/__init__.py") or path.endswith("\\tasks\\__init__.py"):
            return os.path.dirname(os.path.dirname(path))
    return os.getcwd()


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
    # Resolve task_dir once per scorer instance (not per sample) via stack introspection.
    # Cache the result since all samples in the same task use the same task module.
    @lru_cache(maxsize=1)
    def _cached_task_dir() -> str:
        return _find_task_dir()

    async def score(state: TaskState, target: Target) -> Score:
        output_text = state.output.completion if state.output else ""
        if not output_text:
            return Score(value=0.0, explanation="verify_sh: empty model output")

        task_dir = _cached_task_dir()
        script_path = os.path.join(task_dir, script_name)

        if not os.path.isfile(script_path):
            return Score(value=0.0, explanation=f"verify_sh: script not found: {script_path}")

        if not os.access(script_path, os.X_OK):
            return Score(value=0.0, explanation=f"verify_sh: script not executable: {script_path}")

        env = os.environ.copy()
        env["SAMPLE_ID"] = str(state.sample_id) if state.sample_id is not None else ""

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
            return Score(value=0.0, explanation=f"verify_sh: timeout after {timeout}s")
        except Exception as exc:
            return Score(value=0.0, explanation=f"verify_sh: error running script: {exc}")

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        combined = stdout + (f"\n--- stderr ---\n{stderr}" if stderr.strip() else "")

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
