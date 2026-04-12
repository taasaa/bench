"""F20 Scope Calibration: model must make exactly one text change and nothing else."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.verify_sh import verify_sh


@task
def f20_scope_calibration():
    """Evaluate ability to make exactly the requested change.

    Given a file and a single string replacement instruction, the model
    must change only the specified text — no formatting changes, no extra
    edits, no unnecessary explanations. Tests scope discipline.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=verify_sh(),
    )
