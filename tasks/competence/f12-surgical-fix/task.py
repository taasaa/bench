"""F12 Surgical Fix: model must fix exactly one buggy line without touching anything else."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.verify_sh import verify_sh


@task
def f12_surgical_fix():
    """Evaluate ability to make minimal, precise code fixes.

    Given a small Python function containing a single bug (off-by-one,
    wrong operator, boundary error), the model must fix exactly the buggy
    line and return the complete function with no other changes.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=verify_sh(),
    )
