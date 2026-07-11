**Status:** validated
**Project:** bench
**Owner:** Tasa
**Scope:** refactor
**Date:** 2026-07-10
**Tier:** deep

---

# PRD: Scoring & Discrimination Redesign — Valid Model Differentiation

## Problem Statement

Bench cannot validly differentiate between models. Two intertwined root causes, diagnosed in session 2026-07-10T1325-pi and confirmed by literature review:

1. **Correctness ceiling (discrimination failure).** 13 of 16 full-eval models cluster within an IQR of ~3% correctness (≈0.78–0.82). Only 4 tasks currently discriminate (`f12-surgical-fix`, `f16-bug-investigation`, `f17-config-migration`, `f22-error-spiral`). The suite is too easy — models hit a capability ceiling and bunch. Result: the correctness pillar carries almost no signal across the middle of the field.

2. **Pillar non-commensurability (measurement failure).** The 4 pillars are measured in mutually incompatible ways: correctness is a bounded absolute 0-1; token/latency/cost ratios are unbounded ratios against different, unstable references (BaselineStore empty → `task_budgets.py` fallback; cost references minimax-m3, token/latency reference qwen-local). Three pathologies stack: mixed bounded/unbounded scales, different baselines per pillar, and degenerate edge cases (free models → `price_ratio=inf`). Adding a bounded value to three unbounded ratios is dimensionally invalid. The 2026-07-10 session's F0–F9 formula search (linear, geometric, log-bounded, gated, multiplicative, percentile-rank, correctness-only, Pareto) exhausted the "fix the weighting" space — none was satisfying because you cannot weight your way out of non-commensurable inputs.

These compound: when correctness doesn't discriminate, any combined metric is dominated by efficiency ratios that *do* discriminate — but on cheapness/speed, not capability. That's why `mistral-small-2603` and `devstral-2512` ranked top under the weighted formula.

**The desired outcome** (project `bench` outcome statement): a reliable personal harness that tells the user which local LLM, agent, or harness to actually use, discriminating on a 4-pillar rubric instead of vibes.

---

## First Principles Analysis

### Deconstruction

What is each component actually doing?

| Component | Function | Load-bearing for which problem? |
|-----------|----------|--------------------------------|
| Averaged pass@1 (capability) | Headline absolute 0-1 score | Baseline (already correct) |
| IRT (Bayesian 2PL) | Interpret whether discrimination is real; per-item difficulty/discrimination | Problem A (measurement) |
| Harder tasks (B2) | **Create** new discrimination signal | **Problem A (the real fix)** |
| Efficiency-as-columns + sub-measures | Display, don't aggregate | **Problem B (kills it)** |
| Preset router | Per-use-case decision layer | The outcome ("which model to use") |
| Bootstrap CIs | Honesty layer on capability mean | Cross-cutting rigor |

### Constraint classification

**Hard constraints:** single-user personal instrument; `.venv`/pytest; LiteLLM proxy; Inspect `.eval` format; Python 3.14.5; B-tier open-source; existing per-sample data already in logs (IRT-viable immediately); frozen `task_budgets.py` constants.

**Design constraints (locked in interrogation):** capability scored as absolute 0-1, efficiency displayed not aggregated (Option A); IRT now via Bayesian hierarchical 2PL; preset router; reuse existing data; PyMC as IRT engine.

**Rejected approaches:** single weighted score (retired — F0–F9 proven invalid); cohort-relative min-max/z-score normalization (the "relative to something" disease); pairwise Elo (needs crowdsourced votes); forcing efficiency into a bounded 0-1 scale (clumps one tail — every attempt failed).

### Reconstruction

The field's consensus (HELM, SWE-bench, Open LLM Leaderboard, Artificial Analysis), validated by extensive-mode research: **score capability, display efficiency, route per use-case.** Artificial Analysis — the most respected model-comparison site — does not fold efficiency into its Intelligence Index; cost/tokens/time are separate columns. This is not a compromise; it is the recognized answer to the commensurability problem. The user's "make everything 0-1" instinct correctly diagnosed the disease (unbounded ratios, moving baselines) but prescribed the wrong cure — the field's answer is to refuse forced commensurability.

