"""F14 Insert Don't Replace: model must add code between existing lines without modifying them."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def f14_insert_dont_replace():
    """Evaluate ability to insert new code without modifying existing lines.

    Given a function missing a step, the model must add the missing logic
    between existing lines without altering any of the original code.
    Tests whether models can make precise insertions instead of wholesale
    rewrites.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[verify_sh(), token_ratio_scorer(task_budget=get_task_budget("f14_insert_dont_replace")), time_ratio_scorer(task_budget=get_task_budget("f14_insert_dont_replace"))],
    )
