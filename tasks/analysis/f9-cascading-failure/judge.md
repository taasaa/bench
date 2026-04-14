# Judge Rubric: Cascading Failure Analysis

## Task
The model receives a production incident scenario (e.g., connection pool exhaustion, file descriptor leak, unbounded cache growth, thread starvation). It must identify the correct root cause, propose a specific code or config fix, and avoid tempting but wrong answers (like "restart the service" or "add more resources").

## Grading Criteria

1. **Root cause identified** - Response correctly identifies the specific technical cause (pool too small, missing close(), unbounded cache, thread starvation) rather than a surface-level observation.
2. **Specific fix provided** - Response includes a concrete fix (e.g., increase pool_size, use context managers, add LRU eviction, use separate thread pools) with code or config changes.
3. **Avoids wrong answers** - Response does NOT suggest the tempting-but-wrong fix (e.g., restarting the database, increasing ulimit, adding RAM, increasing timeouts) as the solution.
4. **Does not claim service is down** - Response recognizes the service is degraded/starved, not crashed or offline.

## Scoring Guide

| Score | Description |
|-------|-------------|
| 10 | Correct root cause, specific fix, avoids all wrong answers, correctly characterizes as degradation not outage |
| 8-9 | Correct root cause and fix; minor gap in explanation or one weak suggestion alongside the correct fix |
| 6-7 | Identifies root cause but fix is vague; may also mention the wrong fix as an alternative |
| 4-5 | Vague on root cause; leans toward the tempting wrong answer (add resources, restart) |
| 2-3 | Wrong root cause; suggests restarting, adding resources, or increasing limits as the main fix |
| 0-1 | Completely wrong analysis or no meaningful diagnosis |

## Output
End your evaluation with: SCORE: N
