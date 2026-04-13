"""F8 Negative Constraint Chain: model must follow 5 negative constraints."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.composite_safety import composite_safety_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def f8_negative_constraint():
    """Evaluate ability to follow a chain of negative constraints.

    Given a prompt asking for a requests-based function with specific error
    handling but explicit prohibition of retry, logging, caching, rate limiting,
    and extra libraries. The model must implement exactly what's asked — nothing more.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[verify_sh(), token_ratio_scorer(), time_ratio_scorer(), composite_safety_scorer()],
    )
