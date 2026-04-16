"""F15 Workspace Setup Agent: agent must create a complete Python project structure."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def f15_workspace_setup():
    """Evaluate multi-step project creation and verification.

    The agent must create a complete Python project structure including
    directory layout, source files, tests, and verify everything works.
    Tests whether agents can reliably execute multi-step instructions
    without hallucinating file contents or skipping requirements.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            verify_sh(),
            token_ratio_scorer(task_budget=get_task_budget("f15_workspace_setup")),
            time_ratio_scorer(task_budget=get_task_budget("f15_workspace_setup")),
            price_ratio_scorer(task_budget=get_task_budget("f15_workspace_setup")),
        ],

    )