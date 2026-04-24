"""F16 Bug Investigation Agent: agent must find and fix a bug with minimal changes."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def f16_bug_investigation():
    """Evaluate surgical bug investigation and minimal fix.

    The agent is given a broken codebase and must find the specific
    bug causing the failure, fix only that, and not make unrelated
    changes. Tests debugging discipline and surgical precision.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            verify_sh(),
            token_ratio_scorer(task_budget=get_task_budget("f16_bug_investigation")),
            time_ratio_scorer(task_budget=get_task_budget("f16_bug_investigation")),
            price_ratio_scorer(task_budget=get_task_budget("f16_bug_investigation")),
        ],
    )
