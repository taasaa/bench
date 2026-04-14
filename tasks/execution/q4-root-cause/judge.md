# Judge Rubric: Root Cause Diagnosis

## Task
The model receives a scenario where a tool works in one context but fails in another (e.g., `pip install` succeeds but `python3 import` fails). It must diagnose the root cause and suggest a specific fix.

## Grading Criteria

1. **Root cause identified** - Response explains that the two commands/tools point to different environments, installations, versions, or PATH configurations (not just restating the symptom).
2. **Specific fix provided** - Response includes a concrete actionable fix (e.g., `python3 -m pip`, creating a venv, using Docker service names, setting PATH in crontab) rather than vague advice.
3. **Avoids symptom-only fixes** - Response does NOT suggest superficial workarounds like reinstalling, using `--force`, or `sudo` as the primary solution.

## Scoring Guide

| Score | Description |
|-------|-------------|
| 10 | Identifies root cause clearly, provides a correct specific fix, and avoids all symptom-only approaches |
| 8-9 | Identifies root cause and provides a fix; minor imprecision in explanation or fix |
| 6-7 | Identifies root cause but fix is vague or partially wrong; may mention symptom fixes secondarily |
| 4-5 | Vague on root cause (hints at it but doesn't state it clearly) or suggests a symptom fix first |
| 2-3 | Only restates the problem or suggests only symptom fixes (reinstall, sudo, force) |
| 0-1 | Completely wrong diagnosis or no meaningful analysis |

## Output
End your evaluation with: SCORE: N
