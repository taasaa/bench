"""F23 Ghost Constraint: model must retain constraints across multi-turn evaluation."""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from bench_cli.solvers.multishot import multishot_solver
from scorers.hybrid import hybrid_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer


@task
def f23_ghost_constraint():
    """Evaluate cross-turn constraint retention.

    Inline samples present constraints directly in the prompt. Fixture samples
    bury constraints in workspace documents the model must discover.

    The model must apply constraints consistently across all functions it writes.
    Tests whether models follow constraints stated once at the beginning, or
    forget them as the task grows longer.

    Hybrid scoring: verify_sh checks structural compliance (snake_case, type
    hints, httpx usage), llm_judge evaluates constraint consistency quality.
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        solver=multishot_solver(max_turns=5),
        scorer=[
            hybrid_scorer(),
            token_ratio_scorer(task_budget=get_task_budget("f23_ghost_constraint")),
            time_ratio_scorer(task_budget=get_task_budget("f23_ghost_constraint")),
            price_ratio_scorer(task_budget=get_task_budget("f23_ghost_constraint")),
        ],
    )
