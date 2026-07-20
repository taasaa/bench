# F32 Latency Budget — Judge Rubric
## Task
User asks to fetch full context pack bodies in a loop. A smart agent respects `decisions.md` (which warns against N+1 subprocesses) and uses `recall_body` metadata instead.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Uses `recall_body` and avoids `fetch_pack`. |
| 0 | Failure | Uses `fetch_pack` in a loop. |
## Output
End your evaluation with: SCORE: N
