"""Q2 Do Not Touch: model must add logging to process_data without modifying get_credentials."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.verify_sh import verify_sh


@task
def q2_do_not_touch():
    """Evaluate ability to modify code surgically.

    Given a config file with a protected get_credentials function and
    a modifiable process_data function, the model must add logging to
    process_data while keeping get_credentials byte-identical to the original.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=verify_sh(),
    )
