"""Write-function task: model must produce correct Python function implementations."""

from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec

from scorers.composite import composite


@task
def write_function():
    """Evaluate ability to write Python functions from natural-language specs.

    Covers list processing, string manipulation, and algorithmic thinking.
    Scoring uses composite: (correctness * 0.67 + efficiency * 0.33) * safety_gate.
    """
    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        scorer=composite(),
    )
