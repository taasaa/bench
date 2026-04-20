# F23 Ghost Constraint — Judge Rubric

## Task
The model receives upfront constraints (snake_case naming, type hints, use httpx) and must write multiple functions that consistently follow ALL constraints across several turns. The "ghost" aspect is that constraints are easy to forget as the task progresses.

## Grading Dimensions

### Dimension 1: All Functions Present
Did the response define at least 3 functions, one per turn, each implementing the requested behavior?
- Excellent: All 3+ functions present
- Poor: No code produced or only one function

### Dimension 2: Constraint Consistency
Did the response follow ALL constraints (snake_case, type hints, httpx) across ALL functions?
- Excellent: All functions use correct snake_case, complete type hints, and httpx exclusively
- Poor: Multiple constraint violations (uses requests, no type hints, camelCase names)

### Dimension 3: No Constraint Drift
Did constraints hold up as the task progressed (later functions as consistent as earlier ones)?
- Excellent: Last function is as constraint-compliant as the first
- Poor: Constraints abandoned in later functions

## Scoring Levels

| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | All 3+ functions present, fully correct snake_case, complete type hints on every function, uses httpx exclusively |
| 7.5 | Good | All functions present; one minor constraint slip (e.g., one function missing return type hint, or one camelCase variable) |
| 5 | Partial | Most functions present; one constraint violated (e.g., one camelCase name, or one function without hints, or used requests in one place) |
| 2.5 | Poor | Only one function present; or uses requests library; or no type hints at all; or multiple constraint violations across functions |
| 0 | Failure | No code produced; or completely ignores all constraints; or all functions use wrong library and wrong naming |

## Output
End your evaluation with: SCORE: N (where N is exactly 0, 2.5, 5, 7.5, or 10)
