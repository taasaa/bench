"""F20 Scope Calibration: model must make exactly one text change and nothing else."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer
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
        scorer=[verify_sh(), token_ratio_scorer(task_budget=get_task_budget("f20_scope_calibration")), time_ratio_scorer(task_budget=get_task_budget("f20_scope_calibration")), price_ratio_scorer(task_budget=get_task_budget("f20_scope_calibration"))],
    )
