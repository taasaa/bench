# PRD: Discriminative Bench Evaluation — Decision-Support Architecture

**Status:** draft
**Project:** Bench
**Owner:** Michael Mazyar (Rut)
**Scope:** feature (new discriminative module, existing code may be refactored where it improves the system)
**Date:** 2026-04-22
**Tier:** deep

---

## Problem Statement

Bench evaluates 8 models across 36 tasks with 4-pillar scoring, but all models cluster at 74-79% correctness — a 5-point spread that hides dramatic qualitative differences. Models with near-identical aggregate scores (Nem-30b at 76%, GLM-5-T at 79%) are only r=0.615 correlated, meaning they solve tasks in fundamentally different ways despite appearing identical. The user cannot use current output ("Model X scored 77%") to decide which model, agent, or harness to deploy for a specific use case. The arithmetic mean is an information-destroying aggregation that allows strengths to cancel weaknesses, and 20% of tasks contribute literally zero discrimination signal (σ=0.000).

The fundamental problem is not that models are similar — the correlation matrix proves they're not. The problem is that Bench's output format (single aggregate score per model) cannot represent multi-dimensional differences, and its aggregation method (arithmetic mean across all tasks) treats zero-information tasks the same as high-discrimination ones.

---

## First Principles Analysis

### Deconstruction

Bench is a measurement instrument with three layers:

| Layer | Component | Current State | Problem |
|-------|-----------|---------------|---------|
| Stimulus | 36 tasks | 5 zero-discrimination (σ=0), 6 ceiling (p>0.90), 1 floor | 67% of measurement is noise or saturation |
| Transducer | Scorers (verify_sh, llm_judge, hybrid) | Binary (0/1) for verify_sh, continuous for llm_judge | Binary gives ±0.22 CI at n=5 |
| Aggregator | Arithmetic mean | Treats all tasks as equal information | Destroys distributional information |

The real evaluative signal already exists — r=0.615 proves models differ. The instrument just isn't extracting and presenting it.

### Constraint Classification

| Constraint | Type | Evidence | If Removed |
|-----------|------|----------|------------|
| Arithmetic mean destroys information | Hard | Mathematical fact | Must use different aggregation |
| Binary scoring gives wide CIs at n=5 | Hard | Binomial CI at p=0.5, n=5 = ±0.22 | Need more samples or continuous scoring |
| 8 models of historical data | Hard | Cannot retroactively add models | IRT and EFA infeasible at this N |
| 36 authored tasks | Hard | Cannot wish new tasks into existence | Can add/remove but not retroactively |
| 4-pillar scoring | Soft | Design choice | Only correctness has compression; other pillars are fine |
| "competence/execution/analysis/universal" taxonomy | Soft | Organizational heuristic | May not match empirical clusters |
| Single aggregate per model | Soft | Implementation choice | Multi-dimensional profiles |
| Goal is ranking | Assumption | Unvalidated | Goal is use-case RECOMMENDATION |

### Reconstruction — Recommended Architecture

Given only hard constraints, the optimal system is a **pipeline of pure functions**:

1. **Diagnostic layer**: Task classification (gate/discriminator/ceiling), difficulty and discrimination indices, confidence intervals via Agresti-Coull (not bootstrap)
2. **Profile layer**: Multi-dimensional model profiles with per-cluster scores, strengths/weaknesses
3. **Recommendation layer**: Use-case matching against profiles with explanations and confidence
4. **Exploration layer**: Pareto frontier for quality-cost/quality-speed tradeoffs

Each layer is independently testable. No layer requires IRT, EFA, or discrimination weighting (all invalid at N=8).

---

## Research-Verified Findings

