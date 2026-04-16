"""F5 Multi-Constraint Edit: model must refactor code while satisfying 5 simultaneous constraints."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def f5_multi_constraint_edit():
    """Evaluate ability to refactor code with multiple simultaneous constraints.

    The model receives a Python file and must refactor it while satisfying
    5 constraints: extract validation logic, preserve signatures, keep
    the main block, preserve docstrings, and add type hints only to the
    new function.

    Tests whether models can follow multiple interacting constraints at once
    without violating any — a common real-world refactoring requirement.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[verify_sh(), token_ratio_scorer(task_budget=get_task_budget("f5_multi_constraint_edit")), time_ratio_scorer(task_budget=get_task_budget("f5_multi_constraint_edit")), price_ratio_scorer(task_budget=get_task_budget("f5_multi_constraint_edit"))],
    )
