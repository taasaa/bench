"""F11 Intermittent Bug: model must identify timing/race conditions, not suggest more sleep."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.llm_judge import llm_judge
from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer


@task
def f11_intermittent_bug():
    """Evaluate ability to identify timing/race conditions in intermittent failures.

    Given test failures that pass locally but fail intermittently in CI,
    the model must identify timing issues, race conditions, or flaky
    assumptions rather than suggesting superficial fixes like increasing
    sleep durations or timeouts.

    Graded by LLM judge — open-ended diagnosis with many valid phrasings.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[llm_judge(), token_ratio_scorer(task_budget=get_task_budget("f11_intermittent_bug")), time_ratio_scorer(task_budget=get_task_budget("f11_intermittent_bug")), price_ratio_scorer(task_budget=get_task_budget("f11_intermittent_bug"))],
    )
