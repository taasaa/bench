# Judge Rubric: Intermittent Test Failure Diagnosis

## Task
The model receives a scenario where tests pass locally but fail intermittently in CI. It must identify the root cause as timing/race-condition related and suggest a proper fix (not just "add more sleep").

## Grading Criteria

1. **Root cause identified** - Response identifies the issue as timing-dependent, a race condition, or non-deterministic ordering (not a logic bug or missing dependency).
2. **Proper fix suggested** - Response recommends a real fix such as polling, waiting for a condition, mocking/freezing time, using events, or subprocess.wait (not simply increasing sleep duration).
3. **Avoids superficial fixes** - Response does NOT recommend "increase sleep", "add more sleep", "use a longer timeout", or similar band-aids as the primary fix.

## Scoring Guide

| Score | Description |
|-------|-------------|
| 10 | Correctly identifies timing/race root cause, suggests a proper fix, and avoids superficial sleep/timeout increases |
| 8-9 | Identifies timing issue and suggests proper fix; explanation is slightly imprecise |
| 6-7 | Identifies timing issue but fix is weak or incomplete; may mention sleep increase secondarily |
| 4-5 | Vaguely mentions timing but doesn't clearly identify it as the root cause; fix relies on increasing sleep |
| 2-3 | Only restates the problem; suggests increasing sleep or timeout as the main fix |
| 0-1 | Completely wrong diagnosis (blames missing deps, wrong test logic, etc.) or no meaningful analysis |

## Output
End your evaluation with: SCORE: N
