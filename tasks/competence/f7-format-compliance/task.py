"""F7 Format Compliance: model must output valid JSON with exact key structure."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh


@task
def f7_format_compliance():
    """Evaluate ability to produce structurally exact JSON output.

    Given unstructured text data, the model must output a JSON array with
    objects containing exact keys (name, score, passed) and correct types.
    No markdown fences, no extra text — raw JSON only.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[verify_sh(), token_ratio_scorer(task_budget=get_task_budget("f7_format_compliance")), time_ratio_scorer(task_budget=get_task_budget("f7_format_compliance")), price_ratio_scorer(task_budget=get_task_budget("f7_format_compliance"))],
    )
