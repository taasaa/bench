# F10 Environment Mismatch — Judge Rubric

## Task
The model receives a scenario where a tool works in one environment but fails in another due to a version manager, virtualenv, or configuration mismatch (Python venv shebang, nvm version, rbenv shell vs local, JAVA_HOME). It must identify the mismatch, explain the mechanism, and suggest a root-cause fix.

## Grading Dimensions

### Dimension 1: Mismatch Identified
Did the response correctly identify the version or environment mismatch?
- Excellent: Correctly identifies Python 3.11 venv vs 3.12 alias, Node 18 vs 20, Ruby 3.1 vs 3.2, JDK 17 vs 21
- Poor: Completely wrong mismatch or no identification

### Dimension 2: Mechanism Explained
Did the response identify the specific mechanism causing the mismatch?
- Excellent: Identifies shebang resolution, nvm default, rbenv shell vs local, JAVA_HOME, PATH order, venv activation
- Poor: No mechanism explanation

### Dimension 3: Root-Cause Fix
Did the response provide a fix that addresses the root cause rather than a workaround?
- Excellent: Fix shebang, activate venv, nvm use, set JAVA_HOME, rbenv shell
- Poor: Suggests reinstalling the package as the main fix

## Scoring Levels

| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | Identifies mismatch correctly, explains the specific mechanism, provides correct root-cause fix, does NOT suggest reinstalling |
| 7.5 | Good | Identifies mismatch and provides correct fix; mechanism explanation is slightly imprecise |
| 5 | Partial | Identifies mismatch but fix is vague or partially wrong; may suggest reinstall secondarily; mechanism is hinted but not clearly stated |
| 2.5 | Poor | Vaguely hints at version issue but doesn't clearly identify the mismatch or mechanism; fix relies on reinstalling |
| 0 | Failure | Completely wrong analysis; suggests reinstalling the package as the main fix; no meaningful diagnosis |

## Output
End your evaluation with: SCORE: N (where N is exactly 0, 2.5, 5, 7.5, or 10)
