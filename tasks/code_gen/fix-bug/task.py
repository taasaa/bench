"""Fix-bug task: model must identify and correct bugs in Python code snippets."""

from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec

from scorers.composite import composite


@task
def fix_bug():
    """Evaluate ability to diagnose and fix bugs in Python code.

    Covers syntax errors, off-by-one errors, wrong operators, and logic mistakes.
    Scoring uses composite: (correctness * 0.67 + efficiency * 0.33) * safety_gate.
    """
    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        scorer=composite(),
    )
