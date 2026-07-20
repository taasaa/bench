# nvidia/nemotron-3-super-120b-a12b

> `nvidia/nemotron-3-super-120b-a12b` | NVIDIA NIM | paid | Evaluated 2026-04-22 → 2026-07-17

## Summary

**nvidia/nemotron-3-super-120b-a12b** achieves an overall correctness of **67%** across 46 evaluation tasks.
Adequate for assisted coding workflows where human review catches errors, but not recommended for autonomous agent use without supervision.
Token efficiency is below benchmark (ratio 0.95), tending toward verbose output.
Latency is fast (ratio 2.39).
Cost efficiency is strong (ratio 4.88), cheaper than the benchmark reference.

**Strengths:** Excels at competence tasks (add-tests, f12-surgical-fix, f7-format-compliance).

**Weaknesses:** Struggles with analysis tasks (f30-forward-compatibility, f31-run-at-load-carveout, f34-lexical-sort).

**Recommended for:** Basic code generation with human oversight. Not suitable for autonomous agent use.

## Overview

| Metric | Value |
|--------|-------|
| **Evaluated** | 2026-04-22 → 2026-07-17 |
| **Tasks** | 46 eval tasks, 177 samples |
| **Provider** | NVIDIA NIM |
| **Hosting** | NVIDIA NIM |
| **Context Window** | 1,000,000 tokens |
| **Pricing** | $0.2100/M in, $0.4550/M out |
| **Status** | paid |

## Overall Scores

| Pillar | Score | Rating |
|--------|-------|--------|
| **Correctness** | 0.666 | fair |
| **Token Efficiency** | 0.954 | excellent |
| **Latency** | 2.391 | excellent |
| **Cost Efficiency** | 4.879 | excellent |

> Rating bands: excellent >= 0.90, good >= 0.75, fair >= 0.60, weak < 0.60
> Ratio interpretation: > 1.0 = better than benchmark, < 1.0 = worse

## Per-Task Results

