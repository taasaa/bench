# Judge Rubric: Environment Mismatch Diagnosis

## Task
The model receives a scenario where a tool works in one environment but fails in another due to a version manager, virtualenv, or configuration mismatch (e.g., Python venv shebang, nvm version, rbenv shell vs local, JAVA_HOME). It must identify the mismatch, explain the mechanism, and suggest a root-cause fix.

## Grading Criteria

1. **Mismatch identified** - Response correctly identifies the version or environment mismatch (e.g., Python 3.11 venv vs 3.12 alias, Node 18 vs 20, Ruby 3.1 vs 3.2, JDK 17 vs 21).
2. **Mechanism explained** - Response identifies the specific mechanism causing the mismatch (shebang resolution, nvm default, rbenv shell vs local, JAVA_HOME, PATH order, venv activation).
3. **Root-cause fix suggested** - Response provides a fix that addresses the root cause (fix shebang, activate venv, nvm use, set JAVA_HOME, rbenv shell) rather than a workaround.
4. **Avoids reinstalling** - Response does NOT suggest reinstalling the package as the fix (the package is already installed in the wrong environment).

## Scoring Guide

| Score | Description |
|-------|-------------|
| 10 | Identifies mismatch, explains mechanism, provides correct root-cause fix, avoids reinstall |
| 8-9 | Identifies mismatch and fix; mechanism explanation is slightly imprecise |
| 6-7 | Identifies mismatch but fix is vague or partially wrong; may suggest reinstall secondarily |
| 4-5 | Vaguely hints at version issue but doesn't clearly identify the mismatch or mechanism |
| 2-3 | Wrong diagnosis; suggests reinstalling the package as the main fix |
| 0-1 | Completely wrong analysis or no meaningful diagnosis |

## Output
End your evaluation with: SCORE: N
