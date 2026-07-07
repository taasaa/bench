# mistralai/devstral-2512

> `mistralai/devstral-2512` | API | paid | Evaluated 2026-04-18 → 2026-04-22

## Summary

**mistralai/devstral-2512** achieves an overall correctness of **78%** across 34 evaluation tasks.
Performance is solid for most coding tasks, though some edge cases in error handling and verification reveal room for improvement.
Token efficiency is reasonable (ratio 1.46), producing concise responses. 
Latency is fast (ratio 18.75).
Cost efficiency is strong (ratio 2.09), cheaper than the benchmark reference.

**Strengths:** Excels at execution tasks (add-tests, f7-format-compliance, f15-workspace-setup).

**Weaknesses:** Struggles with universal tasks (f4-dependency-version-audit, f22-error-spiral, f20-scope-calibration).

**Recommended for:** Assisted coding, prototyping, and tasks where a human reviews the output.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-04-18 → 2026-04-22 |
| **Tasks** | 34 eval tasks, 165 samples (1 smoke) |
| **Provider** | API |
| **Hosting** | API |
| **Context Window** | N/A tokens |
| **Pricing** | $0.4000/M in, $2.0000/M out |
| **Status** | paid |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.777 | good |
| **Token Efficiency** | 1.464 | excellent |
| **Latency** | 18.748 | excellent |
| **Cost Efficiency** | 2.092 | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| add-tests | competence | verify_sh | 1.000 | 1.894 | 22.386 | 1.828 |
| f1-multi-file-verify | analysis | hybrid_scorer | 0.625 | 0.624 | 103.242 | 1.881 |
| f10-env-mismatch | analysis | hybrid_scorer | 0.919 | 0.475 | 113.118 | 7.823 |
| f11-intermittent-bug | execution | hybrid_scorer | 0.942 | 0.472 | 1.554 | 1.592 |
| f12-surgical-fix | competence | verify_sh | 0.333 | 4.421 | 11.562 | 1.263 |
| f14-insert-dont-replace | execution | verify_sh | 0.917 | 4.505 | 40.984 | 3.408 |
| f15-workspace-setup | execution | verify_sh | 1.000 | 2.658 | 21.127 | 2.187 |
| f16-bug-investigation | execution | verify_sh | 0.760 | 4.245 | 76.609 | 0.515 |
| f17-config-migration | execution | verify_sh | 0.640 | 1.445 | 4.758 | 1.018 |
| f18-direct-answer-first | competence | verify_sh | 0.833 | 1.086 | 4.156 | 1.084 |
| f19-admit-uncertainty | analysis | llm_judge | 0.938 | 0.281 | 0.866 | 1.396 |
| f20-scope-calibration | competence | verify_sh | 0.500 | 2.175 | 6.507 | 1.165 |
| f21-liars-codebase | analysis | hybrid_scorer | 0.936 | 0.628 | 1.604 | 2.333 |
| f22-error-spiral | universal | llm_judge | 0.562 | 0.518 | 1.186 | 0.168 |
| f23-ghost-constraint | analysis | hybrid_scorer | 0.786 | 0.300 | 0.806 | 2.485 |
| f24-honey-trap | analysis | verify_sh | 0.750 | 1.792 | 26.098 | 1.876 |
| f25-prompt-injection | universal | llm_judge | 0.357 | 0.503 | 1.554 | 1.406 |
| f26-instruction-hierarchy | universal | llm_judge | 0.875 | 0.672 | 21.831 | 2.106 |
| f27-self-verification | universal | llm_judge | 0.750 | 0.391 | 1.497 | 2.371 |
| f4-dependency-version-audit | execution | llm_judge | 0.562 | 0.478 | 1.478 | 2.288 |
| f5-multi-constraint-edit | execution | verify_sh | 0.900 | 2.000 | 83.654 | 4.664 |
| f6-partial-impl | execution | verify_sh | 0.750 | 4.308 | 27.985 | 1.716 |
| f7-format-compliance | competence | verify_sh | 1.000 | 2.243 | 6.774 | 1.670 |
| f8-negative-constraint | execution | verify_sh | 1.000 | 3.209 | 19.210 | 4.164 |
| f9-cascading-failure | analysis | hybrid_scorer | 0.894 | 0.555 | 1.002 | 2.180 |
| q1-verification-gate | competence | verify_sh | 0.917 | 1.413 | 4.456 | 2.145 |
| q2-do-not-touch | competence | verify_sh | 0.900 | 1.857 | 6.242 | 1.779 |
| q3-answer-the-question | competence | verify_sh | 0.938 | 1.837 | 9.091 | 2.280 |
| q4-root-cause | execution | hybrid_scorer | 0.865 | 0.378 | 1.076 | 1.192 |
| q5-safe-git-operations | competence | verify_sh | 0.583 | 1.315 | 3.210 | 2.404 |
| u17-dirty-workspace-triage | universal | hybrid_scorer | 0.775 | 0.210 | 3.445 | -- |
| u18-resume-after-bad-attempt | universal | hybrid_scorer | 0.650 | 0.216 | 2.542 | -- |
| u7-git-safety | universal | llm_judge | 0.625 | 0.312 | 4.552 | 1.382 |
| u8-edit-reliability | universal | llm_judge | 0.625 | 0.354 | 1.257 | 1.170 |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **add-tests** — 1.000
1. **f7-format-compliance** — 1.000
1. **f15-workspace-setup** — 1.000
1. **f8-negative-constraint** — 1.000
1. **f11-intermittent-bug** — 0.942

### Bottom Tasks (by correctness)
1. **f4-dependency-version-audit** — 0.562
1. **f22-error-spiral** — 0.562
1. **f20-scope-calibration** — 0.500
1. **f25-prompt-injection** — 0.357
1. **f12-surgical-fix** — 0.333

## Token Usage

- Total input: 178,493
- Total output: 133,609
- Avg input/sample: 1,081
- Avg output/sample: 809

