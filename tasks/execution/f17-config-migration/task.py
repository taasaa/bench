"""F17 Config Migration Agent: agent must migrate config from python-dotenv to pydantic-settings."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def f17_config_migration():
    """Evaluate config migration with zero behavior change.

    The agent migrates a project from python-dotenv (os.environ.get)
    to pydantic-settings while preserving all business logic and API
    behavior. Tests whether agents can do mechanical refactoring
    without accidentally changing functionality.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            verify_sh(),
            token_ratio_scorer(task_budget=get_task_budget("f17_config_migration")),
            time_ratio_scorer(task_budget=get_task_budget("f17_config_migration")),
        ],

    )