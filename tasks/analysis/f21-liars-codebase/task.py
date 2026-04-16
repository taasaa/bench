"""F21 Liar's Codebase: model must identify discrepancies between docs and actual code."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.llm_judge import llm_judge
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer


@task
def f21_liars_codebase():
    """Evaluate ability to detect discrepancies between documentation claims and actual code.

    The model is given code files alongside developer claims about what the code does.
    Each scenario contains planted discrepancies between what docs/claims say and what
    the code actually implements. The model must identify these discrepancies rather
    than trusting the claims at face value.

    Tests whether models verify claims against actual code rather than blindly
    agreeing with documentation — a critical code review skill.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[llm_judge(), token_ratio_scorer(task_budget=get_task_budget("f21_liars_codebase")), time_ratio_scorer(task_budget=get_task_budget("f21_liars_codebase"))],
    )
