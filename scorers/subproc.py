"""Shared subprocess execution for code-scoring tasks.

HumanEval pattern: assemble a Python script (setup + checks), run it in an
isolated subprocess, parse a PASS line from stdout.
"""

import re
import subprocess
import sys

TIMEOUT = 10  # seconds


def run_checks(script: str, total: int) -> tuple[int, int, str]:
    """Run a Python script in a subprocess and parse ``PASS N/M`` from stdout.

    If the script crashes or times out, returns ``(0, total, error_msg)``.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return 0, total, "Verification timed out"

    match = re.search(r"PASS (\d+)/(\d+)", result.stdout)
    if match:
        return int(match.group(1)), int(match.group(2)), ""

    stderr = result.stderr.strip() if result.stderr else ""
    return 0, total, stderr[:200]


def build_script(func_def: str, checks: list[str]) -> str:
    """Build a subprocess script: function def + check lines wrapped in try/except.

    Each check line should be a complete Python expression (assert, comparison, etc).
    For comparisons like ``foo(x) == y``, wraps in an if-check so falsy results
    don't increment the pass counter.
    """
    lines = [func_def, "", "_p = 0", "_t = 0", ""]
    for check in checks:
        lines.append("_t += 1")
        lines.append("try:")
        # If the check starts with 'assert', run it directly — AssertionError means fail.
        # Otherwise wrap in a conditional so falsy results don't count as passes.
        if check.strip().startswith("assert "):
            lines.append(f"    {check}")
            lines.append("    _p += 1")
        else:
            lines.append(f"    if {check}: _p += 1")
        lines.append("except Exception:")
        lines.append("    pass")
        lines.append("")
    lines.append('print(f"PASS {_p}/{_t}")')
    return "\n".join(lines)
