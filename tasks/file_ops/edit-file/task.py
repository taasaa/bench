"""Edit-file task: model must apply specific edits to provided file content."""

from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec

from scorers.composite import composite


@task
def edit_file():
    """Evaluate ability to apply targeted edits to file content.

    Covers adding imports, renaming variables, changing function signatures,
    and inserting code blocks. Scoring uses composite: (correctness * 0.67 + efficiency * 0.33) * safety_gate.
    """
    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        scorer=composite(),
    )
