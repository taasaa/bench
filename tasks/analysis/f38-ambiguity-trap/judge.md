# F38 Ambiguity Trap — Judge Rubric
## Task
User asks to update app logic to allow multiple bindings. A smart agent realizes the underlying database still has a UNIQUE constraint and writes a SQL migration to drop it.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Drops the UNIQUE index in SQL. |
| 0 | Failure | Only modifies the Python code. |
## Output
End your evaluation with: SCORE: N
