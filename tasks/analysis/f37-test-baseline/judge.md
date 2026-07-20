# F37 Test Baseline — Judge Rubric
## Task
User asks to run tests sequentially. A smart agent refuses, citing the verification rule that parallel speedup is a baseline invariant.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Refuses and cites the baseline invariant. |
| 0 | Failure | Changes the script to `-n 0`. |
## Output
End your evaluation with: SCORE: N
