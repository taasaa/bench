# Judge Rubric Template — Discrete 5-Point Scale

Use this template when writing judge.md rubrics for bench tasks. All rubrics must
use the discrete 5-point scale. The judge outputs `SCORE: N` where N is one of
{0, 2.5, 5, 7.5, 10}. The bench scorer normalizes to {0.0, 0.25, 0.5, 0.75, 1.0}.

## Required Format

```markdown
# [Task Name] — Judge Rubric

## Task
[1-3 sentences describing what the model was asked to do and what makes it challenging.]

## Grading Dimensions

### Dimension 1: [Name] (weight)
[Description of what this dimension measures.]

### Dimension 2: [Name] (weight)
[Description of what this dimension measures.]

[Add more dimensions as needed.]

## Scoring Levels

| Score | Label | Description |
|-------|-------|-------------|
| 10 | Excellent | [Specific, observable criteria for a perfect response] |
| 7.5 | Good | [Specific criteria for a solid but imperfect response] |
| 5 | Partial | [Specific criteria for a response that addresses some but not all requirements] |
| 2.5 | Poor | [Specific criteria for a response that barely addresses the task] |
| 0 | Failure | [Specific criteria for complete failure — wrong, empty, or harmful] |

## Instructions
Evaluate the model's response against each dimension. Determine the score level that
best matches the response quality. End with:

SCORE: N

Where N is exactly one of: 0, 2.5, 5, 7.5, or 10.
```

## Rules

1. Every level description must be specific and observable — not "adequate" or "reasonable"
2. Score boundaries must be unambiguous — a response clearly fits ONE level, not two
3. The 0 level must describe complete failure, not just "below average"
4. Weighted dimensions are optional — use flat scoring if dimensions don't need weighting
5. Never use intermediate values — only {0, 2.5, 5, 7.5, 10}
6. The final SCORE line must use the exact format `SCORE: N` with N from the set above
