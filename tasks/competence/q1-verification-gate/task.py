"""Q1 Verification Gate: model must analyze test output and report failures accurately."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def q1_verification_gate():
    """Evaluate ability to parse and summarize test suite output.

    Given pytest output with some failures, the model must report:
    1. How many tests passed
    2. How many tests failed
    3. Which specific tests failed (by name)
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[verify_sh(), token_ratio_scorer(task_budget=get_task_budget("q1_verification_gate")), time_ratio_scorer(task_budget=get_task_budget("q1_verification_gate")), price_ratio_scorer(task_budget=get_task_budget("q1_verification_gate"))],
    )
