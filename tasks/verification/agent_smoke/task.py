"""Agent eval smoke test: verify agent solver works in Docker sandbox."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState


@scorer(metrics=[mean()])
def includes_numeric() -> None:
    """Like includes() but returns 1.0/0.0 instead of 'C'/'I'.

    The standard includes() scorer returns string values incompatible
    with compare.py's _numeric_val(). This scorer preserves the same
    check semantics (target text present in output) but returns numeric
    values.
    """

    async def score(state: TaskState, target: Target) -> Score:
        output_text = state.output.completion if state.output else ""
        value = 1.0 if target.text.lower() in output_text.lower() else 0.0
        return Score(
            value=value,
            explanation=f"Target '{target.text}' {'found' if value else 'not found'} in output",
            metadata={"pillar": "correctness"},
        )

    return score


@task
def agent_smoke():
    """Minimal verification that agent eval runs end-to-end.

    Uses claude_code() solver in a Docker sandbox with one trivial
    coding task. Proves sandbox creation, agent execution, and
    EvalLog with agent transcript + tool calls all work.

    Prerequisites:
      - Docker must be running
      - OPENAI_API_KEY must be set to the LiteLLM proxy key (e.g. sk-1234)
      - OPENAI_BASE_URL must be set to the LiteLLM proxy (e.g. http://smallbox:4000/v1)
      - anthropic package must be installed (pip install anthropic)

    Run example:
      bench run --tier quick --task agent_smoke --agent claude
    """
    from inspect_swe import claude_code  # type: ignore[import-untyped]

    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        solver=claude_code(),
        scorer=includes_numeric(),
        sandbox="docker",
    )
