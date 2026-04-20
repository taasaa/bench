"""U18 Resume After Bad Attempt: model must recover from a partially-correct prior attempt."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from bench_cli.solvers.multishot import multishot_solver
from scorers.hybrid import hybrid_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer


@task
def u18_resume_after_bad_attempt():
    """Evaluate ability to resume work after a partially-correct prior attempt.

    The model receives a workspace with:
    - A buggy source file (scheduler.py) with a known defect
    - A correct helper module (duration.py) with the right utility
    - ATTEMPT_NOTES.md documenting a prior developer's analysis and false leads

    The model must read the prior attempt notes, understand the bug, and produce
    a correct fix that reuses the existing helper — not start from scratch.

    Hybrid scoring: verify_sh checks structural correctness (correct import,
    right function used), llm_judge evaluates reasoning quality.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        solver=multishot_solver(max_turns=5),
        scorer=[
            hybrid_scorer(),
            token_ratio_scorer(task_budget=get_task_budget("u18_resume_after_bad_attempt")),
            time_ratio_scorer(task_budget=get_task_budget("u18_resume_after_bad_attempt")),
            price_ratio_scorer(task_budget=get_task_budget("u18_resume_after_bad_attempt")),
        ],
    )