| Claim in Analysis Doc | Verified? | Correct Value | Impact on PRD |
|---|---|---|---|
| IRT needs 10+ models | Understated | **50+ needed** for stable 2PL; 8 is infeasible | Remove IRT from all phases |
| Bootstrap CI useful at n=5 binary | **False** | Use Agresti-Coull exact intervals | Replace bootstrap with exact binomial CIs |
| Discrimination-weighted mean is standard | **Not standard** | IRT uses Fisher Information, not fixed weights. Naive weighting reduces validity at small N | Remove discrimination weighting |
| EFA feasible with 8x25 | **Mathematically impossible** | Correlation matrix singular at N<p | Use hierarchical clustering instead |
| USMLE uses non-compensatory scoring | Partially | Main exams are compensatory; only discontinued Step 2 CS was non-compensatory | Still valid pattern for safety gates |
| ICAO uses non-compensatory scoring | **Correct** | Must pass all 6 sub-skills independently | Validates safety gate design |
| Pareto frontier works with free models | **Correct** | Free models anchor cost at $0 | Include in exploration layer |
| `girth` package available | Unmaintained | Use `mirt` (Python/Rust) or `IRTorch` (PyTorch) | Not needed until Phase 4+ |

---

## Research Suggestions Disposition

Every suggestion from the research analysis, the original score-compression-analysis.md document (12 solutions S1-S12), and the RedTeam/Council findings. Each is either **ADDRESSED** in the PRD (specific phase and implementation) or **DEFERRED** with a concrete data gate that must be met before implementation.

### ADDRESSED in PRD

| # | Suggestion | Source | PRD Phase | How |
|---|-----------|--------|-----------|-----|
| S1 | Model Profile Vector | Analysis doc, IterativeDepth HC-1, Council unanimous | Phase 1 | `profiles.py` — per-cluster correctness/efficiency/latency/cost with CI bars and strength/weakness labels. Replaces single aggregate score with multi-dimensional profile. |
| S3 | Pareto Frontier Plot | Analysis doc, Research verified (works with free models) | Phase 2 | `pareto.py` — quality vs cost for paid models, quality-only for free models. ASCII or structured table in `--compare` output. Timestamped with eval data freshness. |
| S4 | Safety Gates (Non-Compensatory) | Analysis doc, Research verified (ICAO uses per-category minimums), Council unanimous | Phase 2 | `gates.py` + `config/gates.yaml` — per-cluster correctness gate (default threshold 0.60), coverage gate. Hard block by default, configurable to warning. Cites specific failed tasks. |
| S5 | Task Difficulty Recalibration | Analysis doc | Phase 1 | `diagnostics.py` — computes difficulty (p-value) and discrimination (σ) per task. Tasks at ceiling (p>0.90) and floor (p<0.10) flagged. Non-discriminative tasks (σ=0) excluded from cluster scores. |
| S11 | Anti-Profile Matching | Analysis doc, IterativeDepth HC-6 | Phase 1 | Profiles show bottom-2 clusters and specific weak tasks alongside strengths. "VERDICT" line summarizes both in plain language. |
| S12 | Saturation Monitoring | Analysis doc | Phase 1 | `diagnostics.py` — discrimination index per task is a first-class output. Tasks with σ near zero are flagged as saturated. Trackable over time as new models are added. |
| R1 | Exact Binomial CIs instead of Bootstrap | Research (bootstrap useless at n=5 binary) | Phase 1 | `ci.py` — Agresti-Coull interval. Handles n=5 binary correctly (only 6 possible outcomes). Replaces all bootstrap CI plans. No new dependencies (stdlib math only). |
| R2 | Hierarchical Clustering instead of EFA | Research (EFA mathematically impossible at N=8, p=25 — correlation matrix is singular) | Phase 3 | `correlation.py` — task correlation heatmap + hierarchical clustering of tasks by model response pattern. Reveals natural groupings without factor analysis. PCA on transposed matrix (25 tasks × 8 models) is valid. |
| R3 | Cronbach's Alpha for Cluster Validation | Council unanimous | Phase 2 | Computed per cluster in `profiles.py`. Flags clusters with alpha < 0.5 (tasks don't cohere). Triggers manual review of cluster composition. |
| R7 | Pareto Handling for Free Models | Research (free models anchor cost at $0) | Phase 2 | Separate Pareto frontiers: free models ranked quality-only, paid models on quality-cost. Free models that dominate paid models on quality are highlighted as "cost-optimal." |
| R8 | Per-Category Scoring with CIs | Research (LMSYS pattern) | Phase 1 | Cluster scores with Agresti-Coull CIs. Each cluster independently scored and confidence-bounded. Matches LMSYS per-category leaderboard pattern without Bradley-Terry model. |
| RT1 | Show Data, Don't Build Machinery | RedTeam (32-agent consensus) | All phases | Architecture is profile + decision support, not recommendation engine. Output presents facts; user makes decisions. No "Use Model X" assertions. |
| RT2 | Phased Scope | RedTeam (scope exceeds solo bandwidth if all built at once) | All phases | 3 phases with strict scope. Each phase independently useful. No phase depends on a later phase. |
| RT3 | Gate Explanation Requirement | Council (Aditi) | Phase 2 | Every gate failure cites specific tasks, samples, and CI. Not "GATE FAILED" but "FAILED: scored 2/5 on q5-safe-git-operations (CI: [15%-77%])." |
| RT4 | Configurable Thresholds | Council (Ava, Marcus) | Phase 2 | Gates, clusters, and CI levels all configurable via YAML. No hardcoded thresholds. User tunes without touching code. |
| C1 | Pipeline of Pure Functions | Council (Marcus, Ava) | Phase 1 | `pipeline.py` — each stage is a testable function. Diagnostics → Profiles → Output. Typed dataclasses at each boundary. |
| C2 | Manual Clusters in YAML | Council (unanimous) | Phase 1 | `config/clusters.yaml` — cluster name → list of task IDs + purpose description. Editable without code changes. Validated against task registry on load. |
| C3 | Cost as First-Class Dimension | Council (unanimous), Analysis doc | Phase 1 | Cost per sample per cluster in profile output. Free models show "FREE" explicitly. Value metric (correctness per dollar) alongside raw cost. |
| C4 | `--compare` Mode | Council (Aditi) | Phase 1 | Side-by-side profiles for two models. Primary user workflow. Low incremental cost over single-model profile. |

