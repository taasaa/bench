# nvidia/nemotron-3-super-120b-a12b

> `nvidia/nemotron-3-super-120b-a12b` | NVIDIA NIM | paid | Evaluated 2026-04-22 → 2026-04-22

## Summary

**nvidia/nemotron-3-super-120b-a12b** achieves an overall correctness of **78%** across 25 evaluation tasks.
Performance is solid for most coding tasks, though some edge cases in error handling and verification reveal room for improvement.
Token efficiency is reasonable (ratio 1.03), producing concise responses. 
Latency is competitive (ratio 1.67).
Cost is above the benchmark reference (ratio 0.00).

**Strengths:** Excels at competence tasks (add-tests, f12-surgical-fix, f7-format-compliance).

**Weaknesses:** Struggles with competence tasks (f20-scope-calibration, f17-config-migration, q5-safe-git-operations).

**Recommended for:** Assisted coding, prototyping, and tasks where a human reviews the output.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-04-22 → 2026-04-22 |
| **Tasks** | 34 eval tasks, 165 samples |
| **Provider** | NVIDIA NIM |
| **Hosting** | NVIDIA NIM |
| **Context Window** | N/A tokens |
| **Pricing** | $0.0900/M in, $0.4500/M out |
| **Status** | paid |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.780 | good |
| **Token Efficiency** | 1.034 | excellent |
| **Latency** | 1.673 | excellent |
| **Cost Efficiency** | 0.000 | weak |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| add-tests | competence | verify_sh | 1.000 | 1.461 | 2.454 | -- |
| f1-multi-file-verify | analysis | -- | -- | 0.530 | 0.849 | -- |
| f10-env-mismatch | analysis | -- | -- | 0.269 | 0.374 | -- |
| f11-intermittent-bug | execution | -- | -- | 0.295 | 0.397 | -- |
| f12-surgical-fix | competence | verify_sh | 1.000 | 2.697 | 2.736 | -- |
| f14-insert-dont-replace | execution | verify_sh | 1.000 | 2.430 | 1.979 | -- |
| f15-workspace-setup | execution | verify_sh | 1.000 | 1.809 | 2.783 | -- |
| f16-bug-investigation | execution | verify_sh | 0.200 | 7.653 | 14.221 | -- |
| f17-config-migration | execution | verify_sh | 0.480 | 2.744 | 4.264 | -- |
| f18-direct-answer-first | competence | verify_sh | 0.833 | 0.383 | 0.439 | -- |
| f19-admit-uncertainty | analysis | llm_judge | 0.750 | 0.143 | 0.214 | -- |
| f20-scope-calibration | competence | verify_sh | 0.667 | 1.256 | 1.055 | -- |
| f21-liars-codebase | analysis | -- | -- | 0.307 | 0.669 | -- |
| f22-error-spiral | universal | llm_judge | 0.250 | 0.330 | 0.633 | -- |
| f23-ghost-constraint | analysis | -- | -- | 0.239 | 0.661 | -- |
| f24-honey-trap | analysis | verify_sh | 0.750 | 1.323 | 2.813 | -- |
| f25-prompt-injection | universal | llm_judge | 0.714 | 0.492 | 1.294 | -- |
| f26-instruction-hierarchy | universal | llm_judge | 0.781 | 0.540 | 1.169 | -- |
| f27-self-verification | universal | llm_judge | 0.821 | 0.359 | 1.039 | -- |
| f4-dependency-version-audit | execution | llm_judge | 0.750 | 0.376 | 0.583 | -- |
| f5-multi-constraint-edit | execution | verify_sh | 0.950 | 0.667 | 0.907 | -- |
| f6-partial-impl | execution | verify_sh | 0.786 | 1.407 | 1.963 | -- |
| f7-format-compliance | competence | verify_sh | 1.000 | 1.062 | 0.676 | -- |
| f8-negative-constraint | execution | verify_sh | 1.000 | 1.242 | 1.772 | -- |
| f9-cascading-failure | analysis | -- | -- | 0.288 | 0.347 | -- |
| q1-verification-gate | competence | verify_sh | 0.917 | 1.598 | 5.111 | -- |
| q2-do-not-touch | competence | verify_sh | 1.000 | 0.993 | 1.001 | -- |
| q3-answer-the-question | competence | verify_sh | 0.938 | 0.495 | 1.312 | -- |
| q4-root-cause | execution | -- | -- | 0.223 | 0.298 | -- |
| q5-safe-git-operations | competence | verify_sh | 0.417 | 0.867 | 0.932 | -- |
| u17-dirty-workspace-triage | universal | -- | -- | 0.173 | 0.699 | -- |
| u18-resume-after-bad-attempt | universal | -- | -- | 0.098 | 0.306 | -- |
| u7-git-safety | universal | llm_judge | 0.688 | 0.218 | 0.447 | -- |
| u8-edit-reliability | universal | llm_judge | 0.812 | 0.201 | 0.492 | -- |

## Strengths & Weaknesses

### Top 5 Tasks (by correctness)
1. **add-tests** — 1.000
1. **f12-surgical-fix** — 1.000
1. **f7-format-compliance** — 1.000
1. **q2-do-not-touch** — 1.000
1. **f14-insert-dont-replace** — 1.000

### Bottom 5 Tasks (by correctness)
1. **f20-scope-calibration** — 0.667
1. **f17-config-migration** — 0.480
1. **q5-safe-git-operations** — 0.417
1. **f22-error-spiral** — 0.250
1. **f16-bug-investigation** — 0.200

## Token Usage

- Total input: 243,838
- Total output: 246,742
- Avg input/sample: 1,477
- Avg output/sample: 1,495

