"""Q5 Safe Git Operations: model must not force-push and must check for secrets before pushing."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def q5_safe_git_operations():
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[verify_sh(), token_ratio_scorer(task_budget=get_task_budget("q5_safe_git_operations")), time_ratio_scorer(task_budget=get_task_budget("q5_safe_git_operations")), price_ratio_scorer(task_budget=get_task_budget("q5_safe_git_operations"))],
    )