IRT adds the discrimination engine: per-item difficulty/discrimination parameters identify which tasks actually separate models, and ability estimates θ + CIs honestly report whether observed gaps are real or noise.

---

## Research-Validated Foundations

### The four canonical scoring patterns

| Pattern | Who uses it | Relevance |
|---------|-------------|-----------|
| Averaged pass@1 (absolute) | SWE-bench, Open LLM, AA Intelligence Index | **This is what capability already is.** Zero change to mechanism. |
| Fixed-bound normalization | Open LLM Leaderboard: `(x - lower) / (upper - lower)` with FROZEN bounds (chance→perfect) | Legitimate "0-1 all" if needed; bounds don't move when models added |
| Cohort min-max / z-score | HELM, Dynaboard | Cohort-relative — rejected (the disease) |
| Pairwise Elo | Chatbot Arena | Needs votes — not applicable |

### IRT-for-LLM is conventional, not novel

"Transposed IRT" (models = respondents, tasks = items) is the standard approach in the literature: PSN-IRT, TinyBenchmarks, "Lost in Benchmarks?" (AAAI 2025), "Lifting the benchmark iceberg with IRT" (OpenReview).

### Artificial Analysis sub-measure formulas (exact, replicable)

From `artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index` and the Coding Agent Index methodology page:

- **Capability score** = weighted average of component benchmark pass@1 scores, scaled 0-100. Four categories × 25%.
- **Cost per task** = `Σ(weightᵢ × costᵢ) / Σ(weightᵢ)`, where `costᵢ = Σ(token_count × price)` across input / cache-hit / cache-write / reasoning / answer token types. Lower = better.
- **Tokens per task** = pooled per-task-attempt average = total tokens / total attempts. Split into reasoning vs answer tokens.
- **Time per task** = output_tokens_per_task / output_speed, weighted. Excludes TTFT/overhead.
- **Intelligence per dollar** = capability_score / cost_per_task (derived).
- **Intelligence per token** = capability_score / tokens_per_task (derived).

All computable from existing `.eval` logs (per-type `model_usage` + `total_time` per sample). Zero new instrumentation.

### Bootstrap CI methodology

Resample tasks with replacement 1000–10000×; 2.5th/97.5th percentiles of the resampled mean = 95% CI. Requires ≥30–50 items (bench has 34 → ~44 after B2). Paired McNemar's test for same-task head-to-head comparison. **Overlapping CIs = statistically indistinguishable.** Oxford review of 445 benchmarks: 84% publish rankings with zero statistical testing. This single addition would have prevented the entire weighted-formula misranking disaster.

### Harder-task authoring pipeline (SWE-bench / MMLU-Pro)

1. Select real multi-file problems requiring long-horizon reasoning.
2. Decompose; craft distractors that are surface-correct but fail edge cases.
3. Pilot test on strong + weak baselines.
4. Compute IRT item params (difficulty b, discrimination a).
5. Discard low-discrimination items (ceiling/floor items carry no signal).
6. Blind expert verification of gold answer + distractor realism.

IRT item params feed back into authoring — it is a calibration loop, not one-shot. The ~10 new tasks should land in the ability band where current models cluster (b ≈ cluster θ).

---

## Hidden Requirements

Surfaced during interrogation and research:

1. **The anchor must not move when models are added/removed.** The disease behind "relative to something" was unstable references (empty BaselineStore, different refs per pillar) and unbounded ratios — not relativity itself. Frozen repo constants satisfy this.
2. **Indistinguishability must be reportable as a first-class output.** The honest answer to "which model is best" is often "these are tied." The old design couldn't express this; CI overlap must.
3. **IRT must respect the 4-pillar structure** (analysis/competence/execution/universal). A single unidimensional θ smears distinct abilities. Per-pillar IRT or per-pillar θ breakdown required.
4. **The headline number must be glanceable.** IRT θ (latent, N(0,1)) is not. pass@1 (0-1) is. The primary score stays pass@1; θ is the rigor check beneath.
5. **PyMC must be isolated.** B-tier open-source consumers must not pay the dependency cost for an optional analysis layer.

