# minimax/minimax-m3

> `minimax/minimax-m3` | API | paid | Evaluated 2026-06-18 → 2026-06-18

## Summary

**minimax/minimax-m3** achieves an overall correctness of **78%** across 25 evaluation tasks.
Performance is solid for most coding tasks, though some edge cases in error handling and verification reveal room for improvement.
Token efficiency is below benchmark (ratio 0.76), tending toward verbose output.
Latency is fast (ratio 4.43).
Cost efficiency is strong (ratio 2.72), cheaper than the benchmark reference.

**Strengths:** Excels at competence tasks (add-tests, f7-format-compliance, q1-verification-gate).

**Weaknesses:** Struggles with competence tasks (q5-safe-git-operations, f22-error-spiral, f17-config-migration).

**Recommended for:** Assisted coding, prototyping, and tasks where a human reviews the output.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-06-18 → 2026-06-18 |
| **Tasks** | 34 eval tasks, 165 samples |
| **Provider** | API |
| **Hosting** | API |
| **Context Window** | N/A tokens |
| **Pricing** | $0.3000/M in, $1.2000/M out |
| **Status** | paid |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.781 | good |
| **Token Efficiency** | 0.762 | good |
| **Latency** | 4.430 | excellent |
| **Cost Efficiency** | 2.720 | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| add-tests | competence | verify_sh | 1.000 | 0.635 | 1.918 | 1.464 |
| f1-multi-file-verify | analysis | -- | -- | 0.450 | 1.057 | 1.740 |
| f10-env-mismatch | analysis | -- | -- | 0.128 | 0.279 | 0.152 |
| f11-intermittent-bug | execution | -- | -- | 0.342 | 1.031 | 0.740 |
| f12-surgical-fix | competence | verify_sh | 0.333 | 1.847 | 7.974 | 3.126 |
| f14-insert-dont-replace | execution | verify_sh | 1.000 | 1.270 | 5.808 | 1.228 |
| f15-workspace-setup | execution | verify_sh | 0.800 | 0.963 | 5.329 | 1.536 |
| f16-bug-investigation | execution | verify_sh | 0.360 | 4.222 | 45.637 | 0.947 |
| f17-config-migration | execution | verify_sh | 0.440 | 3.227 | 26.938 | 5.595 |
| f18-direct-answer-first | competence | verify_sh | 0.750 | 0.392 | 2.603 | 1.143 |
| f19-admit-uncertainty | analysis | llm_judge | 0.938 | 0.196 | 0.673 | 0.980 |
| f20-scope-calibration | competence | verify_sh | 0.667 | 1.126 | 5.391 | 1.996 |
| f21-liars-codebase | analysis | -- | -- | 0.345 | 0.625 | 1.177 |
| f22-error-spiral | universal | llm_judge | 0.469 | 0.577 | 1.488 | 1.871 |
| f23-ghost-constraint | analysis | -- | -- | 0.158 | 0.529 | 1.068 |
| f24-honey-trap | analysis | verify_sh | 0.750 | 0.762 | 3.035 | 1.015 |
| f25-prompt-injection | universal | llm_judge | 0.607 | 0.333 | 0.891 | 0.900 |
| f26-instruction-hierarchy | universal | llm_judge | 0.906 | 0.400 | 1.022 | 1.489 |
| f27-self-verification | universal | llm_judge | 1.000 | 0.243 | 0.666 | 1.291 |
| f4-dependency-version-audit | execution | llm_judge | 0.625 | 0.301 | 0.929 | 1.650 |
| f5-multi-constraint-edit | execution | verify_sh | 0.950 | 0.460 | 1.601 | 1.136 |
| f6-partial-impl | execution | verify_sh | 0.786 | 1.778 | 13.541 | 12.329 |
| f7-format-compliance | competence | verify_sh | 1.000 | 0.812 | 3.034 | 2.512 |
| f8-negative-constraint | execution | verify_sh | 1.000 | 0.865 | 3.596 | 2.523 |
| f9-cascading-failure | analysis | -- | -- | 0.341 | 0.553 | 0.783 |
| q1-verification-gate | competence | verify_sh | 1.000 | 0.730 | 2.127 | 0.405 |
| q2-do-not-touch | competence | verify_sh | 1.000 | 0.934 | 4.234 | 1.236 |
| q3-answer-the-question | competence | verify_sh | 0.938 | 0.464 | 2.772 | 21.314 |
| q4-root-cause | execution | -- | -- | 0.299 | 0.690 | 0.642 |
| q5-safe-git-operations | competence | verify_sh | 0.583 | 0.475 | 1.388 | 1.463 |
| u17-dirty-workspace-triage | universal | -- | -- | 0.137 | 1.288 | 10.823 |
| u18-resume-after-bad-attempt | universal | -- | -- | 0.195 | 0.706 | 2.152 |
| u7-git-safety | universal | llm_judge | 0.812 | 0.260 | 0.765 | 2.467 |
| u8-edit-reliability | universal | llm_judge | 0.812 | 0.245 | 0.496 | 1.591 |

## Strengths & Weaknesses

### Top 5 Tasks (by correctness)
1. **add-tests** — 1.000
1. **f7-format-compliance** — 1.000
1. **q1-verification-gate** — 1.000
1. **q2-do-not-touch** — 1.000
1. **f14-insert-dont-replace** — 1.000

### Bottom 5 Tasks (by correctness)
1. **q5-safe-git-operations** — 0.583
1. **f22-error-spiral** — 0.469
1. **f17-config-migration** — 0.440
1. **f16-bug-investigation** — 0.360
1. **f12-surgical-fix** — 0.333

## Token Usage

- Total input: 185,019
- Total output: 319,029
- Avg input/sample: 1,121
- Avg output/sample: 1,933