### DEFERRED — Data Gate Required

Each deferred item has a specific, measurable condition that must be true before it can be implemented. Not "too hard" — the condition is genuinely outside our control (needs more data, more models, more samples).

| # | Suggestion | Source | What It Needs | Current State | Gate to Unlock |
|---|-----------|--------|---------------|---------------|----------------|
| S2 | Discrimination-Weighted Aggregation | Analysis doc | 30+ models for stable discrimination estimates | 8 models — weights are dominated by sampling noise (a single anomalous model flips a task's discrimination weight) | N ≥ 30 evaluated models with consistent scoring. At that point, point-biserial discrimination indices become stable enough to use as weights without amplifying noise. |
| S6 | Bootstrap Confidence Intervals | Analysis doc | n ≥ 15-20 samples per task (continuous scoring helps too) | n=5 binary samples — only 6 possible outcomes per task. Bootstrap resampling from 6 discrete values produces biased, over-optimistic intervals. Agresti-Coull is used instead (exact for binary data). | n ≥ 15 samples per task, OR hybrid/continuous scoring on ≥50% of tasks (producing non-binary outcomes where bootstrap becomes valid). |
| S7 | IRT-Based Ability Estimation (2PL/3PL) | Analysis doc, ATLAS paper | 50+ models for stable IRT parameter estimation (difficulty b, discrimination a, ability θ). Standard psychometric minimum is 250-500 for 2PL. | 8 models — more parameters (8θ + 25a + 25b = 58) than data points (8×25 = 200 binary observations). Model would be entirely prior-dominated. | N ≥ 50 evaluated models. Then: install `IRTorch` (PyTorch, actively maintained, v0.5.3) or Python `mirt` (Rust-backed). Fit 2PL model. Compare IRT θ estimates to profile-based cluster scores to validate. |
| S8 | Exploratory Factor Analysis | Analysis doc, ICLR 2026 paper | 100+ models (N >> p requirement; current N=8, p=25 gives singular correlation matrix) | 8 models × 25 tasks — correlation matrix is rank-deficient (max rank 8, needs 25). EFA is mathematically impossible. | N ≥ 100 models. Then: run EFA to discover empirically-derived capability dimensions. Validate whether current 4-tier taxonomy matches factor structure. Replace manual clusters with factor-derived clusters if alpha improves. |
| S9 | Adaptive Task Selection | Analysis doc, ATLAS paper | IRT model must be fitted first (requires S7), THEN Fisher information can identify most informative tasks per model | No IRT model exists. Adaptive selection requires knowing each task's difficulty and discrimination parameters a priori. | S7 completed (IRT model fitted). Then: use Fisher Information to select 10-15 most informative tasks per model. Research shows 90% cost reduction while maintaining precision. |
| S10 | Use-Case Recommendation Engine | Analysis doc, IterativeDepth HC-2 | Validated mapping from task patterns to real-world use cases; user feedback confirming recommendations match actual production experience | No validation data. Task-to-use-case mapping is subjective (who decides "code assistant" maps to tasks {c1, c3, f2, u4}?). Recommending a model that fails in production destroys trust. | (1) Profile-based output used for ≥5 real model selection decisions by user. (2) User tracks whether chosen model performed as predicted. (3) If prediction accuracy ≥ 80%, build automated matching. Until then, profiles + manual user judgment. |
| R4 | IRT Python Packages (`IRTorch`, `mirt`) | Research | Same as S7 — IRT requires sufficient N | `IRTorch` v0.5.3 (PyTorch, Feb 2026) and Python `mirt` (Rust-backed) are current best options. Both are ready; the data isn't. | Same gate as S7. |
| R5 | LMSYS-Style Bradley-Terry Model | Research | 30+ models with pairwise comparison data | 8 models. Bradley-Terry needs many pairwise comparisons to estimate model-specific strength parameters reliably. Current data is task-level correctness, not pairwise comparisons. | N ≥ 30 models with pairwise eval data (or convert task-level to pairwise: for each task, model A "beats" model B if score_A > score_B). |
| S13 | Secret/Held-Out Task Set | RedTeam (gaming prevention) | Stable task infrastructure + regular eval cycle; enough tasks to justify holding some out | 36 tasks total. Holding out 5-10 means losing 14-28% of an already small task set. Discrimination would suffer further. | Task suite grows to ≥60 tasks. Then hold out 10 tasks as a secret validation set, not in the repo. Eval against secret set confirms public results aren't gamed. |
| S14 | Sample Size Increase (n=5 → n=10+) | IterativeDepth, RedTeam | More compute budget per eval run | n=5 binary gives ±0.22 CI per task. n=10 would halve CI width to ±0.15. n=20 would give ±0.11. But each eval run already takes significant time and cost. | Compute budget allows 2-4x samples per task without unacceptable time/cost increase. OR: implement continuous scoring (llm_judge/hybrid) on more tasks so n=5 continuous gives better resolution than n=5 binary. |

---

## Hidden Requirements (from 8-lens IterativeDepth)

48 ISC criteria generated across 8 lenses. 6 highest-confidence requirements appearing across 3+ lenses:

| # | Requirement | Supporting Lenses | Confidence |
|---|-------------|-------------------|------------|
| HC-1 | Multi-dimensional model profiles (not scalar scores) | Literal, Stakeholder, Experiential, Inversion, Analogical (5 lenses) | Highest |
| HC-2 | Use-case-specific recommendations ("for X, use Y") | Literal, Stakeholder, Experiential, Analogical (4 lenses) | Very High |
| HC-3 | Task discrimination as first-class measured metric | Literal, Failure, Meta (3 lenses) | High |
| HC-4 | Confidence indicators on every recommendation | Stakeholder, Failure, Meta (3 lenses) | High |
| HC-5 | User-adjustable pillar weights | Experiential, Inversion, Meta (3 lenses) | High |
| HC-6 | Recommendation explanations ("why" not just "what") | Stakeholder, Experiential, Analogical (3 lenses) | High |

---

## Council Synthesis (4-agent debate)

### Convergence Points (unanimous)

1. **Recommendation-first output** — primary output is "use Model X for Y", data underneath as expandable evidence
2. **Pipeline of pure functions** — Diagnostics → Profiles → Recommendations, each stage typed and testable
3. **Hard safety gates by default** — configurable via YAML to downgrade to warnings
4. **Three implementation phases** — Phase 1: usable tool. Phase 2: rich tool. Phase 3: extensible tool
5. **Manual clusters in YAML** — existing tier structure, validated post-hoc with Cronbach's alpha
6. **No psychometric methods** — IRT/EFA excluded (N=8 insufficient), architecture leaves room
7. **New `bench_cli/discriminative/` module** — consumes existing eval logs; existing code may be refactored where it improves clarity or removes duplication
8. **Cost as first-class dimension** — integrated from Phase 1

### Disagreements (resolved)

| Topic | Resolution | Rationale |
|-------|-----------|-----------|
| CI default: 90% vs 95% | 90% default, configurable | Avoids decision paralysis; user can tighten |
| `--compare` in Phase 1 or Phase 2 | Phase 1 | Primary user workflow, low incremental cost |
| Number of core types | 4: DiagnosticReport, ModelProfile, Recommendation, GateResult | Start minimal, add when needed |
| Per-cluster gate thresholds | Uniform default with optional per-cluster override in YAML | Simple default, flexible override |

---

## RedTeam Counter-Arguments

### Steelman (strongest arguments FOR the proposal)

1. **The current system is broken** — 8 models at 74-79% arithmetic mean provides zero decision value. Something must change.
2. **Capability profiles are simple, robust, and genuinely useful** — per-category breakdowns require no statistical machinery, work at N=8, and provide immediately actionable information. Highest-value, lowest-cost change.
3. **Safety gates are architecturally correct** — non-compensatory blocking on safety-critical tasks is standard in ICAO, FAA, nuclear regulatory. Framework is correct even if current models all pass.
4. **The 36 tasks are public and gameable** — but this is inherent to any fixed benchmark, not specific to this architecture.

### Fatal Flaws Identified & Mitigated

| Flaw | Severity | Mitigation |
|------|----------|------------|
| Discrimination weighting invalid at N=8 (weights dominated by noise) | HIGH | **Removed from PRD.** Use equal weights within manually-defined clusters instead |
| Bootstrap CIs provide false precision at n=5 binary | HIGH | **Replaced with Agresti-Coull exact intervals** — mathematically honest for small binary samples |
| Full-scope exceeds solo-developer bandwidth | HIGH | **Reduced to 3 phases with strict scope** — profiles + tables first, gates second, exploration third |
| Use-case matching creates false authority | MAJOR | **Bench reports facts, not recommendations** — output is "Model X is strong at Y, weak at Z" not "Use Model X" |
| Eval-to-production gap undermines recommendations | MAJOR | **Explicit disclaimers** — Bench measures narrow-task performance, not production behavior |

### Key RedTeam Insight

> "The correct implementation at N=8 is to SHOW the discriminative data (per-task tables, category profiles), not to BUILD discriminative machinery (weighting, CIs, recommendation engines) that the data cannot support."

This reshapes the architecture: Bench should be a **data presentation tool with profiles**, not a **recommendation engine**. The output helps the user decide; it doesn't decide for them.

---

## Success Criteria

### Phase 1: Foundation (Diagnostic + Profile + Basic Decision Support)

1. `bench_cli recommend --model openai/qwen-local` produces multi-dimensional profile output — verify by: run command, confirm per-cluster scores appear
2. Zero-discrimination tasks (σ=0) identified and flagged in output — verify by: check output includes discrimination index per task
3. Per-cluster correctness scores computed using existing tier groupings — verify by: compare cluster scores to manual calculation from inspect stats
4. Agresti-Coull 90% CI computed for each cluster score — verify by: check CI width is narrower than ±0.22 (per-task) for cluster aggregates
5. `--compare` mode shows side-by-side profiles for two models — verify by: run with two known models, confirm visually distinct profiles
6. Strength/weakness labels generated per model (top 2 clusters, bottom 2 clusters) — verify by: validate against known model characteristics
7. Cost appears in profile output as cost-per-sample per cluster — verify by: compare to `bench inspect stats` cost data
8. Existing code refactored where beneficial (not artificially constrained) — verify by: review diff for intentional improvements, not incidental changes
9. Existing 405 tests still pass — verify by: `pytest` returns 405 passed
10. New module has ≥90% test coverage — verify by: `pytest --cov=bench_cli/discriminative`

### Phase 2: Safety + Exploration

11. Safety gate tasks defined in YAML config with configurable thresholds — verify by: edit threshold, re-run, confirm changed behavior
12. Gate evaluation produces pass/fail with specific failed tasks listed — verify by: run on model with known safety weakness (e.g., Nem-30b on q5)
13. Gate results integrated into profile output (PASS/FAIL per gate) — verify by: confirm gate status appears alongside cluster scores
14. Pareto frontier computed for quality vs cost (paid models) and quality-only (free models) — verify by: generate frontier, confirm free models at cost=$0
15. Pareto frontier timestamped with eval data freshness — verify by: confirm output shows date of eval run
16. Cluster coherence validated with Cronbach's alpha — verify by: check alpha reported per cluster, flag clusters with alpha < 0.5

### Phase 3: Agent Eval + Extensibility

17. Agent eval results (model+agent+mode combos) flow through same pipeline — verify by: run with agent eval logs, confirm profile output
18. Custom clusters definable in YAML without code changes — verify by: add a custom cluster to YAML, re-run, confirm new cluster appears
19. Task correlation heatmap produced for exploratory analysis — verify by: generate heatmap, confirm task clustering patterns visible
20. Pipeline extension point documented for future psychometric methods — verify by: check docs describe where IRT stage would insert

---

## Edge Cases & Gotchas

- **Free models on Pareto**: All free models tie at cost=$0 — Pareto collapses to quality-only ranking among free models. Separate free vs paid frontiers.
- **Single model evaluated**: Profile still works (self-assessment). Gates still work. Comparison mode requires 2+ models.
- **New model is statistical outlier**: Profile will show unusual pattern. No misclassification risk because there are no fixed categories to shoehorn into.
- **All models pass all gates**: Expected for current model generation. Gates become useful as harder safety tasks are added.
- **Task added/removed between eval runs**: Profiles only include tasks that have data. Coverage gate flags missing tasks.
- **Judge model bias**: llm_judge scores are continuous but subject to GLM-5.1's own biases. Cross-validate with verify_sh where both exist.
- **Pricing changes between runs**: Pareto frontier uses eval-run-date pricing. Cached prices may be stale. Show cache freshness.
- **Binary scoring limits profile granularity**: With n=5, a cluster of 9 tasks gives aggregate CI of ~±0.07 (much better than per-task ±0.22). Aggregation helps.

---

## Anti-Patterns to Avoid

- **Don't build a recommendation engine** — Bench reports profiles and facts. The USER decides. False-authority recommendations are worse than no recommendation.
- **Don't use discrimination weighting** — Invalid at N=8. The weights amplify noise, not signal.
- **Don't use bootstrap CIs** — Useless at n=5 binary. Use Agresti-Coull exact intervals.
- **Don't use IRT or EFA** — 8 models is 2 orders of magnitude below minimum. Revisit at N=50+.
- **Don't preserve bad code for backward compatibility** — This is pre-alpha. Refactor existing modules where it improves clarity, removes duplication, or simplifies the system. No sacred cows.
- **Don't make safety gates too aggressive** — Current models are mid-range; gates should filter genuine safety risks, not create artificial failures.
- **Don't add dependencies** — Agresti-Coull is a simple formula (stdlib math only). No scipy, no girth, no IRTorch.
- **Don't conflate eval performance with production performance** — Bench measures narrow-task behavior. Always include disclaimers.

---

## Implementation Approach

### Phase 1: Foundation (1-2 sessions)

**Goal**: Multi-dimensional profiles that immediately distinguish models

```
bench_cli/discriminative/
├── __init__.py
├── types.py             # DiagnosticReport, ModelProfile, GateResult
├── pipeline.py          # run_pipeline(), PipelineConfig
├── diagnostics.py       # run_diagnostics() — difficulty + discrimination indices
├── profiles.py          # build_profile() — cluster scores + strengths/weaknesses
├── ci.py                # agresti_coull_ci() for binary confidence intervals
├── filters.py           # discrimination filter (σ < threshold → flag)
├── cli.py               # Click CLI: recommend --model, --compare
└── config/
    └── clusters.yaml    # cluster → tasks mapping + purpose
```

**Steps:**
1. Create `bench_cli/discriminative/` package skeleton with types
2. Implement `ci.py` — Agresti-Coull interval computation
3. Implement `filters.py` — compute σ per task across models, flag non-discriminative tasks
4. Implement `diagnostics.py` — per-task difficulty (p-value), discrimination (σ), CI on cluster aggregates
5. Implement `profiles.py` — per-cluster correctness, token ratio, time ratio, cost ratio with CIs
6. Implement `pipeline.py` — wire diagnostics → profiles, load clusters.yaml
7. Implement `cli.py` — `bench recommend --model X` and `--compare X Y` with rich formatted output
8. Write tests (target: ≥90% coverage)
9. Run full test suite, verify zero regressions

**Output format (Phase 1):**
```
PROFILE: qwen-local (huihui-qwen3.5-35b-a3b)
═══════════════════════════════════════════════

CLUSTER SCORES (90% CI):
  Competence:   0.83 [0.71-0.91]  ████████░░  GOOD
  Execution:    0.79 [0.68-0.88]  ████████░░  GOOD
  Analysis:     0.72 [0.58-0.84]  ███████░░░  FAIR
  Universal:    0.65 [0.52-0.77]  ██████░░░░  FAIR

STRENGTHS:
  ✓ q1-verification-gate (1.00), q3-answer-the-question (1.00)
  ✓ f7-format-compliance (1.00), add-tests (1.00)

WEAKNESSES:
  ✗ f16-bug-investigation (0.40)
  ✗ f22-error-spiral (0.35)

NON-DISCRIMINATIVE TASKS (excluded from cluster scores):
  add-tests (σ=0.000), f7-format-compliance (σ=0.000),
  q1-verification-gate (σ=0.000), q3-answer-the-question (σ=0.000)

COST: $0.00/sample (FREE, local model)
LATENCY: 8.2s avg (1.3× benchmark)

VERDICT: Strong on competence and execution.
Weak on error recovery and investigation.
Free — cost-optimal for any use case.
```

### Phase 2: Safety + Exploration (1 session)

**Goal**: Non-compensatory safety gates + Pareto frontier for cost-quality exploration

**Steps:**
1. Add `gates.py` — Gate protocol with correctness_gate, coverage_gate implementations
2. Add `config/gates.yaml` — gate definitions with thresholds, per-cluster overrides
3. Integrate gates into pipeline (between diagnostics and profiles)
4. Add gate results to profile output (PASS/FAIL per gate with failed tasks listed)
5. Add `pareto.py` — compute Pareto frontier on (correctness, cost) and (correctness, speed)
6. Add Pareto output to `--compare` mode (ASCII plot or structured table)
7. Add Cronbach's alpha computation to validate cluster coherence
8. Update tests

### Phase 3: Agent Eval + Extensibility (1 session)

**Goal**: Agent/harness results flow through same pipeline + exploratory tools

**Steps:**
1. Extend `ModelProfile` to handle composite IDs (`model|agent|mode`)
2. Add task correlation heatmap output (ASCII or matplotlib)
3. Document pipeline extension points for future psychometric methods
4. Add `--agent` and `--agent-mode` flags to `bench recommend`
5. Update tests

---

## Test Plan

- **Unit tests**: ci.py (Agresti-Coull against known values), filters.py (σ computation), profiles.py (cluster aggregation), gates.py (pass/fail logic)
- **Integration tests**: Full pipeline from eval logs to profile output, compare mode with two models
- **Regression tests**: Existing 405 tests still pass after any refactoring
- **Validation tests**: Profile output matches manual calculation from `bench inspect stats` for known model

---

## Docs to Update

- [ ] CLAUDE.md — add `bench recommend` to CLI Usage section
- [ ] docs/EVAL-GUIDE.md — add discriminative output interpretation guide
- [ ] bench_cli/discriminative/config/clusters.yaml — cluster definitions with purpose descriptions

---

## Open Questions

1. **Use-case categories**: Should Bench define preset use-cases ("surgical edits", "complex reasoning") or let users define their own via pillar weights? → **Resolution: User-defined weights.** Preset use-cases create false authority. The profile shows the data; the user maps it to their use-case.

2. **Cluster definitions**: Start with existing 4-tier taxonomy or merge/split based on correlation analysis? → **Resolution: Start with 4 tiers, validate with Cronbach's alpha, adjust if alpha < 0.5.**

3. **Safety gate thresholds**: What correctness level constitutes "safe"? → **Resolution: 0.60 default (configurable).** Below 60% on a safety cluster means the model fails more often than it passes. User can tighten or relax.

4. **Phase 1 CLI name**: `bench recommend` or `bench profile`? → **Resolution: `bench recommend`** — matches the user's mental model ("tell me what to use"). Output is actually a profile, but the command name reflects the intent.

---

## Skill Integration Log

- **FirstPrinciples/Deconstruct**: Identified measurement instrument as 3-layer system (stimulus/transducer/aggregator); found signal already exists (r=0.615); framed as information extraction problem
- **FirstPrinciples/Challenge**: Classified constraints; found 5 hidden assumptions including "ranking is the goal" and "more metrics = better"; validated that goal is RECOMMENDATION not RANKING
- **FirstPrinciples/Reconstruct**: Generated 3 alternative architectures; recommended hybrid Diagnostic + Profile approach; mapped 12 solutions to architectural layers
- **IterativeDepth**: 48 ISC across 8 lenses; 6 highest-confidence criteria; confirmed Profile as architectural keystone
- **Council**: 4-agent 3-round debate; unanimous on recommendation-first, pipeline architecture, hard gates, manual clusters, no psychometrics, refactoring permitted
- **RedTeam**: 32-agent attack; identified 3 fatal flaws (discrimination weighting, bootstrap CIs, scope); reshaped PRD from recommendation-engine to data-presentation
- **Research**: Verified 8 claims; corrected IRT minimum (50+), bootstrap invalidity, EFA impossibility, Agresti-Coull as alternative; confirmed Pareto works with free models

---

## Implementation Notes

*Fill this as you work. Capture: decisions made and why, trade-offs considered, gotchas found, ideas for later.*

- **Decision**: Removed discrimination weighting from PRD based on RedTeam finding that N=8 weights amplify noise. Equal weights within manually-defined clusters instead. Deferred to N≥30 (see Research Suggestions Disposition).
- **Decision**: Replaced bootstrap CIs with Agresti-Coull exact intervals based on Research finding that bootstrap is useless at n=5 binary samples. Deferred bootstrap to n≥15 or continuous scoring (see Research Suggestions Disposition).
- **Decision**: Changed from "recommendation engine" to "profile + decision support" based on RedTeam finding that false-authority recommendations are worse than honest data. Automated recommendation engine deferred to after validated prediction accuracy (see Research Suggestions Disposition).
- **Decision**: Removed IRT and EFA from all phases based on Research confirmation that N=8 is 2 orders of magnitude below minimum. Deferred to N≥50 for IRT, N≥100 for EFA (see Research Suggestions Disposition).
- **Decision**: Cluster definitions in YAML, not code, per Council consensus.
- **Decision**: Refactoring existing code is permitted and encouraged — this is pre-alpha. No backward compatibility constraints.
- **Gotcha**: Free models return `price_ratio = inf` — Pareto frontier needs special handling.
- **Gotcha**: Binary verify_sh scores only have 6 possible values at n=5 (0/5 through 5/5) — CI computation must account for discreteness.
- **Idea**: Future: accumulate data across 50+ models, then revisit IRT using `IRTorch` or Python `mirt` package.
- **Idea**: Future: hold out 5-10 secret tasks not in the repo to prevent benchmark gaming.
