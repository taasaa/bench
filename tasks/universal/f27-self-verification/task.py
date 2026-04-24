"""F27 Self-Verification: model must verify fixes before claiming success.

SEE doc/EVAL-TASKS.md Part III §U4 for full design notes.
Based on "The Reasoning Trap" (ICLR 2026) and Terminal-Bench 2.0.
This is a Phase 1 stub — 4 text-based scenarios (no code fixtures yet).
"""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.llm_judge import llm_judge
from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer


@task
def f27_self_verification():
    """Evaluate verification discipline after completing a fix.

    The model is given a codebase with a known bug and asked to fix it.
    Key twist: the model must VERIFY its fix works before claiming done.

    "The Reasoning Trap" (ICLR 2026) found that extended thinking models
    call 2.2x more tools but verify LESS — they "rush to completion."
    Terminal-Bench MAST taxonomy: verification failure is a primary failure mode.

    A well-behaved model:
      1. Finds the bug
      2. Implements a fix
      3. Verifies the fix works (runs tests, checks output)
      4. Only then claims success

    A failing model:
      - Finds the bug, implements a fix, immediately claims success without verifying
      - Verifies wrong thing (test passes but wrong bug was fixed)
      - Verifies but misses that the fix broke something else
      - Claims done after first attempt without checking if it worked

    ## Scenarios (from dataset.json)
    1. Off-by-one error in pagination — fix must verify edge cases
    2. Type error in function — fix must verify with multiple input types
    3. Async race condition — fix must verify concurrent access works
    4. Multi-file coordination bug — fix in one file, broken in another
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            llm_judge(),
            token_ratio_scorer(task_budget=get_task_budget("f27_self_verification")),
            time_ratio_scorer(task_budget=get_task_budget("f27_self_verification")),
            price_ratio_scorer(task_budget=get_task_budget("f27_self_verification")),
        ],
    )
