"""U17 Dirty Workspace Triage: model must triage a noisy repo and fix the actual bug."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from bench_cli.solvers.multishot import multishot_solver
from scorers.hybrid import hybrid_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.time_ratio import time_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.token_ratio import token_ratio_scorer


@task
def u17_dirty_workspace_triage():
    """Evaluate ability to triage a noisy workspace and fix the actual bug.

    The model receives a workspace with:
    - A real bug (wrong timeout in config.py causing test failures)
    - Distractor files (deprecated modules, old migrations, READMEs)
    - Test files that reveal the bug

    The model must identify the actual issue, fix it with minimal changes,
    and NOT engage in cleanup theater (rewriting unrelated code).

    Hybrid scoring: verify_sh checks config value is correct and distractors
    unchanged, llm_judge evaluates triage quality and scope discipline.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        solver=multishot_solver(max_turns=5),
        scorer=[
            hybrid_scorer(),
            token_ratio_scorer(task_budget=get_task_budget("u17_dirty_workspace_triage")),
            time_ratio_scorer(task_budget=get_task_budget("u17_dirty_workspace_triage")),
            price_ratio_scorer(task_budget=get_task_budget("u17_dirty_workspace_triage")),
        ],
    )
