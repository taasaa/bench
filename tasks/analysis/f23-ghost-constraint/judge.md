# Judge Rubric: Ghost Constraint Compliance

## Task
The model receives upfront constraints (snake_case naming, type hints, use httpx) and must write multiple functions that consistently follow ALL constraints across several turns. The "ghost" aspect is that constraints are easy to forget as the task progresses.

## Grading Criteria

1. **All functions present** - Response defines at least 3 functions (one per turn), each implementing the requested behavior.
2. **Snake_case naming** - All function and variable names use snake_case consistently. No camelCase or PascalCase identifiers anywhere in the code.
3. **Type hints included** - Every function definition includes type hints for parameters and return types (e.g., `def fetch_user(user_id: int) -> dict:`).
4. **Uses httpx** - Code imports and uses the `httpx` library for HTTP requests. Does NOT use the `requests` library.

## Scoring Guide

| Score | Description |
|-------|-------------|
| 10 | All 3+ functions present, fully correct snake_case, complete type hints, uses httpx exclusively |
| 8-9 | All functions present; one minor constraint slip (e.g., one function missing return type hint) |
| 6-7 | Most functions present; one constraint violated (e.g., one camelCase name, or one function without hints) |
| 4-5 | Functions present but multiple constraint violations (e.g., uses requests instead of httpx, or half the functions lack type hints) |
| 2-3 | Only one function present, or uses requests library, or no type hints at all |
| 0-1 | No code produced, or completely ignores all constraints |

## Output
End your evaluation with: SCORE: N
