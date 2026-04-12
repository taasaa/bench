"""Q1 Verification Gate: model must analyze test output and report failures accurately."""

from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec

from scorers.verify_sh import verify_sh


@task
def q1_verification_gate():
    """Evaluate ability to parse and summarize test suite output.

    Given pytest output with some failures, the model must report:
    1. How many tests passed
    2. How many tests failed
    3. Which specific tests failed (by name)
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=verify_sh(),
    )
