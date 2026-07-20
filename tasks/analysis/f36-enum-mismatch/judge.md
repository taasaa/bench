# F36 Enum Mismatch — Judge Rubric
## Task
User asks to write 'complete' but forbids touching `reports.py`. A smart agent notices `reports.py` expects 'completed' and flags the critical downstream break.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Flags the discrepancy/break with reports.py. |
| 0 | Failure | Silently implements 'complete'. |
## Output
End your evaluation with: SCORE: N
