"""F10 Environmental Mismatch: model must diagnose multi-layer version/environment mismatches."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.llm_judge import llm_judge
from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer


@task
def f10_env_mismatch():
    """Evaluate ability to diagnose multi-layer environment mismatches.

    Given a scenario where no single clue is sufficient, the model must chain
    shebang resolution, PATH/alias, and version manager settings to identify
    the root cause — a mismatch between the environment the package was
    installed in and the environment the script actually runs in.

    Graded by LLM judge — open-ended diagnosis with many valid phrasings.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[llm_judge(), token_ratio_scorer(task_budget=get_task_budget("f10_env_mismatch")), time_ratio_scorer(task_budget=get_task_budget("f10_env_mismatch")), price_ratio_scorer(task_budget=get_task_budget("f10_env_mismatch"))],
    )
