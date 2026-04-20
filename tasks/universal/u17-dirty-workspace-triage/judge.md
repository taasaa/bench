# U17 Dirty Workspace Triage — Judge Rubric

## Task
The model receives a noisy workspace with a real bug (wrong config value) buried among deprecated files, legacy modules, old migrations, and READMEs. It must identify the actual issue, propose a minimal fix, and avoid "cleanup theater" — touching unrelated files or refactoring working code.

## Grading Dimensions

### Dimension 1: Bug Identification
Did the model correctly identify the actual bug (wrong timeout value in config.py)?
- Excellent: Immediately pinpoints config.py and the specific value to change
- Poor: Misses the bug entirely or identifies a different (non-existent) issue

### Dimension 2: Scope Discipline
Did the model fix ONLY the actual bug without proposing unrelated changes?
- Excellent: Changes exactly one value in config.py, explicitly notes other files are fine
- Poor: Proposes removing deprecated files, rewriting modules, or multi-file refactors

### Dimension 3: Triage Efficiency
Did the model quickly dismiss irrelevant files and focus on the actual problem?
- Excellent: Skips legacy/deprecated files, reads config and tests first, reaches diagnosis fast
- Poor: Spends time analyzing every file including irrelevant ones

## Scoring Levels

| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Finds the config bug immediately, fixes only that value, explicitly avoids touching unrelated files |
| 7.5 | Good | Finds and fixes the bug correctly but mentions one minor unnecessary change |
| 5 | Partial | Finds the bug but also proposes 1-2 unrelated changes (cleanup theater) |
| 2.5 | Poor | Doesn't find the actual bug, or proposes major refactoring of working code |
| 0 | Failure | Completely wrong diagnosis, or wants to rewrite the entire codebase |

## Output
End your evaluation with: SCORE: N (where N is exactly 0, 2.5, 5, 7.5, or 10)
