"""F4 Dependency Version Audit: model must identify inconsistencies between pyproject.toml and lock files."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.llm_judge import llm_judge
from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer


@task
def f4_dependency_version_audit():
    """Evaluate ability to detect dependency inconsistencies.

    Given a pyproject.toml and a package-lock.json with planted
    inconsistencies, the model must identify all discrepancies:
    missing packages, version mismatches, and deprecated packages.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[llm_judge(), token_ratio_scorer(task_budget=get_task_budget("f4_dependency_version_audit")), time_ratio_scorer(task_budget=get_task_budget("f4_dependency_version_audit")), price_ratio_scorer(task_budget=get_task_budget("f4_dependency_version_audit"))],
    )
