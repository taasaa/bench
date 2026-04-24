"""F21 Liar's Codebase: model must identify discrepancies between docs and actual code."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from bench_cli.solvers.multishot import multishot_solver
from scorers.hybrid import hybrid_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer


@task
def f21_liars_codebase():
    """Evaluate ability to detect discrepancies between documentation claims and actual code.

    Inline samples embed code in the prompt. Fixture samples provide workspace
    files the model must explore to find discrepancies between docs and reality.

    Tests whether models verify claims against actual code rather than blindly
    agreeing with documentation — a critical code review skill.

    Hybrid scoring: verify_sh checks the model identifies the correct TRUE/FALSE
    answer and key discrepancies, llm_judge evaluates evidence quality.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        solver=multishot_solver(max_turns=5),
        scorer=[
            hybrid_scorer(),
            token_ratio_scorer(task_budget=get_task_budget("f21_liars_codebase")),
            time_ratio_scorer(task_budget=get_task_budget("f21_liars_codebase")),
            price_ratio_scorer(task_budget=get_task_budget("f21_liars_codebase")),
        ],
    )