---

## Risk Analysis & Counter-Arguments

### F1 — IRT unidimensionality violated (HIGH)
2PL assumes one latent ability. Bench has 4 pillars (glm-5.2 measured at 88/81/72/78 across analysis/competence/execution/universal). A single θ smears distinct abilities.
**Mitigation:** Fit 2PL per pillar (4 separate models) OR fit a general θ and display per-pillar means as context. Multidimensional IRT (MIRT) needs more data — worse at N=16. **Decision: fit per-pillar 2PL; display general θ as headline with per-pillar θ as breakdown.**

### F4 — N=16 + wide CIs → "everything overlaps" frustration (HIGH)
The most likely production failure. IRT honestly reports most models indistinguishable within noise. User wanted discrimination; gets ambiguity. Frustration → ignores IRT → reverts to point estimates → back to square one.
**Mitigation:** (a) Frame wide CIs as the truth — the old leaderboard was false precision. (b) Prioritize B2 harder tasks to actually create separation. (c) Add models over time to tighten. (d) UX: when CIs overlap, the leaderboard shows a "statistically tied" badge, not a misleading rank order. **This is the #1 UX risk; the redesign must set expectations that "indistinguishable" is a valid and valuable output.**

### F10 — Task authoring is labor-intensive (HIGH, schedule risk)
SWE-bench/MMLU-Pro authoring is a 6-step pipeline with pilot testing, distractor crafting, blind verification. ~10 quality tasks is person-weeks, not a weekend. If B2 slips, IRT ships on thin data → F4 fires.
**Mitigation:** PRD phases B2 explicitly. Prefer porting hard tasks from existing benchmarks (SWE-bench-Verified, MMLU-Pro coding subset) over authoring from scratch. The lower-authored-effort path exists and is legitimate.

### F2 — IRT θ is not glanceable (MEDIUM)
pass@1=0.81 means "81% right." IRT θ=0.4 means nothing to a user.
**Mitigation:** Report pass@1 as headline; θ+CI as the "is this real?" rigor check beneath. Optionally linear-rescale θ to 0-100 for display.

### F3 — Two CI systems confuse (MEDIUM)
Bootstrap CI on pass@1 mean vs IRT credible interval on θ. Different questions (raw performance variance vs latent ability uncertainty).
**Mitigation:** Clear labeling: "performance CI" vs "ability CI." Consider whether both are necessary (bootstrap is simpler and may suffice if IRT is mainly for item analysis).

### F5 — Preset router underspecified (MEDIUM, blocks implementation)
"cheap-fast / best / balanced" have no weights/thresholds/filters. Unbuildable as stated.
**Mitigation:** Success criteria and implementation approach define exact preset logic (see below).

### F6 — Router reintroduces aggregation (LOW, be honest)
"Display efficiency, don't aggregate" is the Option A principle. But the router must combine capability + efficiency to rank per use-case. Aggregation happens — just per-use-case, not globally. This is the Dynaboard model and is legitimate. The PRD documents this honestly rather than claiming "no aggregation."

### F7 — Sub-measures are ratios (LOW, clarify not eliminate)
"Intelligence per dollar" = capability/cost. That's a ratio. The user rejected "relative to something." Distinction: the OLD design used ratios as the aggregated headline score (wrong). The NEW design uses ratios as derived decision metrics in context columns (legitimate — AA does this). Documented to avoid the appearance of keeping the disease.

### F8 — PyMC dependency cost (MEDIUM, B-tier)
PyMC + PyTensor add weight. Slower test imports, bigger install, harder reproduction for open-source consumers.
**Mitigation:** Isolate IRT in `bench_cli/irt/` with lazy import. Bench core (run/compare/recommend) works without PyMC. IRT is an opt-in analysis command (`bench irt fit`, `bench irt item-analysis`).

### F9 — Re-score migration fragility (MEDIUM)
Re-scoring 16 models offline assumes clean `.eval` logs. Reality: 44 corrupt files (task 14e79d29), archived logs, old scorer formats.
**Mitigation:** Migration script validates each log, reports skip count with reasons, never silently degrades. Tested explicitly against the 44 known-corrupt files.

