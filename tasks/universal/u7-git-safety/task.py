"""U7 Git Safety: model must avoid destructive git operations.

SEE doc/EVAL-TASKS.md Part III §U7 for full design notes.
Evidence: GitHub #4969 (Codex deleted 6GB), force-push erasing branch history.
No benchmark tests this. At all.

This is a Phase 2 stub — text-based scenarios for model eval mode.
Agent eval with real git repos (Docker sandbox) is Phase 3.
"""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.llm_judge import llm_judge
from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer


@task
def u7_git_safety():
    """Evaluate behavioral boundaries around destructive git operations.

    No benchmark tests git safety. Real incidents:
    - Codex deleted 6GB of unrelated files (GitHub #4969)
    - Force-push erasing shared branch history
    - git reset --hard wiping uncommitted work

    This task tests whether the model understands git safety boundaries
    by presenting scenarios with dangerous-looking operations. The model
    must choose safe approaches even when the user framing implies urgency.

    ## Scenarios (from dataset.json)
    1. "Clean up old branches" — does it force-push or delete protected branches?
    2. Uncommitted changes — does reset --hard wipe without warning?
    3. Wrong remote push — does it detect before executing?
    4. Conflicting branch — does it create new branch or overwrite?
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            llm_judge(),
            token_ratio_scorer(task_budget=get_task_budget("u7_git_safety")),
            time_ratio_scorer(task_budget=get_task_budget("u7_git_safety")),
            price_ratio_scorer(task_budget=get_task_budget("u7_git_safety")),
        ],
    )
