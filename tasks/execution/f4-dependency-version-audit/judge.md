# F4 Dependency Version Audit — LLM Judge Rubric

## Task
The model receives a `pyproject.toml` and a `package-lock.json` with planted inconsistencies. It must identify ALL discrepancies between the two files.

Types of inconsistencies planted:
- **Missing in lock file**: A dependency declared in pyproject.toml has no entry at all in package-lock.json
- **Version mismatch**: A dependency's locked version is below the minimum declared in pyproject.toml
- **Deprecated package**: A package that was deprecated and replaced by a successor (e.g., PyPDF2 → pypdf)

## What Good Behavior Looks Like

A model that handles this well:
1. **Identifies the correct number of issues** — counts all planted inconsistencies
2. **Avoids false positives** — does NOT flag issues that don't exist (e.g., claiming httpx 0.25.2 satisfies httpx>=0.25.0 is correct, not a mismatch)
3. **Explains root cause** — for each issue, states clearly what is wrong and why (e.g., "flask 2.15.0 is below the minimum 3.0.0")
4. **Distinguishes version satisfaction from mismatch** — recognizes that httpx 0.25.2 satisfies httpx>=0.25.0

## Dimensions to Grade

### Dimension 1: Issue Detection (0-10)
Did the model identify the correct count of planted inconsistencies?

- 10: Found all planted issues, no extras
- 8: Found all planted issues but also flagged 1 false positive
- 6: Found most but missed 1 real issue
- 4: Found fewer than half of the issues
- 2: Found only 1 issue or only false positives
- 0: Found nothing or everything was wrong

### Dimension 2: No False Positives (0-10)
Did the model avoid flagging non-issues?

- 10: Zero false positives; only flagged actual inconsistencies
- 8: 1 minor false positive (e.g., misread a version range)
- 6: 2 false positives
- 4: More false positives than real issues
- 2: Mostly false positives
- 0: All flagged issues were false positives

### Dimension 3: Root Cause Explanation (0-10)
Did the model correctly explain WHY each issue is a problem?

- 10: Clear, precise explanation for every issue (e.g., "flask 2.15.0 is below the minimum 3.0.0 declared in pyproject.toml")
- 8: Good explanations with minor imprecision
- 6: Explanations present but vague for some issues
- 4: Explanations are generic ("there's a mismatch") without specifics
- 2: Barely any explanation
- 0: No explanation of root causes

## Final Score

Calculate the geometric mean of all 3 dimensions:
```
final_score = (issue_detection × no_false_positives × root_cause) ** (1/3)
```

Or if any dimension is 0: final score is 0.

Report the geometric mean as your SCORE: N. A score of 8+ indicates thorough and accurate dependency auditing. A score below 5 indicates the model missed significant issues or produced many false positives.

## Important Notes

- Version ranges matter: `httpx>=0.25.0` is satisfied by `0.25.2` — this is NOT a mismatch.
- A package completely absent from the lock file is a missing dependency, which is a serious issue.
- A locked version below the declared minimum (e.g., `>=3.0.0` but locked at `2.15.0`) is a version mismatch.
- Be fair about deprecated package scenarios — credit the model if it correctly identifies the deprecation direction.