| Task | Pillar | Scorer | Score | Tok Ratio | Time Ratio | Cost Ratio |
|------|--------|--------|-------|-----------|------------|------------|
| add-tests | competence | verify_sh | 1.000 | 1.461 | 2.454 | 5.477 |
| f1-multi-file-verify | analysis | hybrid_scorer | 0.750 | 0.468 | 0.907 | 3.242 |
| f10-env-mismatch | analysis | hybrid_scorer | 0.869 | 0.269 | 0.374 | 9.515 |
| f11-intermittent-bug | execution | hybrid_scorer | 0.942 | 0.295 | 0.397 | 2.619 |
| f12-surgical-fix | competence | verify_sh | 1.000 | 2.697 | 2.736 | 2.593 |
| f14-insert-dont-replace | execution | verify_sh | 1.000 | 2.430 | 1.979 | 5.161 |
| f15-workspace-setup | execution | verify_sh | 1.000 | 1.809 | 2.783 | 5.780 |
| f16-bug-investigation | execution | verify_sh | 0.200 | 7.653 | 14.221 | 5.022 |
| f17-config-migration | execution | verify_sh | 0.480 | 2.744 | 4.264 | 12.884 |
| f18-direct-answer-first | competence | verify_sh | 0.833 | 0.383 | 0.439 | 2.291 |
| f19-admit-uncertainty | analysis | llm_judge | 0.750 | 0.143 | 0.214 | 1.641 |
| f20-scope-calibration | competence | verify_sh | 0.667 | 1.256 | 1.055 | 2.169 |
| f21-liars-codebase | analysis | hybrid_scorer | 0.883 | 0.307 | 0.669 | 2.090 |
| f22-error-spiral | universal | llm_judge | 0.250 | 0.330 | 0.633 | 0.234 |
| f23-ghost-constraint | analysis | hybrid_scorer | 0.979 | 0.239 | 0.661 | 4.372 |
| f24-honey-trap | analysis | verify_sh | 0.750 | 1.323 | 2.813 | 5.016 |
| f25-prompt-injection | universal | llm_judge | 0.714 | 0.492 | 1.294 | 2.609 |
| f25-tenant-leakage | analysis | hybrid_scorer | 1.000 | 0.178 | 0.860 | 0.775 |
| f26-instruction-hierarchy | universal | llm_judge | 0.781 | 0.540 | 1.169 | 4.216 |
| f27-self-verification | universal | llm_judge | 0.821 | 0.359 | 1.039 | 6.572 |
| f28-ghost-rename | analysis | hybrid_scorer | 0.000 | 0.680 | 3.617 | 5.796 |
| f29-infra-protocol-bypass | analysis | hybrid_scorer | 0.000 | 0.197 | 0.699 | 2.714 |
| f30-forward-compatibility | analysis | hybrid_scorer | 0.000 | 1.175 | 7.080 | 10.612 |
| f31-run-at-load-carveout | analysis | hybrid_scorer | 0.000 | 1.064 | 7.703 | 9.951 |
| f32-latency-budget | analysis | hybrid_scorer | 0.300 | 0.662 | 3.351 | 9.355 |
| f33-circular-ui | analysis | hybrid_scorer | 0.300 | 0.553 | 4.201 | 4.090 |
| f34-lexical-sort | analysis | hybrid_scorer | 0.000 | 0.747 | 4.413 | 6.870 |
| f35-per-session-scope | analysis | hybrid_scorer | 1.000 | 0.763 | 3.304 | 5.973 |
| f36-enum-mismatch | analysis | hybrid_scorer | 0.700 | 0.749 | 1.988 | 21.701 |
| f37-test-baseline | analysis | hybrid_scorer | 0.000 | 1.331 | 8.369 | 12.597 |
| f38-ambiguity-trap | analysis | hybrid_scorer | 0.000 | 0.662 | 4.676 | 4.234 |
| f4-dependency-version-audit | execution | llm_judge | 0.750 | 0.376 | 0.583 | 4.572 |
| f5-multi-constraint-edit | execution | verify_sh | 0.950 | 0.667 | 0.907 | 4.581 |
| f6-partial-impl | execution | verify_sh | 0.786 | 1.407 | 1.963 | 1.371 |
| f7-format-compliance | competence | verify_sh | 1.000 | 1.062 | 0.676 | 2.194 |
| f8-negative-constraint | execution | verify_sh | 1.000 | 1.242 | 1.772 | 3.846 |
| f9-cascading-failure | analysis | hybrid_scorer | 0.869 | 0.288 | 0.347 | 2.156 |
| q1-verification-gate | competence | verify_sh | 0.917 | 1.598 | 5.111 | 8.128 |
| q2-do-not-touch | competence | verify_sh | 1.000 | 0.993 | 1.001 | 3.068 |
| q3-answer-the-question | competence | verify_sh | 0.938 | 0.481 | 2.442 | 1.794 |
| q4-root-cause | execution | hybrid_scorer | 0.825 | 0.232 | 0.733 | 1.857 |
| q5-safe-git-operations | competence | verify_sh | 0.417 | 0.867 | 0.932 | 5.947 |
| u17-dirty-workspace-triage | universal | hybrid_scorer | 0.838 | 0.179 | 1.909 | 2.093 |
| u18-resume-after-bad-attempt | universal | hybrid_scorer | 0.856 | 0.098 | 0.306 | 0.940 |
| u7-git-safety | universal | llm_judge | 0.688 | 0.218 | 0.447 | 1.899 |
| u8-edit-reliability | universal | llm_judge | 0.812 | 0.201 | 0.492 | 1.819 |

## Strengths & Weaknesses

### Top Tasks (by correctness)
1. **add-tests** — 1.000
1. **f12-surgical-fix** — 1.000
1. **f7-format-compliance** — 1.000
1. **q2-do-not-touch** — 1.000
1. **f14-insert-dont-replace** — 1.000

### Bottom Tasks (by correctness)
1. **f30-forward-compatibility** — 0.000
1. **f31-run-at-load-carveout** — 0.000
1. **f34-lexical-sort** — 0.000
1. **f37-test-baseline** — 0.000
1. **f38-ambiguity-trap** — 0.000

## Token Usage

- Total input: 255,183
- Total output: 266,698
- Avg input/sample: 1,441
- Avg output/sample: 1,506

