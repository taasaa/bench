"""Find-replace task: model must perform find-and-replace operations on file content."""

from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec

from scorers.composite import composite


@task
def find_replace():
    """Evaluate ability to find and replace code patterns across file content.

    Covers multi-line replacements, pattern-based changes, and structural edits.
    Scoring uses composite: (correctness * 0.67 + efficiency * 0.33) * safety_gate.
    """
    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        scorer=composite(),
    )
