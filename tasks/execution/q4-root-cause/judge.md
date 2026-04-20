# Q4 Root Cause Diagnosis — Judge Rubric

## Task
The model receives a scenario where a tool works in one context but fails in another (e.g., `pip install` succeeds but `python3 import` fails). It must diagnose the root cause and suggest a specific fix.

## Grading Dimensions

### Dimension 1: Root Cause Identified
Did the response explain that the two commands/tools point to different environments, installations, versions, or PATH configurations?
- Excellent: Clearly explains different environments or PATH configurations
- Poor: Only restates the symptom without explaining why

### Dimension 2: Specific Fix
Did the response include a concrete actionable fix?
- Excellent: `python3 -m pip`, creating a venv, using Docker service names, setting PATH in crontab
- Poor: Vague advice like "check your installation"

### Dimension 3: Avoids Symptom-Only Fixes
Did the response avoid suggesting superficial workarounds as the primary solution?
- Excellent: Does NOT suggest reinstalling, using `--force`, or `sudo` as the primary fix
- Poor: Suggests reinstalling, `--force`, or `sudo` as the main solution

## Scoring Levels

| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Identifies root cause clearly, provides a correct specific fix, avoids all symptom-only approaches |
| 7.5 | Good | Identifies root cause and provides a fix; minor imprecision in explanation or fix |
| 5 | Partial | Identifies root cause but fix is vague or partially wrong; may mention symptom fixes secondarily |
| 2.5 | Poor | Vague on root cause (hints at it but doesn't state it clearly); or suggests a symptom fix first |
| 0 | Failure | Completely wrong diagnosis or no meaningful analysis; only restates the problem |

## Output
End your evaluation with: SCORE: N (where N is exactly 0, 2.5, 5, 7.5, or 10)
