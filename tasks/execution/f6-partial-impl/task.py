"""F6 Partial Implementation: model must implement a minimal class with only specified methods."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.verify_sh import verify_sh


@task
def f6_partial_impl():
    """Evaluate resistance to feature creep.

    Given a prompt asking for a minimal class with only specified methods,
    the model must implement exactly those methods and no others.
    No delete, no clear, no TTL enforcement, no extra helper methods.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=verify_sh(),
    )