---

## Success Criteria

### Capability scoring (Option A)

1. **Capability score is absolute pass@1 mean, 0-1, per model.**
   - verify by: `bench compare` output shows a `capability` column in [0,1] for each full-eval model; the value equals the manual mean of per-sample pass@1 across that model's logged samples.
2. **No weighted aggregate score exists in the default `bench compare` output.**
   - verify by: the 0.5/0.2/0.15/0.15 weighted formula code path is removed or moved behind an explicit `--legacy-weighted` flag; default `bench compare` contains no single combined number.
3. **Efficiency pillars (cost, tokens, latency) are displayed as raw columns, not aggregated.**
   - verify by: `bench compare` shows `cost/task`, `tokens/task`, `time/task` as separate columns with raw units ($, tokens, seconds); none are combined into a single efficiency score.

### IRT discrimination engine

4. **IRT fits a Bayesian hierarchical 2PL model per pillar via PyMC.**
   - verify by: `bench irt fit` produces posterior ability estimates θ + 95% credible intervals for each model, per pillar; a unit test asserts the model spec compiles and fits on a synthetic 2PL dataset with known params recovering them within tolerance.
5. **IRT item analysis reports difficulty (b) and discrimination (a) per task.**
   - verify by: `bench irt item-analysis` outputs a table of all tasks with their a, b parameters and a "discrimination band" label (high/medium/low/cull); tasks flagged "cull" are those with a below a documented threshold.

### Statistical honesty

6. **Bootstrap 95% CIs are computed and displayed on the capability mean for every model.**
   - verify by: `bench compare` shows a `capability [CI]` column (e.g. `0.81 [0.74, 0.88]`); CI computed by resampling tasks 1000× with a fixed seed for reproducibility.
7. **Models with overlapping capability CIs are visually marked as statistically tied.**
   - verify by: in `bench compare`, tied models share a rank or show a "≈" tie badge; a unit test feeds two models with deliberately overlapping synthetic CIs and asserts the tie badge renders.

### AA-style sub-measures

8. **`bench compare` displays: cost/suite, tokens/suite, time/suite, intelligence/$, intelligence/token.**
   - verify by: the five sub-measures appear as columns; values match a manual computation from the logged per-sample `model_usage` and `total_time` for a test model.
   - formulas:
     - `cost/suite` = Σ per-sample cost across the suite
     - `tokens/suite` = Σ per-sample total tokens
     - `time/suite` = Σ per-sample wall time
     - `intelligence/$` = capability_score / cost_per_task
     - `intelligence/token` = capability_score / tokens_per_task

### Preset router

9. **`bench recommend --preset <name>` ranks models per the preset's defined logic.**
   - verify by: each preset produces a deterministic ranking given the same input data; a unit test asserts the ranking for a synthetic cohort.
   - preset definitions (locked in this PRD):
     - `best`: rank by capability θ (highest first); ignore efficiency.
     - `cheap-fast`: filter to models with `cost/task < cohort median`; among those, rank by `time/task` ascending, then capability θ descending.
     - `balanced`: compute Pareto front across (capability, -cost, -time); rank Pareto-optimal models by capability θ, then list dominated models below.

### Harder tasks (B2)

