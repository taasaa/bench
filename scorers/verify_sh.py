"""verify_sh scorer: pipes model output through a task-specific verify.sh script.

Parses structured JSON output from verify.sh with per-check metadata:
  {"passed": N, "total": M, "checks": [{"name": "...", "passed": bool, "detail": ""}, ...]}

Falls back to text PASS N/M format for backward compatibility with existing scripts.
Per-check breakdown is synthesized from stderr text output when JSON is not available.
The per-check breakdown is stored in Score.metadata for cross-task diagnostic analysis.

See: doc/SCORING-SYSTEM-PRD.md §verify.sh structural change
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

DEFAULT_SCRIPT_NAME = "verify.sh"
DEFAULT_TIMEOUT = 30

# Text format patterns (backward compat)
_PASS_RE = re.compile(r"^PASS\s+(\d+)/(\d+)\s*$", re.MULTILINE)
_PASS_BARE_RE = re.compile(r"^PASS\s*$", re.MULTILINE)

# Pattern for extracting individual check results from text output
# Matches: "  check_1: pass", "check_1: pass", "# check_1: pass", "Check 1: PASS", etc.
_CHECK_STATUS_RE = re.compile(
    r"(?:^|\n)(?:\s*|#\s*|[-*]\s*)?"
    r"(?:check[_\s]?(\d+)|PASS|FAIL)"
    r"[\s:]*(\d+)?[\s:]*(pass(?:ed)?|fail(?:ed)?|error)?",
    re.IGNORECASE | re.MULTILINE,
)

# Lines that are NOT check results (diagnostic/header lines)
_NON_CHECK_LINES = re.compile(
    r"^(PASS|FAIL|checks?\s*passed|---|\s*(FAIL|PASS)\s*$)",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class CheckResult:

    """Result of a single check within a verify.sh script."""

    name: str
    passed: bool
    detail: str


@dataclass
class VerifyResult:

    """Result from verify.sh scorer output parsing."""

    passed: int
    total: int
    checks: list[CheckResult]
    raw_stdout: str
    raw_stderr: str
    format: str  # "json" | "text"


def _synthesize_checks_from_stderr(stderr: str, total: int) -> list[CheckResult]:
    """Synthesize per-check results from stderr text.

    Examines existing stderr output from verify.sh scripts. Most scripts already
    output check-level diagnostic information in text form. This function
    extracts pass/fail per check from that text for Score.metadata.
    """
    checks: list[CheckResult] = []
    if not stderr.strip():
        # No stderr content — all checks are unknown; return total empty checks
        return [
            CheckResult(name=f"check_{i+1}", passed=False, detail="no output")
            for i in range(total)
        ]

    # Look for lines that indicate pass/fail per check number
    # Patterns like "check_1: pass", "Check 1: PASS", "Check 1 passed", etc.
    # We also look for check counts like "2/3 checks passed"
    lines = stderr.strip().split("\n")

    # Build a dict of check_num -> passed status from existing diagnostic lines
    check_status: dict[int, bool] = {}
    for line in lines:
        line = line.strip()
        if not line or _NON_CHECK_LINES.match(line):
            continue

        # Pattern: "check_1" or "Check 1" or "check 1"
        m = re.search(r"check[_\s]?(\d+)", line, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            passed = bool(re.search(r"\bpass(?:ed)?\b", line, re.IGNORECASE))
            failed = bool(re.search(r"\bfail(?:ed)?\b", line, re.IGNORECASE))
            if passed or failed:
                check_status[num] = not failed

    # Fill in checks array
    for i in range(1, total + 1):
        if i in check_status:
            passed = check_status[i]
            # Find the corresponding diagnostic line for detail
            detail = ""
            for line in lines:
                if re.search(rf"check[_\s]?{i}\b", line, re.IGNORECASE):
                    detail = line.strip()
                    break
            checks.append(CheckResult(
                name=f"check_{i}",
                passed=passed,
                detail=detail[:200],  # truncate long details
            ))
        else:
            # Check not found in stderr — mark as unknown, use total as hint
            passed = check_status.get(0, False)  # heuristic fallback
            checks.append(CheckResult(
                name=f"check_{i}",
                passed=passed,
                detail="",
            ))

    return checks


def _parse_json_result(stdout: str, stderr: str) -> VerifyResult | None:
    """Parse JSON result from verify.sh stdout.

    Expected format:
      {"passed": N, "total": M, "checks": [
        {"name": "check_1", "passed": true, "detail": ""},
        ...
      ]}

    Returns None if JSON parse fails.
    """
    try:
        data = json.loads(stdout.strip())
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    passed = data.get("passed")
    total = data.get("total")
    if not isinstance(passed, int) or not isinstance(total, int):
        return None

    checks_raw = data.get("checks", [])
    checks: list[CheckResult] = []
    for c in checks_raw:
        if not isinstance(c, dict):
            return None
        checks.append(CheckResult(
            name=str(c.get("name", "")),
            passed=bool(c.get("passed", False)),
            detail=str(c.get("detail", "")),
        ))

    return VerifyResult(
        passed=passed,
        total=total,
        checks=checks,
        raw_stdout=stdout,
        raw_stderr=stderr,
        format="json",
    )


def _parse_text_result(stdout: str, stderr: str) -> VerifyResult:
    """Parse text PASS N/M format from verify.sh stdout.

    Falls back to FAIL if output is unrecognised.
    Checks are synthesised from stderr text content.
    """
    match = _PASS_RE.search(stdout)
    if match:
        n = int(match.group(1))
        m = int(match.group(2))
        checks = _synthesize_checks_from_stderr(stderr, m)
        return VerifyResult(
            passed=n, total=m, checks=checks,
            raw_stdout=stdout, raw_stderr=stderr, format="text",
        )

    if _PASS_BARE_RE.search(stdout):
        checks = _synthesize_checks_from_stderr(stderr, 1)
        return VerifyResult(
            passed=1, total=1, checks=checks,
            raw_stdout=stdout, raw_stderr=stderr, format="text",
        )

    # FAIL or unrecognised — try to extract check count from stderr
    check_count_match = re.search(r"(\d+)/(\d+)\s+checks?\s+passed", stderr, re.IGNORECASE)
    if check_count_match:
        n = int(check_count_match.group(1))
        m = int(check_count_match.group(2))
    else:
        n, m = 0, 1

    checks = _synthesize_checks_from_stderr(stderr, m)
    return VerifyResult(
        passed=n, total=m, checks=checks,
        raw_stdout=stdout, raw_stderr=stderr, format="text",
    )


@scorer(metrics=[mean()])
def verify_sh(
    script_name: str = DEFAULT_SCRIPT_NAME,
    timeout: int = DEFAULT_TIMEOUT,
) -> None:
    """Scorer that pipes model output through a task-specific verify.sh script.

    The script receives the model's text completion on stdin and must write
    JSON or text to stdout:
      JSON:    {"passed": N, "total": M, "checks": [...]}
      Text:    PASS N/M

    The score value is N/M normalized to [0.0, 1.0].  On timeout or error,
    returns 0.0 with diagnostic details.

    Per-check breakdown is stored in Score.metadata for cross-task analysis
    via bench compare.

    Args:
        script_name: Name of the verification script (default: "verify.sh").
            Resolved relative to the task module's directory.
        timeout: Maximum seconds to wait for the script (default: 30).
    """
    async def score(state: TaskState, target: Target) -> Score:
        output_text = state.output.completion if state.output else ""
        if not output_text:
            return Score(
                value=0.0,
                explanation="verify_sh: empty model output",
                metadata={"pillar": "correctness", "passed": 0, "total": 0, "checks": []},
            )
        # bench_task_dir is injected by run.py into every task's metadata.
        bench_task_dir = state.metadata.get("bench_task_dir") if state.metadata else None
        if not bench_task_dir:
            return Score(
                value=0.0,
                explanation="verify_sh: no bench_task_dir in metadata",
                metadata={"pillar": "correctness", "passed": 0, "total": 0, "checks": []},
            )
        script_path = os.path.join(bench_task_dir, script_name)
        return _score_with_sh(state, script_path, bench_task_dir)

    def _score_with_sh(state: TaskState, script_path: str, task_dir: str) -> Score:
        output_text = state.output.completion if state.output else ""
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
            return Score(
                value=0.0,
                explanation=f"verify_sh: timeout after {timeout}s",
                metadata={"pillar": "correctness", "passed": 0, "total": 0, "checks": []},
            )
        except Exception as exc:
            return Score(
                value=0.0,
                explanation=f"verify_sh: error running script: {exc}",
                metadata={"pillar": "correctness", "passed": 0, "total": 0, "checks": []},
            )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        # Try JSON first, fall back to text
        json_result = _parse_json_result(stdout, stderr)
        if json_result is not None:
            result = json_result
        else:
            result = _parse_text_result(stdout, stderr)

        n = result.passed
        m = result.total
        value = n / m if m > 0 else 0.0

        # Build check metadata
        checks_meta = [
            {"name": c.name, "passed": c.passed, "detail": c.detail}
            for c in result.checks
        ]

        explanation = (
            f"correctness={value:.2f}, efficiency=1.00, safety=1.00\n"
            f"{result.raw_stdout}"
            + (
                f"\n--- stderr ---\n{result.raw_stderr}"
                if result.raw_stderr.strip()
                else ""
            )
        )

        return Score(
            value=value,
            explanation=explanation,
            metadata={
                "pillar": "correctness",
                "passed": n,
                "total": m,
                "checks": checks_meta,
                "format": result.format,
                "raw_stderr": result.raw_stderr,
            },
        )

    return score
