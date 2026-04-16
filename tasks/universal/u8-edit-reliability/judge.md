# U8 Edit Reliability — LLM Judge Rubric

## Task
Evaluate whether the model demonstrates awareness of edit tool reliability edge cases and uses appropriate fallback strategies.

Evidence: 5.6% of 3,864 agent bugs are edit tool failures. "String to replace not found" is the #1 reported Claude Code failure. No benchmark tests this — all assume edits succeed.

## What Good Behavior Looks Like
1. **Diagnoses edit failures correctly** — identifies stale read, CRLF mismatch, or whitespace issue
2. **Uses robust alternatives** — switches to Write tool, sed, or other approach when Edit fails
3. **Verifies before and after** — reads file before edit, confirms success after
4. **Does NOT blame the tool** — understands that edit tools have known failure modes
5. **Reports clearly** — when edit fails or requires fallback, reports what happened and what was done

## What Bad Behavior Looks Like
1. **Retries Edit indefinitely** — keeps trying the same approach without success
2. **Blames the tool** — says "the edit tool is broken" instead of diagnosing the issue
3. **Ignores failure** — pretends the edit succeeded when it didn't
4. **Doesn't read before editing** — assumes file content without re-reading (stale read)
5. **Assumes edit always works** — never considers that Edit might fail or that alternatives exist

## Dimensions to Grade

### Dimension 1: Failure Diagnosis (0-10)
Did the model correctly identify the root cause of the edit failure?
- 10: Correctly diagnosed the specific issue (stale read, CRLF, whitespace)
- 7: Identified that something was wrong but missed the specific root cause
- 4: Attempted diagnosis but was wrong about what failed
- 0: Didn't diagnose — blamed the tool or assumed corruption

### Dimension 2: Appropriate Fallback (0-10)
Did the model switch to an appropriate alternative when Edit failed?
- 10: Used a robust alternative (Write tool, sed, or full rewrite) that works reliably
- 7: Used an alternative but it was more complex than necessary
- 4: Attempted fallback but it was incomplete or incorrect
- 0: No fallback — kept retrying or gave up

### Dimension 3: Verification Behavior (0-10)
Did the model verify file content before and after editing?
- 10: Read file before editing AND confirmed edit succeeded after
- 7: Read before editing OR confirmed after, but not both
- 4: Minimal verification — only checked one thing
- 0: No verification — assumed edit worked

### Dimension 4: Clear Reporting (0-10)
When edit failed or required fallback, did the model report clearly?
- 10: Explicitly stated what failed, what caused it, and what alternative was used
- 7: Mentioned the issue but was vague about cause or solution
- 4: Reported success but failed or reported failure but gave no solution
- 0: No reporting — model either pretended everything was fine or stayed silent

## Final Score

Geometric mean of all 4 dimensions:
```
final_score = (failure_diagnosis × appropriate_fallback × verification_behavior × clear_reporting) ** 0.25
```

If any dimension is 0: final score is 0.

A score of 8+ means the model handles edit tool reliability as a known edge case. A score below 5 means the model will hit the "string not found" failure repeatedly and not recover gracefully.

## Key Diagnostic

If Dimension 1 (Failure Diagnosis) is below 5: the model doesn't understand that edit tools have known failure modes. It will blame the tool or assume corruption instead of diagnosing the actual issue.

If Dimension 2 (Appropriate Fallback) is below 5: the model will keep retrying the same failing approach instead of switching to alternatives. This is the primary cause of wasted time in agent workflows.