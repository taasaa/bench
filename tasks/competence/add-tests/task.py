"""Add-tests task: model must write unit tests for given function signatures."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def add_tests():
    """Evaluate ability to write comprehensive unit tests for Python functions.

    Covers edge cases, normal inputs, and boundary conditions.
    """
    return Task(
        dataset=json_dataset("dataset.json", FieldSpec(input="input", target="target", id="id")),
        scorer=[verify_sh(), token_ratio_scorer(task_budget=get_task_budget("add_tests")), time_ratio_scorer(task_budget=get_task_budget("add_tests")), price_ratio_scorer(task_budget=get_task_budget("add_tests"))],
    )
