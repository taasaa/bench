# F4 Dependency Version Audit — Judge Rubric

## Task
The model receives a `pyproject.toml` and a `package-lock.json` with planted inconsistencies. It must identify ALL discrepancies between the two files.

Types of inconsistencies planted:
- **Missing in lock file**: A dependency declared in pyproject.toml has no entry at all in package-lock.json
- **Version mismatch**: A dependency's locked version is below the minimum declared in pyproject.toml
- **Deprecated package**: A package that was deprecated and replaced by a successor (e.g., PyPDF2 → pypdf)

## Grading Dimensions

### Dimension 1: Issue Detection
Did the model identify the correct count of planted inconsistencies?
- Excellent: Found all planted issues, no extras
- Poor: Found nothing or everything was wrong

### Dimension 2: No False Positives
Did the model avoid flagging non-issues?
- Excellent: Zero false positives; only flagged actual inconsistencies
- Poor: All flagged issues were false positives

### Dimension 3: Root Cause Explanation
Did the model correctly explain WHY each issue is a problem?
- Excellent: Clear, precise explanation for every issue (e.g., "flask 2.15.0 is below the minimum 3.0.0")
- Poor: No explanation of root causes

## Scoring Levels

| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Found all planted issues with zero false positives, clear root-cause explanations for each |
| 7.5 | Good | Found all planted issues but also flagged 1 false positive; or found all with good but slightly imprecise explanations |
| 5 | Partial | Found most issues but missed 1; or found all but with 2+ false positives; explanations are vague for some |
| 2.5 | Poor | Found fewer than half of the issues; or more false positives than real issues; explanations are generic |
| 0 | Failure | Found nothing; or only false positives; no explanation of root causes |

## Important Notes
- Version ranges matter: `httpx>=0.25.0` is satisfied by `0.25.2` — NOT a mismatch.
- A package completely absent from the lock file is a serious issue.
- A locked version below the declared minimum is a version mismatch.

## Output
End your evaluation with: SCORE: N (where N is exactly 0, 2.5, 5, 7.5, or 10)
