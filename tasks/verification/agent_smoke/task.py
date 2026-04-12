"""Agent eval smoke test: verify claude_code() solver works in Docker sandbox."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset
from inspect_ai.scorer import includes
from inspect_swe import claude_code


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
      OPENAI_BASE_URL=http://smallbox:4000/v1 OPENAI_API_KEY=sk-1234 \\
        inspect eval tasks/verification/agent_smoke/task.py \\
        --model openai/rut-small --max-tasks 1 --time-limit 300
    """
    return Task(
        dataset=json_dataset(
            "dataset.json", FieldSpec(input="input", target="target", id="id")
        ),
        solver=claude_code(),
        scorer=includes(),
        sandbox="docker",
    )
