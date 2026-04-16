"""F9 Cascading Failure: model must identify root cause, not treat symptoms."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.llm_judge import llm_judge
from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer


@task
def f9_cascading_failure():
    """Evaluate deep root-cause analysis of cascading failures.

    Given a scenario where a service appears to be failing, the model must
    distinguish between a service that is down vs. one that is misconfigured,
    and identify the true root cause (pool exhaustion, fd leak, unbounded
    cache, thread starvation) rather than suggesting symptom workarounds.

    Graded by LLM judge — open-ended analysis with many valid framings.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[llm_judge(), token_ratio_scorer(task_budget=get_task_budget("f9_cascading_failure")), time_ratio_scorer(task_budget=get_task_budget("f9_cascading_failure")), price_ratio_scorer(task_budget=get_task_budget("f9_cascading_failure"))],
    )
