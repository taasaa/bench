"""Add-tests task: model must write unit tests for given function signatures."""

from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec

from scorers.composite import composite


@task
def add_tests():
    """Evaluate ability to write comprehensive unit tests for Python functions.

    Covers edge cases, normal inputs, and boundary conditions.
    Scoring uses composite: (correctness * 0.67 + efficiency * 0.33) * safety_gate.
    """
    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        scorer=composite(),
    )
