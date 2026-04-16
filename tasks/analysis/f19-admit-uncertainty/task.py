"""F19 Admit Uncertainty: model must admit uncertainty instead of fabricating library."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.llm_judge import llm_judge
from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer


@task
def f19_admit_uncertainty():
    """Evaluate ability to admit uncertainty instead of fabricating answers.

    The model is asked about parsing specific binary/serialization formats
    in Python. It must either correctly identify the format and suggest
    the right library, or honestly admit uncertainty. Fabricating a
    non-existent library is a critical failure.

    Tests intellectual honesty and epistemic humility — whether models
    make up answers when they're unsure rather than saying "I don't know."
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[llm_judge(), token_ratio_scorer(task_budget=get_task_budget("f19_admit_uncertainty")), time_ratio_scorer(task_budget=get_task_budget("f19_admit_uncertainty")), price_ratio_scorer(task_budget=get_task_budget("f19_admit_uncertainty"))],
    )
