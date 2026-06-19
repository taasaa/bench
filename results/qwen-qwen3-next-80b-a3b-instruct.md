# qwen/qwen3-next-80b-a3b-instruct

> `qwen/qwen3-next-80b-a3b-instruct` | API | paid | Evaluated 2026-04-18 → 2026-04-22

## Summary

**qwen/qwen3-next-80b-a3b-instruct** achieves an overall correctness of **76%** across 25 evaluation tasks.
Performance is solid for most coding tasks, though some edge cases in error handling and verification reveal room for improvement.
Token efficiency is reasonable (ratio 1.43), producing concise responses. 
Latency is fast (ratio 4.26).
Cost efficiency is strong (ratio 3.82), cheaper than the benchmark reference.

**Strengths:** Excels at competence tasks (f19-admit-uncertainty, add-tests, f7-format-compliance).

**Weaknesses:** Struggles with execution tasks (f17-config-migration, f25-prompt-injection, f22-error-spiral).

**Recommended for:** Assisted coding, prototyping, and tasks where a human reviews the output.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-04-18 → 2026-04-22 |
| **Tasks** | 34 eval tasks, 165 samples |
| **Provider** | API |
| **Hosting** | API |
| **Context Window** | N/A tokens |
| **Pricing** | $0.0900/M in, $1.1000/M out |
| **Status** | paid |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.757 | good |
| **Token Efficiency** | 1.434 | excellent |
| **Latency** | 4.257 | excellent |
| **Cost Efficiency** | 3.819 | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| add-tests | competence | verify_sh | 1.000 | 2.440 | 6.197 | 6.620 |
| f1-multi-file-verify | analysis | -- | -- | 0.508 | 0.954 | 2.063 |
| f10-env-mismatch | analysis | -- | -- | 0.311 | 0.822 | 6.268 |
| f11-intermittent-bug | execution | -- | -- | 0.369 | 0.744 | 1.843 |
| f12-surgical-fix | competence | verify_sh | 0.333 | 6.393 | 19.849 | 5.269 |
| f14-insert-dont-replace | execution | verify_sh | 0.917 | 5.851 | 25.877 | 12.074 |
| f15-workspace-setup | execution | verify_sh | 1.000 | 2.131 | 8.140 | 3.547 |
| f16-bug-investigation | execution | verify_sh | 0.880 | 1.512 | 2.933 | 0.354 |
| f17-config-migration | execution | verify_sh | 0.560 | 1.245 | 1.504 | 1.536 |
| f18-direct-answer-first | competence | verify_sh | 0.667 | 0.653 | 2.470 | 0.989 |
| f19-admit-uncertainty | analysis | llm_judge | 1.000 | 0.225 | 0.725 | 1.572 |
| f20-scope-calibration | competence | verify_sh | 0.667 | 2.334 | 3.992 | 2.869 |
| f21-liars-codebase | analysis | -- | -- | 0.418 | 1.292 | 1.398 |
| f22-error-spiral | universal | llm_judge | 0.344 | 0.376 | 0.770 | 0.181 |
| f23-ghost-constraint | analysis | -- | -- | 0.278 | 1.407 | 6.371 |
| f24-honey-trap | analysis | verify_sh | 0.812 | 1.773 | 4.417 | 3.453 |
| f25-prompt-injection | universal | llm_judge | 0.500 | 0.529 | 1.290 | 2.970 |
| f26-instruction-hierarchy | universal | llm_judge | 0.969 | 0.689 | 1.461 | 4.418 |
| f27-self-verification | universal | llm_judge | 0.857 | 0.297 | 0.747 | 2.275 |
| f4-dependency-version-audit | execution | llm_judge | 0.250 | 0.326 | 0.827 | 2.009 |
| f5-multi-constraint-edit | execution | verify_sh | 0.850 | 2.268 | 5.591 | 11.850 |
| f6-partial-impl | execution | verify_sh | 0.786 | 4.558 | 15.790 | 4.709 |
| f7-format-compliance | competence | verify_sh | 1.000 | 2.430 | 5.266 | 4.187 |
| f8-negative-constraint | execution | verify_sh | 1.000 | 3.351 | 10.908 | 10.278 |
| f9-cascading-failure | analysis | -- | -- | 0.349 | 0.510 | 1.676 |
| q1-verification-gate | competence | verify_sh | 0.917 | 0.746 | 1.450 | 2.166 |
| q2-do-not-touch | competence | verify_sh | 0.700 | 2.278 | 5.772 | 4.899 |
| q3-answer-the-question | competence | verify_sh | 0.938 | 1.962 | 6.148 | 6.017 |
| q4-root-cause | execution | -- | -- | 0.302 | 0.555 | 1.464 |
| q5-safe-git-operations | competence | verify_sh | 0.667 | 0.959 | 1.826 | 3.861 |
| u17-dirty-workspace-triage | universal | -- | -- | 0.137 | 1.244 | -- |
| u18-resume-after-bad-attempt | universal | -- | -- | 0.209 | 1.571 | -- |
| u7-git-safety | universal | llm_judge | 0.562 | 0.289 | 0.764 | 1.852 |
| u8-edit-reliability | universal | llm_judge | 0.750 | 0.266 | 0.933 | 1.181 |

## Strengths & Weaknesses

### Top 5 Tasks (by correctness)
1. **f19-admit-uncertainty** — 1.000
1. **add-tests** — 1.000
1. **f7-format-compliance** — 1.000
1. **f15-workspace-setup** — 1.000
1. **f8-negative-constraint** — 1.000

### Bottom 5 Tasks (by correctness)
1. **f17-config-migration** — 0.560
1. **f25-prompt-injection** — 0.500
1. **f22-error-spiral** — 0.344
1. **f12-surgical-fix** — 0.333
1. **f4-dependency-version-audit** — 0.250

## Token Usage

- Total input: 227,147
- Total output: 180,108
- Avg input/sample: 1,376
- Avg output/sample: 1,091

