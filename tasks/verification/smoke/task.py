"""Smoke test task: minimal eval to verify Inspect AI + LiteLLM wiring."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset
from inspect_ai.scorer import includes


@task
def smoke():
    """Minimal verification that inspect eval runs end-to-end.

    One trivial sample, includes() scorer. compare.py's _numeric_val()
    handles the 'C'/'I' string return values correctly.
    """
    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        scorer=includes(),
    )
