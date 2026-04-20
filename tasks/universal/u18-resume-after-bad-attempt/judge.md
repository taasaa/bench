# U18 Resume After Bad Attempt — Judge Rubric

## Task
The model receives a workspace with a buggy source file, a correct helper module, and ATTEMPT_NOTES.md documenting a prior developer's incomplete fix. The model must resume the fix correctly — reading the notes, understanding what was tried and why it failed, and producing a minimal correct fix that reuses the existing helper.

## Grading Dimensions

### Dimension 1: Prior Work Awareness
Did the model read and reference the ATTEMPT_NOTES.md to understand what was already tried?
- Excellent: Explicitly cites the notes, identifies the false leads, and builds on the correct insight
- Poor: Ignores the notes entirely and approaches from scratch

### Dimension 2: Minimal Fix Discipline
Did the model make only the necessary changes (import + comparison fix) without unnecessary refactoring?
- Excellent: Changes exactly what's needed — import line and one comparison expression
- Poor: Rewrites multiple methods, adds new classes, or refactors unrelated code

### Dimension 3: Dead-End Avoidance
Did the model avoid the false approaches documented in ATTEMPT_NOTES?
- Excellent: Explicitly rejects the false leads from the notes
- Poor: Repeats one of the documented wrong approaches

## Scoring Levels

| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Reads notes, identifies correct fix, uses existing helper, minimal changes, explicitly avoids documented false leads |
| 7.5 | Good | Uses correct approach with existing helper but adds minor unnecessary changes or doesn't reference the notes |
| 5 | Partial | Fixes the bug correctly but doesn't use the existing helper, or ignores prior work context entirely |
| 2.5 | Poor | Takes a wrong approach documented in the notes, or makes invasive unnecessary changes alongside the fix |
| 0 | Failure | Doesn't fix the bug, or rewrites the entire module, or introduces new bugs |

## Output
End your evaluation with: SCORE: N (where N is exactly 0, 2.5, 5, 7.5, or 10)
