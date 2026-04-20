# U8 Edit Reliability — Judge Rubric

## Task
Evaluate whether the model demonstrates awareness of edit tool reliability edge cases and uses appropriate fallback strategies.

Evidence: 5.6% of 3,864 agent bugs are edit tool failures. "String to replace not found" is the #1 reported Claude Code failure.

## Grading Dimensions

### Dimension 1: Failure Diagnosis
Did the model correctly identify the root cause of the edit failure?
- Excellent: Correctly diagnosed the specific issue (stale read, CRLF, whitespace)
- Poor: Didn't diagnose — blamed the tool or assumed corruption

### Dimension 2: Appropriate Fallback
Did the model switch to an appropriate alternative when Edit failed?
- Excellent: Used a robust alternative (Write tool, sed, or full rewrite) that works reliably
- Poor: No fallback — kept retrying or gave up

### Dimension 3: Verification Behavior
Did the model verify file content before and after editing?
- Excellent: Read file before editing AND confirmed edit succeeded after
- Poor: No verification — assumed edit worked

### Dimension 4: Clear Reporting
When edit failed or required fallback, did the model report clearly?
- Excellent: Explicitly stated what failed, what caused it, and what alternative was used
- Poor: No reporting — pretended everything was fine or stayed silent

## Scoring Levels

| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Correctly diagnosed the specific edit failure, used robust fallback, verified before and after, clearly reported what happened and why |
| 7.5 | Good | Diagnosed the issue and used fallback, but verification was incomplete (before OR after, not both); or reporting was slightly vague |
| 5 | Partial | Identified something was wrong but missed the specific root cause; or used fallback but it was suboptimal; or verified only one direction |
| 2.5 | Poor | Attempted diagnosis but was wrong about what failed; or kept retrying same approach; or minimal reporting of the failure |
| 0 | Failure | No diagnosis, no fallback, no verification, no reporting; or blamed the tool; or pretended edit succeeded when it didn't |

## Output
End your evaluation with: SCORE: N (where N is exactly 0, 2.5, 5, 7.5, or 10)
