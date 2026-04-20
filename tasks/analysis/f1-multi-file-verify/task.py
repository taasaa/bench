"""F1 Multi-File Verification: cross-reference model claims against actual code."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.hybrid import hybrid_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer


@task
def f1_multi_file_verify():
    """Evaluate multi-file code verification ability.

    The model is told a developer claims "all tests pass and the service works"
    for a 3-file project. It must verify this claim by reading all 3 files,
    finding 2 planted bugs, and correctly reporting the claim is FALSE.

    Tests whether models actually read code carefully rather than agreeing
    with the developer's claim, and whether they can identify subtle bugs
    like wrong attribute names, missing imports, field name mismatches,
    and mutation side effects.

    Hybrid scoring: verify_sh checks structural answers, llm_judge evaluates
    verification quality and evidence.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[hybrid_scorer(), token_ratio_scorer(task_budget=get_task_budget("f1_multi_file_verify")), time_ratio_scorer(task_budget=get_task_budget("f1_multi_file_verify")), price_ratio_scorer(task_budget=get_task_budget("f1_multi_file_verify"))],
    )
