# F9 Cascading Failure Analysis — Judge Rubric

## Task
The model receives a production incident scenario (connection pool exhaustion, file descriptor leak, unbounded cache growth, thread starvation). It must identify the correct root cause, propose a specific code or config fix, and avoid tempting but wrong answers (like "restart the service" or "add more resources").

## Grading Dimensions

### Dimension 1: Root Cause
Did the response correctly identify the specific technical cause?
- Excellent: Correctly identifies pool too small, missing close(), unbounded cache, thread starvation
- Poor: Wrong root cause or only surface-level observation

### Dimension 2: Specific Fix
Did the response include a concrete fix with code or config changes?
- Excellent: Provides concrete fix (increase pool_size, context managers, LRU eviction, separate thread pools)
- Poor: No specific fix provided

### Dimension 3: Avoids Wrong Answers
Did the response avoid tempting-but-wrong fixes?
- Excellent: Does NOT suggest restarting the database, increasing ulimit, adding RAM, or increasing timeouts
- Poor: Suggests restarting or adding resources as the main solution

## Scoring Levels

| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Correct root cause, specific code/config fix, avoids all wrong answers, correctly characterizes as degradation not outage |
| 7.5 | Good | Correct root cause and specific fix; minor gap in explanation or one weak suggestion alongside the correct fix |
| 5 | Partial | Identifies root cause but fix is vague; or may also mention the wrong fix as an alternative alongside the right one |
| 2.5 | Poor | Vague on root cause; leans toward the tempting wrong answer (add resources, restart); fix relies on increasing resources |
| 0 | Failure | Wrong root cause entirely; suggests restarting or adding resources as the main fix; no meaningful diagnosis |

## Output
End your evaluation with: SCORE: N (where N is exactly 0, 2.5, 5, 7.5, or 10)
