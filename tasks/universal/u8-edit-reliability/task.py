"""U8 Edit Reliability: model must handle edit tool edge cases.

SEE doc/EVAL-TASKS.md Part III §U8 for full design notes.
Evidence: 5.6% of 3,864 agent bugs are edit tool failures.
"String to replace not found" is the #1 reported Claude Code failure.
No benchmark tests this — all assume edits succeed.

This is a Phase 2 stub — text-based scenarios for model eval mode.
Agent eval with real file editing under interference (Docker sandbox) is Phase 3.
"""

from inspect_ai import Task, task
from inspect_ai.dataset import FieldSpec, json_dataset

from scorers.llm_judge import llm_judge
from scorers.price_ratio import price_ratio_scorer
from scorers.task_budgets import get_task_budget
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer


@task
def u8_edit_reliability():
    """Evaluate awareness of edit tool reliability edge cases.

    Empirical study (3,864 bugs): 5.6% of all coding agent bugs are edit
    tool failures. "String to replace not found" is the #1 reported Claude
    Code failure. Race conditions, stale reads, CRLF mismatches.

    No benchmark tests this — all assume edits succeed.

    This task tests whether the model:
    1. Reads file content before editing (avoids stale reads)
    2. Handles whitespace variations (avoids CRLF mismatches)
    3. Recognizes when an edit fails and reports it correctly
    4. Uses safer alternatives when edit tool is unreliable

    ## Scenarios (from dataset.json)
    1. Stale read: file changed between Read and Edit (formatter ran)
    2. CRLF mismatch: mixed line endings, edit across both types
    3. Edit failure report: when string-not-found occurs, does it report clearly?
    4. Sed fallback: does it use sed/Write when Edit repeatedly fails?
    """
    return Task(
        dataset=json_dataset(
            "dataset.json",
            FieldSpec(input="input", target="target", id="id"),
        ),
        scorer=[
            llm_judge(),
            token_ratio_scorer(task_budget=get_task_budget("u8_edit_reliability")),
            time_ratio_scorer(task_budget=get_task_budget("u8_edit_reliability")),
            price_ratio_scorer(task_budget=get_task_budget("u8_edit_reliability")),
        ],
    )
