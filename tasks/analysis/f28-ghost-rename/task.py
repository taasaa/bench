"""F28 Ghost Rename: test if model proactively fixes dependents despite narrow instructions."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.hybrid import hybrid_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer

@task
def f28_ghost_rename():
    """Evaluate agency in refactoring.
    
    Model is instructed to rename a field in 2 files, but a 3rd file has a raw SQL
    dependency on the field. A smart model will update the 3rd file too.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            hybrid_scorer(),
            token_ratio_scorer(task_budget=get_task_budget("f28_ghost_rename")),
            time_ratio_scorer(task_budget=get_task_budget("f28_ghost_rename")),
            price_ratio_scorer(task_budget=get_task_budget("f28_ghost_rename")),
        ],
    )
