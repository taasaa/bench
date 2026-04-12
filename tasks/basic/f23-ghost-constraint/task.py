"""F23 Ghost Constraint: model must retain constraints from Turn 1 and apply them across Turns 2-4."""

from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset, FieldSpec

from scorers.verify_sh import verify_sh


@task
def f23_ghost_constraint():
    """Evaluate cross-turn constraint retention.

    The model receives a single prompt with 4 labeled turns. Turn 1 states
    constraints (snake_case naming, type hints, httpx not requests).
    Turns 2-4 ask it to write functions. The model must apply the Turn-1
    constraints to all subsequent code — even though it's never reminded.

    Tests whether models actually follow constraints stated once at the
    beginning, or forget them as the prompt grows longer. A common failure
    mode is switching to camelCase, dropping type hints, or using the
    requests library by default.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=verify_sh(),
    )
