"""Q4 Root Cause Not Symptom: model must identify root cause rather than treating symptoms."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.hybrid import hybrid_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer


@task
def q4_root_cause():
    """Evaluate ability to identify root causes rather than treating symptoms.

    Given a problem description involving environment mismatches, path issues,
    or configuration conflicts, the model must identify the underlying root
    cause and provide a specific fix rather than workarounds that only
    address symptoms.

    Hybrid scoring: verify_sh checks key diagnostic answers, llm_judge evaluates
    root-cause reasoning quality.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[hybrid_scorer(), token_ratio_scorer(task_budget=get_task_budget("q4_root_cause")), time_ratio_scorer(task_budget=get_task_budget("q4_root_cause")), price_ratio_scorer(task_budget=get_task_budget("q4_root_cause"))],
    )
