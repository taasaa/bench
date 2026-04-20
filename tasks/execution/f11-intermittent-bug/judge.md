# F11 Intermittent Test Failure — Judge Rubric

## Task
The model receives a scenario where tests pass locally but fail intermittently in CI. It must identify the root cause as timing/race-condition related and suggest a proper fix (not just "add more sleep").

## Grading Dimensions

### Dimension 1: Root Cause
Did the response identify the issue as timing-dependent, a race condition, or non-deterministic ordering?
- Excellent: Correctly identifies timing/race condition as the root cause (not logic bug or missing dependency)
- Poor: Wrong diagnosis (blames missing deps, wrong test logic, etc.)

### Dimension 2: Proper Fix
Did the response recommend a real fix such as polling, waiting for a condition, mocking/freezing time, using events, or subprocess.wait?
- Excellent: Recommends a proper synchronization mechanism or mocking approach
- Poor: Only recommends increasing sleep or timeout

### Dimension 3: Avoids Superficial Fixes
Did the response NOT recommend increasing sleep/timeout as the primary fix?
- Excellent: Does NOT suggest "increase sleep", "add more sleep", or "use a longer timeout"
- Poor: Primary fix relies on increasing sleep duration

## Scoring Levels

| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Identifies timing/race root cause, suggests proper synchronization fix, avoids superficial sleep/timeout increases |
| 7.5 | Good | Identifies timing issue and suggests proper fix; explanation is slightly imprecise but fundamentally correct |
| 5 | Partial | Identifies timing issue but fix is weak or incomplete; may mention sleep increase secondarily |
| 2.5 | Poor | Vaguely mentions timing but doesn't clearly identify it as the root cause; fix relies on increasing sleep |
| 0 | Failure | Wrong diagnosis (blames missing deps, wrong test logic); or suggests only increasing sleep/timeout as the main fix |

## Output
End your evaluation with: SCORE: N (where N is exactly 0, 2.5, 5, 7.5, or 10)