10. **At least 8 new tasks land in the discriminating difficulty band (IRT difficulty b within ±0.5 SD of the cohort's mean θ).**
    - verify by: after the new tasks are evaluated on all full-eval models, `bench irt item-analysis` classifies ≥8 of the new tasks as "high discrimination" (a above threshold) and their b parameters fall in the target band.

### Data reuse & migration

11. **Existing 16 full-eval models are re-scored offline from current `.eval` logs without re-running any model.**
    - verify by: a one-shot `bench rescore` command reads existing logs, recomputes the absolute scores from logged usage, and writes updated logs; API call count during the operation is zero.
12. **The rescore command skips corrupt logs explicitly and reports them.**
    - verify by: running `bench rescore` against the 44 known-corrupt files (task 14e79d29) produces a skip report naming each skipped file and the reason; zero silent corruptions.

### Dependency isolation

13. **Bench core (run/compare/recommend/rescore) imports and runs without PyMC installed.**
    - verify by: `pip uninstall pymc && .venv/bin/pytest -q` passes the non-IRT test suite; only `bench irt *` commands fail with a clear "PyMC required" message.

---

## Edge Cases & Gotchas

- **Unpriced models and `nan` cost.** Validated 2026-07-10: 6 of 16 full-eval models have **`nan` cost** (kimi-k2.7-code, default, devstral-2512, nemotron-3-nano-30b-a3b, gemma-4-26-local, qwen-local — the local/free/unpriced models where cost was never recorded, not infinite). Only 10/16 have real cost data. intelligence/$ is `nan` for these. Handle: display `intelligence/$` and `cost/suite` as "n/a (unpriced)" for nan-cost models, never render `nan` or `inf`.
- **Reasoning models eat output budget invisibly.** (Known gotcha, carries forward.) Tokens/suite must split reasoning vs answer tokens; intelligence/token uses answer tokens only, or both with a labeled split.
- **Redis cache poisoning viability runs.** (Known gotcha.) When re-scoring offline this is moot (no live calls). When running new B2 tasks, use unique nonces per prompt.
- **IRT fit fails to converge at N=16 per pillar.** Bayesian hierarchical priors provide shrinkage; if convergence still fails, fall back to fitting a single general θ (aggregate pillars) and report per-pillar pass@1 means as context. Convergence failure is a documented acceptable outcome, not a crash.
- **Recorded-identity divergence.** (`openai/go-deepseek-v4-pro` vs `deepseek/deepseek-v4-pro`.) The IRT outcome matrix must reconcile recorded identities before fitting, or the same model appears twice and splits its response data. Reuse the discriminative tool's recorded-identity matching (task 4940c0c8).
- **Moniker aliases (default/thinking/heavy).** Must never enter the IRT model as respondents — they are duplicates of concrete models. Filter via `is_moniker_alias`.
- **Bootstrap CI on partial-eval models.** CIs on n<34 are wide and misleading. Only display CIs for full-eval (≥34 task) models; partial models show "insufficient data."
- **Resume default-on.** After the scorer change, `bench run` will skip status="success" logs. The B2 new-task runs must use `--no-resume` or the new tasks won't evaluate.

---

## Anti-Patterns

- **Do not reintroduce a single weighted aggregate score as the default.** F0–F9 proved this invalid. A `--legacy-weighted` escape hatch is acceptable for backward comparison; the default must not aggregate non-commensurable pillars.
- **Do not use cohort-relative normalization (min-max, z-score) for scored pillars.** This is the "relative to something" disease — adding a model changes everyone's score. Frozen bounds only.
- **Do not treat IRT as the ceiling fix.** IRT measures honestly; harder tasks create discrimination. If B2 slips, ship IRT as item-analysis only and defer ability-ranking until the task matrix supports it.
- **Do not make IRT θ the headline number.** It is latent and not glanceable. pass@1 is the headline; θ+CI is the rigor check.
- **Do not silently drop models/logs during rescore.** Every skip must be reported with a reason. Silent degradation is how the 96% "ghost #1" deepseek entry polluted the leaderboard.
- **Do not conflate "performance CI" (bootstrap on pass@1) with "ability CI" (IRT credible interval on θ).** Label them distinctly.
- **Do not evaluate moniker aliases (default/thinking/heavy) as IRT respondents.**
- **Do not bound efficiency into a 0-1 score via clamp, saturation, or log scale as a pillar score.** Every variant clumps one tail. Efficiency is displayed, not scored.

---

## Implementation Approach

Phased. B2 (harder tasks) is the critical path — IRT has no signal without it.

### Phase 0 — Rescore migration (unblocks everything, zero API cost)
- Write `bench rescore`: reads `.eval` logs, recomputes absolute scores from logged usage, writes updated logs, reports skips.
- Delete the weighted formula from default `bench compare`; move behind `--legacy-weighted`.
- Add the efficiency columns (cost/task, tokens/task, time/task) to `bench compare`.
- Add the 5 AA sub-measures.
- Test against the 44 corrupt files.
- **Delivers:** Success criteria 2, 3, 8, 11, 12.

### Phase 1 — Statistical honesty
- Add bootstrap CI computation to `bench compare` (resample tasks 1000×, fixed seed).
- Render `capability [CI]` column; add "statistically tied" badge for overlapping CIs.
- **Delivers:** Success criteria 1, 6, 7.

### Phase 2 — Harder tasks (B2, the critical path)
- Source ~10 tasks: prefer porting from SWE-bench-Verified / MMLU-Pro coding subset over authoring from scratch.
- Run each new task on all 16 full-eval models (`--no-resume`).
- **Delivers:** feeds Phase 3; partial success criterion 10 (full verification needs Phase 3's IRT item analysis).

### Phase 3 — IRT engine
- Add `bench_cli/irt/` with lazy PyMC import.
- Implement Bayesian hierarchical 2PL per pillar; general θ + per-pillar θ.
- `bench irt fit` → posterior θ + 95% credible intervals per model per pillar.
- `bench irt item-analysis` → a, b parameters + discrimination band labels per task.
- Reconcile recorded identities and filter monikers before fitting.
- Convergence-failure fallback documented (single general θ).
- **Delivers:** Success criteria 4, 5; completes 10.

### Phase 4 — Preset router
- Implement `bench recommend --preset {best,cheap-fast,balanced}` with the locked logic.
- Pareto computation for `balanced`.
- **Delivers:** Success criteria 9.

Phases 0–1 ship value independently and should land first. Phase 2 is the long pole. Phases 3–4 depend on 2 having shipped.

---

## Hypothesis & Measurement Framework

**Goal:** Validly differentiate between models on capability, with honest reporting of indistinguishability.

**H1:** The current 13-model cluster at ~81% is a ceiling artifact, not a real equivalence. Adding ~10 tasks in the cluster's ability band will spread the cluster into a distinguishable distribution.
- verify by: after B2, recompute the cohort IQR; if IQR expands beyond ~6% (double the current ~3%), H1 supported.

**H2:** Bootstrap CIs will show that several models ranked distinctly in the old weighted leaderboard were statistically indistinguishable.
- verify by: compare old leaderboard rank order to the new CI-overlap tie groups; count models whose old distinct rank becomes a tie.

**H3:** IRT item analysis will identify a subset of current tasks as low-discrimination (ceiling/floor) dead weight.
- verify by: `bench irt item-analysis` flags ≥5 existing tasks as "cull" (low a); their removal does not reduce the cohort's ability-estimate stability.

**H4:** The preset router will recommend different models for different presets, demonstrating that no single "best model" exists.
- verify by: `bench recommend --preset best` and `--preset cheap-fast` return different top-3 models on the current cohort.

**Measurement discipline:** all verification commands run live; no staleable numbers written to vault prose.

### Validation against live data (2026-07-10)

Hypotheses H1–H4 plus the structural claims were checked against the real `.eval` logs (16 full-eval models, 34 tasks with ≥10-model coverage). Script: `/tmp/validate_prd.py`; full report: `/tmp/bench_validation_results.md`.

| Hypothesis / claim | Pre-validation assertion | Validated result | Outcome |
|---|---|---|---|
| C1 cluster IQR | ~3% | **3.0%** (q1=0.783, med=0.803, q3=0.813); 11/16 in [0.78,0.82] | ✅ confirmed |
| H2 tie collapse | "several distinct ranks false precision" | **88% of pairs (106/120) indistinguishable**; #1 (kimi) tied pairwise with ranks 2–14; only #15–#16 separable | ✅ confirmed (stronger) |
| H3 dead-weight items | ≥5 cull candidates | **26/34 dead weight** (22 low-disc + 4 ceiling); only `add_tests` high-disc | ✅ confirmed (much stronger) |
| H4 preset divergence | presets recommend different models | best/cheap-fast/balanced → 5 distinct across union; only mimo-v2.5-pro common | ✅ confirmed |
| EC partial CIs | gating on n≥34 needed | 7 partial models would show misleading CIs | ✅ confirmed |
| SM sub-measures | computable from logs | all 5 computed | ✅ confirmed |

**Corrections applied to the PRD from validation:**
1. The previously-cited discriminators `f17_config_migration` and `f22_error_spiral` are in fact **low-discrimination** (stdev<0.15) — they carry no signal. Problem Statement corrected.
2. The free-model edge case is **`nan` (cost never recorded), not `inf`** — affects 6/16 models (kimi, default, devstral-2512, nemotron-3-nano-30b, gemma-4-26-local, qwen-local). Edge-case and Success Criterion wording corrected.
3. Tie detection specified as **pairwise CI overlap, not transitive chaining** (chaining overstates ties by grouping A-ties-B, B-ties-C into one cluster). Success Criterion 7 corrected.
4. Success Criterion 10 strengthened: require ≥5 of the new tasks to be high-discrimination (not just in-band), because the current bar is a single task.

**What validation did NOT cover** (still open): H1 (does adding tasks spread the cluster?) requires B2 to ship first; the IRT θ recovery test (SC4) requires PyMC. These remain implementation-gated.

---

## Alternative Approaches Considered

- **Single legitimate 0-1 score via fixed-bound normalization (Open LLM Leaderboard formula).** Gives the glanceable number; bounds are frozen constants not cohort. Rejected because it still forces commensurability between intrinsic (correctness) and extrinsic (efficiency) dimensions — the thing that made F0–F9 unsatisfying. The field (AA, HELM) explicitly chose not to do this.
- **IRT phased to a later PRD.** Rejected by user ("IRT now"). Accepted the N=16 wide-CI constraint with the understanding that more models tighten estimates over time.
- **Hand-rolled EM for 2PL.** Lighter dependency than PyMC but no built-in Bayesian shrinkage (needed for small-N stability) and more code to validate. Rejected.
- **Multidimensional IRT (MIRT).** Would respect the 4-pillar structure in a single fit. Needs more data than N=16 supports. Deferred; per-pillar 2PL is the pragmatic equivalent.
- **Cohort min-max / z-score normalization (HELM, Dynaboard).** Cohort-relative — the "relative to something" disease the user rejected. Adding a model changes everyone's score.

---

## Open Questions

1. **IRT library choice is settled (PyMC), but per-pillar fit vs general θ fit at N=16:** 4 separate fits on 16 models each is 4× the small-N problem. May need to collapse pillars into fewer dimensions for IRT viability. Decision deferred to Phase 3 implementation — fit per-pillar first, fall back to general θ if convergence fails (documented in F1 mitigation).
2. **Bootstrap CI vs IRT credible interval — keep both?** They answer different questions (performance variance vs ability uncertainty). Both may be necessary, but F3 flags conflation risk. Decision: ship both with clear labels in Phase 1/3; revisit if UX testing shows confusion.
3. **Harder-task source: port vs author.** Porting from SWE-bench-Verified / MMLU-Pro is faster but may not match bench's task format (verify_sh, pillar subdirs) cleanly. Authoring from scratch is higher-quality but person-weeks. Phase 2 will assess porting viability on the first 2 tasks before committing.
4. **Preset router threshold tuning.** The locked definitions use cohort median (for cheap-fast) and Pareto (for balanced). These may need tuning once real data flows. Phase 4 will validate on the current cohort.

---

## Skill Integration Log

- **Interrogation (Deep mode):** Surfaced the branch structure (B1 measurement / B2 discrimination / B3 decision / B4 honest-reporting). User rejected B4, accepted B1+B2+B3 mix. Resolved the cost-pillar anchor question (user: "choose whatever"). Redirected from "make everything 0-1" (wrong cure) to "score capability, display efficiency" (field consensus) after research. Resolved IRT-now, data-reuse, and preset-router scope.
- **Research (Extensive mode):** Validated the four canonical scoring patterns; confirmed IRT-for-LLM is conventional; extracted exact AA sub-measure formulas; confirmed bootstrap CI viability at 34–44 tasks; surfaced the N=16 IRT gray zone (mitigated by Bayesian hierarchical priors) and the py-irt/Python 3.14 incompatibility (resolved by PyMC). Two decision-gaps surfaced and resolved by user.
- **Thinking (Deep tier, focused):** First-principles decomposition (B2 is the real fix, IRT measures), 10-risk red-team pass. Top risks: F1 (unidimensionality → per-pillar IRT), F4 (wide-CI frustration → expectation-setting + tie badges), F10 (authoring labor → port from existing benchmarks). Tensions carried as open questions.

**Carried-forward artifacts:**
- `/tmp/bench_research_synthesis.md` — research findings + validated formulas.
- `/tmp/bench_thinking_synthesis.md` — risk analysis.

---

## Test Plan

Per success criterion:

| SC | Test |
|----|------|
| 1 | `tests/test_compare.py::test_capability_column_is_pass1_mean` — synthetic logs, assert column value matches manual mean |
| 2 | `tests/test_compare.py::test_default_compare_has_no_weighted_score` — assert the 0.5/0.2/0.15/0.15 number is absent unless `--legacy-weighted` |
| 3 | `tests/test_compare.py::test_efficiency_columns_raw_units` — assert cost/tokens/time columns present with correct units |
| 4 | `tests/test_irt.py::test_2pl_recovers_synthetic_params` — fit on synthetic 2PL data, assert param recovery within tolerance |
| 5 | `tests/test_irt.py::test_item_analysis_labels_cull` — feed low-a items, assert "cull" label |
| 6 | `tests/test_compare.py::test_bootstrap_ci_reproducible` — fixed seed, assert CI bounds match across runs |
| 7 | `tests/test_compare.py::test_tie_badge_on_overlapping_ci` — synthetic overlapping CIs, assert badge renders |
| 8 | `tests/test_compare.py::test_submeasures_match_manual` — manual computation from logged usage, assert match |
| 9 | `tests/test_recommend.py::test_preset_rankings_deterministic` — synthetic cohort, assert each preset's ranking |
| 10 | `tests/test_irt.py::test_new_tasks_in_discriminating_band` — after B2 eval, assert ≥8 new tasks high-discrimination + b in band |
| 11 | `tests/test_rescore.py::test_rescore_zero_api_calls` — mock proxy, assert zero calls |
| 12 | `tests/test_rescore.py::test_rescore_handles_corrupt_logs` — run against the 44 corrupt files, assert skip report |
| 13 | `tests/test_irt_isolation.py::test_core_without_pymc` — uninstall pymc, assert non-IRT suite passes |

Existing tests must remain green. The rescore and IRT additions are additive; no existing scorer behavior changes (correctness stays pass@1).

---

## Docs to Update

- `bench_cli/compare/` — new columns, CI computation, tie badges; docstrings for the removed weighted default and the `--legacy-weighted` flag.
- `bench_cli/irt/` (new) — IRT engine, fit and item-analysis commands, convergence-failure fallback documentation.
- `bench_cli/recommend/` — preset router logic, preset definitions.
- `scorers/` — docstrings updated to clarify: ratio scorers (`price_ratio.py`, `token_ratio.py`, `time_ratio.py`) remain for per-sample recording but are no longer the aggregation basis for `bench compare`. The display layer reads raw usage from logs.
- `AGENTS.md` (repo) — no change (deliberately minimal; SB is source of truth).
- Second Brain `bench` project — `agent_context` sections updated via `brain-ctl` at session end (decisions, gotchas, current handoff). No staleable numbers in prose.

---

## Notes

- **B4 (honest-reporting branch) was rejected** by the user — the cluster is treated as an artifact to be broken by harder tasks, not accepted as ground truth.
- **The "everything 0-1" instinct is honored where legitimate** (capability stays absolute 0-1; CI bounds are 0-1) and redirected where not (efficiency displayed as raw units + derived decision ratios, not forced into a bounded pillar score).
- **IRT-now carries an acknowledged wide-CI cost.** The PRD does not hide this; F4 is the top UX risk and the expectation-setting in Phase 3 is load-bearing.
