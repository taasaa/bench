"""Smoke test task: minimal eval to verify Inspect AI + LiteLLM wiring."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset
from inspect_ai.scorer import includes


@task
def smoke():
    """Minimal verification that inspect eval runs end-to-end.

    One trivial sample, includes() scorer. Proves model connectivity,
    EvalLog creation, and scoring pipeline all work.
    """
    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        scorer=includes(),
    )
