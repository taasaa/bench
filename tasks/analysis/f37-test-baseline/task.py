"""F37 TEST BASELINE: Test Invariants"""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.hybrid import hybrid_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer

@task
def f37_test_baseline():
    """Test Invariants"""
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            hybrid_scorer(),
            token_ratio_scorer(task_budget=get_task_budget("f37_test_baseline")),
            time_ratio_scorer(task_budget=get_task_budget("f37_test_baseline")),
            price_ratio_scorer(task_budget=get_task_budget("f37_test_baseline")),
        ],
    )
