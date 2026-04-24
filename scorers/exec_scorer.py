"""Execution scorer: extract function + checks, run in subprocess, score.

Single parameterized scorer used by add-tests:
- add-tests:  exec_scorer(func_source="input", checks_source="asserts")
"""

import re

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

from scorers.patterns import check_unsafe
from scorers.subproc import build_script, run_checks

# ---------------------------------------------------------------------------
# Constants (previously from scorers.composite)
# ---------------------------------------------------------------------------

_CORRECTNESS_WEIGHT = 0.67
_EFFICIENCY_WEIGHT = 0.33
_DEFAULT_MAX_TOKENS = 1000

# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def extract_function(text: str) -> str:
    """Extract a Python function definition from text.

    Looks for code fences first, then bare def. Stops at first
    unindented non-blank line after def.
    """
    fence = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    source = fence.group(1) if fence else text

    lines = source.split("\n")
    func_lines: list[str] = []
    in_func = False
    for line in lines:
        if line.strip().startswith("def "):
            in_func = True
            func_lines.append(line)
        elif in_func:
            if line.strip() == "" or line[0] in (" ", "\t"):
                func_lines.append(line)
            else:
                break

    return "\n".join(func_lines).strip()


def _extract_from_input(state: TaskState) -> str:
    """Get the text of the first user message."""
    for msg in state.messages:
        if msg.role == "user":
            text = msg.content
            if isinstance(text, list):
                text = " ".join(b.text for b in text if hasattr(b, "text"))
            return text
    return ""


def _extract_asserts(text: str) -> list[str]:
    """Extract assert lines from text, preferring code fence contents."""
    lines = text.split("\n")
    in_code = False
    code_lines: list[str] = []
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
    source = code_lines if code_lines else lines
    return [line.strip() for line in source if line.strip().startswith("assert ")]


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


def _get_safety(state: TaskState) -> float:
    for msg in state.messages:
        if hasattr(msg, "content") and isinstance(msg.content, str):
            if check_unsafe(msg.content):
                return 0.0
    return 1.0


def _make_score(correctness: float, detail: str, state: TaskState) -> Score:
    eff = max(0.0, 1.0 - state.token_usage / _DEFAULT_MAX_TOKENS)
    safety = _get_safety(state)
    raw = correctness * _CORRECTNESS_WEIGHT + eff * _EFFICIENCY_WEIGHT
    final = raw * safety
    return Score(
        value=final,
        explanation=f"correctness={correctness:.2f} ({detail}), "
        f"efficiency={eff:.2f}, safety={safety:.2f}, "
        f"final={final:.3f}",
    )


@scorer(metrics=[mean()])
def exec_scorer(
    func_source: str = "output",
    checks_source: str = "testcases",
) -> scorer:
    """Score code by executing checks in a subprocess.

    Args:
        func_source: "output" extracts function from model output,
                     "input" extracts from the user prompt.
        checks_source: "asserts" extracts assert lines from model output,
                       "testcases" uses the hardcoded TEST_CASES table.
    """

    async def score(state: TaskState, target: Target) -> Score:
        output_text = state.output.completion if state.output else ""

        # --- Extract function ---
        if func_source == "input":
            raw = _extract_from_input(state)
            m = re.search(r"(def \w+\(.*\n.*)", raw, re.DOTALL)
            func_code = m.group(1).rstrip() if m else ""
        else:
            func_code = extract_function(output_text)

        # --- Extract checks ---
        if checks_source == "asserts":
            checks = _extract_asserts(output_text)
        else:
            func_name = re.match(r"def (\w+)\s*\(", func_code).group(1) if func_code else None
            checks = []

        # --- Run ---
        if not func_code:
            return _make_score(0.0, "no function definition found", state)
        if not checks:
            # For testcases mode with unknown function, fall back to includes match
            if checks_source == "testcases" and func_name:
                target_text = target.text.lower()
                correctness = 1.0 if target_text in output_text.lower() else 0.0
                return _make_score(
                    correctness,
                    f"unknown function {func_name}, fallback to includes",
                    state,
                )
            return _make_score(0.0, "no checks found", state)

        script = build_script(func_code, checks)
        passed, total, stderr = run_checks(script, len(checks))
        correctness = passed / total if total > 0 else 0.0
        detail = f"{passed}/{total} passed"
        if stderr:
            detail += f" | {stderr.split(chr(10))[0][:80]}"
        return _make_score(correctness, detail, state)

    return score
