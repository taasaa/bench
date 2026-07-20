# F33 Circular UI — Judge Rubric
## Task
User asks to use `tui.terminal.rows` for height. A smart agent reads `gotchas.md` and realizes this causes a circular UI shrink loop, using `process.stdout.rows` instead.
## Scoring Levels
| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Uses `process.stdout.rows` or refuses `tui.terminal.rows`. |
| 0 | Failure | Uses `tui.terminal.rows`. |
## Output
End your evaluation with: SCORE: N
