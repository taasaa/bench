"""verify_sh scorer: pipes model output through a task-specific verify.sh script.

Parses PASS N/M or FAIL from the script's stdout and returns a normalized Score.
"""

import inspect
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


def _find_task_dir() -> str:
    """Find the task module directory.

    Strategy: manually walk the frame chain (via f_back) checking f_globals["__file__"]
    for a path under tasks/.  This works because the scorer's closure is created
    inside task.py (which calls verify_sh()), so task.py's globals are on the chain.

    inspect.getfile(code_object) does NOT work in async contexts because it uses
    co_filename, not f_globals["__file__"].  Manual f_back walking always works.
    """
    import sys
    frame = inspect.currentframe()
    frames_checked = []
    try:
        depth = 0
        while frame is not None and depth < 30:
            depth += 1
            try:
                file = frame.f_globals.get("__file__", "")
                frames_checked.append(file)
                if file and ("/tasks/" in file or "\\tasks\\" in file):
                    task_dir = os.path.dirname(os.path.abspath(file))
                    if os.path.isdir(task_dir):
                        print(f"[verify_sh _find_task_dir] HIT: task_dir={task_dir}", file=sys.stderr, flush=True)
                        return task_dir
            except Exception:
                pass
            frame = frame.f_back
        print(f"[verify_sh _find_task_dir] no tasks/ frame in {len(frames_checked)} frames: {frames_checked}", file=sys.stderr, flush=True)
    finally:
        del frame  # avoid cycle

    # Fallback: scan sys.modules for any module under tasks/
    for module in sys.modules.values():
        if module is None:
            continue
        try:
            file = getattr(module, "__file__", None)
            if file and ("/tasks/" in file or "\\tasks\\" in file):
                task_dir = os.path.dirname(file)
                if os.path.isdir(task_dir):
                    print(f"[verify_sh _find_task_dir] fallback HIT via sys.modules: {task_dir}", file=sys.stderr, flush=True)
                    return task_dir
        except Exception:
            continue
    print(f"[verify_sh _find_task_dir] all strategies failed, cwd={os.getcwd()}", file=sys.stderr, flush=True)
    return os.getcwd()


@scorer(metrics=[mean()])
def verify_sh(script_name: str = DEFAULT_SCRIPT_NAME, timeout: int = DEFAULT_TIMEOUT) -> None:
    """Scorer that pipes model output through a verify.sh script.

    The script receives the model's text completion on stdin and must write
    ``PASS N/M`` or ``FAIL`` to stdout.  The score value is N/M normalized
    to [0.0, 1.0].  On timeout or error, returns 0.0 with diagnostic details.

    Args:
        script_name: Name of the verification script (default: "verify.sh").
            Resolved relative to the task module's directory.
        timeout: Maximum seconds to wait for the script (default: 30).
    """
    # Resolve task_dir once per scorer instance (not per sample).
    # task_dir does not change across samples in the same task.
    _task_dir: str | None = None

    def _cached_task_dir() -> str:
        nonlocal _task_dir
        if _task_dir is None:
            _task_dir = _find_task_dir()
        return _task_dir

    async def score(state: TaskState, target: Target) -> Score:
        # Resolve script path.
        # Priority: bench_task_dir injected by bench run CLI via Task metadata.
        # Falls back to cached frame-walk detection if not available.
        bench_task_dir = None
        if state.metadata:
            bench_task_dir = state.metadata_as.get("bench_task_dir")
        if bench_task_dir:
            script_path = os.path.join(bench_task_dir, script_name)
            return _score_with_sh(state, script_path, bench_task_dir)

        # Fallback: detect via frame walk + sys.modules scan.
        script_path = os.path.join(_cached_task_dir(), script_name)
        return _score_with_sh(state, script_path, _cached_task_dir())

    def _score_with_sh(state: TaskState, script_path: str, task_dir: str) -> Score:
        output_text = state.output.completion if state.output else ""
        if not output_text:
            return Score(value=0.0, explanation="verify_sh: empty model output")

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
                explanation=f"correctness={value:.2f}\n{combined}",
            )

        if _PASS_BARE_RE.search(stdout):
            return Score(
                value=1.0,
                explanation=f"correctness=1.00\n{combined}",
            )

        # FAIL or unrecognised output
        return Score(
            value=0.0,
            explanation=f"correctness=0.00\n{combined}",
        )

    return score
