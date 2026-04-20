"""LLM judge scorer: uses a separate evaluator model to grade model output.

Calls a fixed judge model (never the model under test) with a per-task rubric
from judge.md. The judge returns a SCORE: N rating (0-10) which is normalized
to 0.0-1.0 for the correctness pillar. Values are snapped to the discrete
5-point scale {0, 2.5, 5, 7.5, 10} → {0.0, 0.25, 0.5, 0.75, 1.0}.

Falls back to 0.0 with diagnostic explanation on any failure (missing rubric,
API error, unparseable response).

See: doc/SCORING-SYSTEM-PRD.md §LLMJudgeScorer
"""

from __future__ import annotations

import os
import re

from inspect_ai.model import ChatMessageUser, get_model
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

DEFAULT_JUDGE_MODEL = "openai/judge"
RUBRIC_FILENAME = "judge.md"

# Regex to extract score from judge response.
# Matches: SCORE: 8, Score: 7.5, score: 10, SCORE:8/10, etc.
_SCORE_RE = re.compile(
    r"(?i)SCORE\s*:\s*(\d+(?:\.\d+)?)\s*(?:/\s*10)?(?!\d)"
)

# Template for judge prompt
_JUDGE_TEMPLATE = """\
You are an expert evaluator grading a model's response to a task.

## Task
{question}

## Expected Answer
{target}

## Model's Response
{answer}

## Grading Rubric
{rubric}

## Instructions
Grade the model's response according to the rubric above. Provide your reasoning,
then end with your score on a 0-10 scale using this exact format:

SCORE: <number>

You MUST use one of exactly these five values: 0, 2.5, 5, 7.5, or 10.
Do NOT use any other value. Choose the closest level that matches the response quality.
"""


def _load_rubric(task_dir: str) -> str | None:
    """Load judge.md rubric from task directory."""
    rubric_path = os.path.join(task_dir, RUBRIC_FILENAME)
    if not os.path.isfile(rubric_path):
        return None
    try:
        with open(rubric_path) as f:
            return f.read().strip()
    except OSError:
        return None


_DISCRETE_VALUES = (0.0, 2.5, 5.0, 7.5, 10.0)


def _snap_to_discrete(raw: float) -> float:
    """Snap a 0-10 value to the nearest discrete level."""
    return min(_DISCRETE_VALUES, key=lambda d: abs(d - raw))


def _parse_score(response: str) -> float | None:
    """Extract score from judge response. Returns 0.0-1.0 or None.

    Snaps to the discrete 5-point scale before normalizing.
    """
    match = _SCORE_RE.search(response)
    if match is None:
        return None
    raw = float(match.group(1))
    raw = max(0.0, min(10.0, raw))
    snapped = _snap_to_discrete(raw)
    return snapped / 10.0


@scorer(metrics=[mean()])
def llm_judge(
    judge_model: str = DEFAULT_JUDGE_MODEL,
) -> None:
    """Score correctness using an LLM judge with per-task rubric.

    The scorer reads a judge.md file from the task directory containing
    task-specific grading instructions. It calls the judge model with
    the model's output, expected answer, and rubric, then parses the
    SCORE: N response (0-10, normalized to 0-1).

    Args:
        judge_model: Model string for the judge (default: openai/judge).
            Routed through LiteLLM proxy.
    """
    # Resolve model once at factory time, reused across all samples.
    model = get_model(judge_model)

    # Rubric cache keyed by task directory — loaded once per task, not per sample.
    _rubric_cache: dict[str, str | None] = {}

    def _get_rubric(task_dir: str) -> str | None:
        if task_dir not in _rubric_cache:
            _rubric_cache[task_dir] = _load_rubric(task_dir)
        return _rubric_cache[task_dir]

    async def score(state: TaskState, target: Target) -> Score:
        # Find task directory from metadata (injected by _resolve_task in run.py)
        task_dir = state.metadata.get("bench_task_dir") if state.metadata else None

        # Load rubric
        if task_dir is None:
            return Score(
                value=0.0,
                explanation="llm_judge: no bench_task_dir in metadata",
                metadata={"pillar": "correctness", "judge_error": "no_task_dir"},
            )

        rubric = _get_rubric(task_dir)
        if rubric is None:
            return Score(
                value=0.0,
                explanation=f"llm_judge: no {RUBRIC_FILENAME} found in {task_dir}",
                metadata={
                    "pillar": "correctness",
                    "judge_error": "missing_rubric",
                    "task_dir": task_dir,
                },
            )

        # Build prompt
        output_text = state.output.completion if state.output else ""
        if not output_text:
            return Score(
                value=0.0,
                explanation="llm_judge: empty model output",
                metadata={"pillar": "correctness", "judge_error": "empty_output"},
            )

        prompt = _JUDGE_TEMPLATE.format(
            question=state.input_text,
            target=target.text,
            answer=output_text,
            rubric=rubric,
        )

        # Call judge model (resolved once at factory time)
        try:
            result = await model.generate([ChatMessageUser(content=prompt)])
        except Exception as exc:
            return Score(
                value=0.0,
                explanation=f"llm_judge: judge API error: {exc}",
                metadata={
                    "pillar": "correctness",
                    "judge_error": "api_error",
                    "exception": str(exc),
                },
            )

        judge_response = result.completion

        # Parse score
        parsed = _parse_score(judge_response)
        if parsed is None:
            return Score(
                value=0.0,
                explanation="llm_judge: could not parse score from judge response",
                metadata={
                    "pillar": "correctness",
                    "judge_error": "unparseable",
                    "judge_response": judge_response[:500],
                },
            )

        return Score(
            value=parsed,
            explanation=f"correctness={parsed:.2f}\n{judge_response}",
            metadata={
                "pillar": "correctness",
                "judge_score_raw": parsed * 10,
                "judge_response": judge_response,
                "judge_model": judge_model,
            },
        )

    return score
