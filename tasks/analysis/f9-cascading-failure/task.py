"""F9 Cascading Failure: model must identify root cause, not treat symptoms."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.hybrid import hybrid_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer


@task
def f9_cascading_failure():
    """Evaluate deep root-cause analysis of cascading failures.

    Given a scenario where a service appears to be failing, the model must
    distinguish between a service that is down vs. one that is misconfigured,
    and identify the true root cause (pool exhaustion, fd leak, unbounded
    cache, thread starvation) rather than suggesting symptom workarounds.

    Hybrid scoring: verify_sh checks key factual answers, llm_judge evaluates
    reasoning depth and root-cause quality.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            hybrid_scorer(),
            token_ratio_scorer(task_budget=get_task_budget("f9_cascading_failure")),
            time_ratio_scorer(task_budget=get_task_budget("f9_cascading_failure")),
            price_ratio_scorer(task_budget=get_task_budget("f9_cascading_failure")),
        ],
    )
