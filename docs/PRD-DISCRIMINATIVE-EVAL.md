# PRD: Discriminative Bench Evaluation — Decision-Support Architecture

**Status:** complete
**Completed:** 2026-04-22
**Project:** Bench
**Owner:** Michael Mazyar (Rut)
**Scope:** feature (new discriminative module, existing code may be refactored where it improves the system)
**Date:** 2026-04-22
**Tier:** deep

---

## Problem Statement

Bench evaluates subjects (models, agents in harnesses, bare agents) across 36 tasks with 4-pillar scoring, but all 8 evaluated models cluster at 74-79% correctness — a 5-point spread that hides dramatic qualitative differences. Models with near-identical aggregate scores (Nem-30b at 76%, GLM-5-T at 79%) are only r=0.615 correlated, meaning they solve tasks in fundamentally different ways despite appearing identical.

The **primary use case is evaluating harnesses and agents**, not raw models. Model eval is the testing ground — it validates the scoring methodology with known-good data (many models, clear baselines). The real decision the user needs to make is: "Which agent+harness combination should I deploy?" and "Did my harness change improve or regress performance?" The same compression and aggregation problems apply to agents and harnesses — in fact they're worse, because agent eval introduces additional variance from tool use, multi-turn reasoning, and harness configuration.

The user cannot use current output ("Model X scored 77%" or "Claude-local scored 0.65") to decide which combination to deploy, or whether a harness change was an improvement. The arithmetic mean is an information-destroying aggregation that allows strengths to cancel weaknesses, and 20% of tasks contribute literally zero discrimination signal (σ=0.000). This affects ALL subjects — models, agents, and harnesses alike.

---

## First Principles Analysis

### Deconstruction

Bench is a measurement instrument with three layers:

| Layer | Component | Current State | Problem |
|-------|-----------|---------------|---------|
| Stimulus | 36 tasks | 5 zero-discrimination (σ=0), 6 ceiling (p>0.90), 1 floor | 67% of measurement is noise or saturation |
| Transducer | Scorers (verify_sh, llm_judge, hybrid) | Binary (0/1) for verify_sh, continuous for llm_judge | Binary gives ±0.22 CI at n=5 |
| Aggregator | Arithmetic mean | Treats all tasks as equal information | Destroys distributional information |

The real evaluative signal already exists — r=0.615 proves models differ. The instrument just isn't extracting and presenting it. The same pipeline must work for any eval subject: a model, a model+agent combo, a model+agent+harness combo, or the same combo across different configurations.

### Constraint Classification

| Constraint | Type | Evidence | If Removed |
|-----------|------|----------|------------|
| Arithmetic mean destroys information | Hard | Mathematical fact | Must use different aggregation |
| Binary scoring gives wide CIs at n=5 | Hard | Binomial CI at p=0.5, n=5 = ±0.22 | Need more samples or continuous scoring |
| 8 models of historical data | Hard | Cannot retroactively add models | IRT and EFA infeasible at this N |
| Agent eval produces same data shape as model eval | Hard | Inspect captures correctness/tokens/time/cost for all subjects | Pipeline must be subject-type-agnostic |
| 3 agents × 4 modes = up to 12 agent configs per model | Hard | Each combo is a distinct eval subject | Comparisons can be cross-agent, cross-mode, or cross-model |
| 36 authored tasks | Hard | Cannot wish new tasks into existence | Can add/remove but not retroactively |
| 4-pillar scoring | Soft | Design choice | Only correctness has compression; other pillars are fine |
| "competence/execution/analysis/universal" taxonomy | Soft | Organizational heuristic | May not match empirical clusters |
| Single aggregate per subject | Soft | Implementation choice | Multi-dimensional profiles |
| Goal is model ranking | Assumption | Unvalidated | Goal is harness/agent decision-support; models are testing ground |

### Reconstruction — Recommended Architecture

Given only hard constraints, the optimal system is a **pipeline of pure functions** that operates on eval **subjects** — any entity that produces eval logs (model, agent+model, agent+model+harness):

1. **Diagnostic layer**: Task classification (gate/discriminator/ceiling), difficulty and discrimination indices, confidence intervals via Agresti-Coull (not bootstrap)
2. **Profile layer**: Multi-dimensional subject profiles with per-cluster scores, strengths/weaknesses
3. **Decision-support layer**: Profile comparison with explanations and confidence — "what changed when I modified the harness?"
4. **Exploration layer**: Pareto frontier for quality-cost/quality-speed tradeoffs

Each layer is independently testable. No layer requires IRT, EFA, or discrimination weighting (all invalid at N=8). The pipeline is subject-type-agnostic — it doesn't care whether the eval log came from a model, an agent, or a harness.

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
| C4 | `--compare` Mode | Council (Aditi) | Phase 1 | Side-by-side profiles for any two subjects (model-model, agent-agent, agent-model). Primary user workflow. Low incremental cost over single-subject profile. |
| C5 | Subject-type-agnostic pipeline | First Principles (Reconstruction), existing agent eval infrastructure | Phase 1 | `subject.py` — SubjectID dataclass resolves eval log → subject type automatically. Pipeline operates on SubjectProfile, not ModelProfile. Same code path for models, agents, and harnesses. |
| C6 | Harness regression detection | User requirement ("evaluate my harnesses and changes in them decisively") | Phase 2 | `--compare` mode between two runs of same agent+harness config produces per-cluster delta with CI overlap test. "Significant" = non-overlapping 90% CIs. No new statistical methods needed — same Agresti-Coull framework. |

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
| A1 | Tool Call Efficiency as Profile Dimension | IterativeDepth, existing `tool_call_efficiency` scorer | Stable tool call metric across agent runs | Agent evals produce tool call counts (already captured by Inspect). But tool call efficiency is highly variable per task and per agent — no established "good" baseline. Including it in profiles risks comparing agents unfairly (some tasks require many tool calls by design). | Run tool_call_efficiency scorer on ≥10 agent eval runs across ≥3 agents. Establish per-task baseline tool call counts. Then add as optional dimension in agent profiles. |
| A2 | Multi-Turn Reasoning Quality | Research (ICLR 2026 "Reasoning Trap") | Tasks that specifically test multi-turn reasoning quality, not just single-shot correctness | Current tasks are prompt-in, answer-out. Agents that reason well across multiple turns have no way to demonstrate that advantage. No existing tasks measure "how well did the agent recover from a wrong first attempt?" | Design and implement 5+ multi-turn tasks specifically for agent eval (e.g., "attempt task, receive feedback, retry"). These tasks would discriminate between agents that can self-correct vs those that can't. |

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

1. **Decision-support first output** — primary output is profile + strengths/weaknesses + deltas, data underneath as expandable evidence. Works for models, agents, and harnesses alike.
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

1. `bench recommend --model openai/qwen-local` produces multi-dimensional profile output for a model subject — verify by: run command, confirm per-cluster scores appear
2. `bench recommend --agent claude --agent-mode local` produces profile output for an agent subject — verify by: run command with agent eval logs present, confirm same profile format as model
3. Zero-discrimination tasks (σ=0) identified and flagged in output — verify by: check output includes discrimination index per task
4. Per-cluster correctness scores computed using existing tier groupings — verify by: compare cluster scores to manual calculation from inspect stats
5. Agresti-Coull 90% CI computed for each cluster score — verify by: check CI width is narrower than ±0.22 (per-task) for cluster aggregates
6. `--compare` mode shows side-by-side profiles for any two subjects (model vs model, agent vs agent, agent vs model) — verify by: run with known subjects, confirm visually distinct profiles
7. Strength/weakness labels generated per subject (top 2 clusters, bottom 2 clusters) — verify by: validate against known characteristics
8. Cost appears in profile output as cost-per-sample per cluster — verify by: compare to `bench inspect stats` cost data
9. Profile type (model/agent/harness) is identified automatically from eval log metadata — verify by: confirm output shows subject type without explicit flag
10. Existing code refactored where beneficial (not artificially constrained) — verify by: review diff for intentional improvements, not incidental changes
11. Existing 405 tests still pass — verify by: `pytest` returns 405 passed
12. New module has ≥90% test coverage — verify by: `pytest --cov=bench_cli/discriminative`

### Phase 2: Safety + Exploration

13. Safety gate tasks defined in YAML config with configurable thresholds — verify by: edit threshold, re-run, confirm changed behavior
14. Gate evaluation produces pass/fail with specific failed tasks listed — verify by: run on subject with known safety weakness (e.g., Nem-30b on q5)
15. Gate results integrated into profile output (PASS/FAIL per gate) — verify by: confirm gate status appears alongside cluster scores
16. Pareto frontier computed for quality vs cost (paid subjects) and quality-only (free subjects) — verify by: generate frontier, confirm free subjects at cost=$0
17. Pareto frontier timestamped with eval data freshness — verify by: confirm output shows date of eval run
18. Cluster coherence validated with Cronbach's alpha — verify by: check alpha reported per cluster, flag clusters with alpha < 0.5
19. Harness regression detection: `--compare` between two runs of the same agent+harness flags per-cluster deltas with significance — verify by: compare two runs of same config, confirm delta output

### Phase 3: Cross-Dimensional Analysis + Extensibility

20. Cross-subject comparison matrix: agent vs model baseline, harness A vs harness B — verify by: run compare across subject types, confirm matrix output
21. Custom clusters definable in YAML without code changes — verify by: add a custom cluster to YAML, re-run, confirm new cluster appears
22. Task correlation heatmap produced for exploratory analysis — verify by: generate heatmap, confirm task clustering patterns visible
23. Pipeline extension point documented for future psychometric methods — verify by: check docs describe where IRT stage would insert
24. Harness change report: given before/after eval logs, output structured delta report per cluster per pillar — verify by: run on two eval runs with known differences, confirm accurate delta reporting

---

## Edge Cases & Gotchas

- **Free models on Pareto**: All free models tie at cost=$0 — Pareto collapses to quality-only ranking among free models. Separate free vs paid frontiers.
- **Single subject evaluated**: Profile still works (self-assessment). Gates still work. Comparison mode requires 2+ subjects.
- **New subject is statistical outlier**: Profile will show unusual pattern. No misclassification risk because there are no fixed categories to shoehorn into.
- **All subjects pass all gates**: Expected for current model generation. Gates become useful as harder safety tasks are added.
- **Task added/removed between eval runs**: Profiles only include tasks that have data. Coverage gate flags missing tasks.
- **Judge model bias**: llm_judge scores are continuous but subject to GLM-5.1's own biases. Cross-validate with verify_sh where both exist.
- **Pricing changes between runs**: Pareto frontier uses eval-run-date pricing. Cached prices may be stale. Show cache freshness.
- **Binary scoring limits profile granularity**: With n=5, a cluster of 9 tasks gives aggregate CI of ~±0.07 (much better than per-task ±0.22). Aggregation helps.
- **Agent eval variance is higher than model eval**: Agents introduce tool use, multi-turn reasoning, and configuration variance. Same agent+model may produce different scores across runs. CI bars will be wider. This is honest — report it, don't hide it.
- **Cross-subject comparison (model vs agent)**: Not apples-to-apples — agents have tool calls, multi-turn, and different latency profiles. Compare mode must clearly label subject types and note that efficiency/latency/cost dimensions are not directly comparable between models and agents.
- **Harness change with model change**: If both the harness AND the model change between eval runs, the delta is confounded. Harness regression detection requires same model+agent, different harness config only.
- **Agent produces no eval logs**: If agent fails to produce output for a task, that's a zero score. Missing tasks flagged by coverage gate.

---

## Anti-Patterns to Avoid

- **Don't build a recommendation engine** — Bench reports profiles and facts. The USER decides which harness/agent/model to use. False-authority recommendations are worse than no recommendation.
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

**Goal**: Multi-dimensional profiles that work for any eval subject (model, agent+harness, bare agent)

```
bench_cli/discriminative/
├── __init__.py
├── types.py             # DiagnosticReport, SubjectProfile, GateResult, SubjectType
├── pipeline.py          # run_pipeline(), PipelineConfig
├── diagnostics.py       # run_diagnostics() — difficulty + discrimination indices
├── profiles.py          # build_profile() — cluster scores + strengths/weaknesses
├── ci.py                # agresti_coull_ci() for binary confidence intervals
├── filters.py           # discrimination filter (σ < threshold → flag)
├── subject.py           # subject resolution — detect type from eval log, resolve IDs
├── cli.py               # Click CLI: recommend --model/--agent/--agent-mode, --compare
└── config/
    └── clusters.yaml    # cluster → tasks mapping + purpose
```

**Key type: SubjectProfile (not ModelProfile)**
```python
class SubjectType(Enum):
    MODEL = "model"           # bare LLM via generate()
    AGENT = "agent"           # agent+model combo (e.g. claude-local, codex-docker)
    AGENT_HARNESS = "harness" # agent+model+harness (e.g. claude-local with custom CLAUDE.md)

@dataclass
class SubjectID:
    model: str                # e.g. "openai/qwen-local"
    agent: str | None = None  # e.g. "claude"
    agent_mode: str | None = None  # e.g. "local", "bare", "docker", "harness"
    harness_id: str | None = None  # e.g. "custom-claude-md-v2"

    @property
    def subject_type(self) -> SubjectType: ...
    @property
    def display_name(self) -> str: ...  # "qwen-local" or "claude/qwen-local/local" or "claude/qwen-local/harness:v2"
```

**Steps:**
1. Create `bench_cli/discriminative/` package skeleton with types
2. Implement `ci.py` — Agresti-Coull interval computation
3. Implement `subject.py` — resolve eval log → SubjectID (detect agent/mode from eval metadata)
4. Implement `filters.py` — compute σ per task across subjects, flag non-discriminative tasks
5. Implement `diagnostics.py` — per-task difficulty (p-value), discrimination (σ), CI on cluster aggregates
6. Implement `profiles.py` — per-cluster correctness, token ratio, time ratio, cost ratio with CIs
7. Implement `pipeline.py` — wire subject resolution → diagnostics → profiles, load clusters.yaml
8. Implement `cli.py` — `bench recommend --model X`, `bench recommend --agent claude --agent-mode local`, and `--compare` for any subject pair
9. Write tests (target: ≥90% coverage)
10. Run full test suite, verify zero regressions

**Output format (Phase 1) — model subject:**
```
PROFILE: qwen-local (huihui-qwen3.5-35b-a3b) [MODEL]
═════════════════════════════════════════════════════

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

**Output format (Phase 1) — agent subject:**
```
PROFILE: claude / qwen-local / local [AGENT]
═══════════════════════════════════════════════

CLUSTER SCORES (90% CI):
  Competence:   0.91 [0.82-0.96]  █████████░  EXCELLENT
  Execution:    0.85 [0.74-0.93]  █████████░  GOOD
  Analysis:     0.78 [0.65-0.88]  ████████░░  GOOD
  Universal:    0.72 [0.58-0.84]  ███████░░░  FAIR

STRENGTHS:
  ✓ q1-verification-gate (1.00), q3-answer-the-question (1.00)
  ✓ f7-format-compliance (1.00), add-tests (1.00)

WEAKNESSES:
  ✗ f22-error-spiral (0.45)
  ✗ f16-bug-investigation (0.50)

NON-DISCRIMINATIVE TASKS (excluded from cluster scores):
  add-tests (σ=0.000), f7-format-compliance (σ=0.000)

COST: $0.0032/sample
LATENCY: 45.3s avg (0.24× benchmark) — agent uses tool calls, slower but more thorough
TOOL CALLS: 12.3 avg/sample

VERDICT: Agent layer improves competence (+8%) and execution (+6%) over bare model.
Cost increases due to tool use. Error recovery still weak.
```

**Compare mode — harness regression:**
```
COMPARE: claude/qwen-local/local vs claude/qwen-local/local [before → after harness change]
════════════════════════════════════════════════════════════════════════════════

CLUSTER DELTAS:
  Competence:   +0.04  [not significant at 90% CI]
  Execution:    +0.08  [significant ✓]
  Analysis:     -0.02  [not significant at 90% CI]
  Universal:    +0.12  [significant ✓]

HARNESS CHANGE IMPACT:
  ✓ Execution improved: f5-multi-constraint (+0.20), f14-insert-dont-replace (+0.15)
  ✓ Universal improved: f22-error-spiral (+0.25), f26-instruction-hier (+0.10)
  → No regressions detected

COST: $0.0032 → $0.0035/sample (+9%)
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

### Phase 3: Cross-Dimensional Analysis + Extensibility (1 session)

**Goal**: Cross-subject comparison (agent vs model, harness A vs B) + exploratory tools

**Steps:**
1. Add cross-subject comparison matrix — agent vs model baseline, harness A vs harness B, showing per-cluster deltas
2. Add harness change report — structured delta output given before/after eval logs of same config
3. Add task correlation heatmap output (ASCII or matplotlib)
4. Document pipeline extension points for future psychometric methods
5. Update tests

---

## Test Plan

- **Unit tests**: ci.py (Agresti-Coull against known values), filters.py (σ computation), profiles.py (cluster aggregation), gates.py (pass/fail logic), subject.py (SubjectID resolution, type detection)
- **Integration tests**: Full pipeline from eval logs to profile output for model subjects, agent subjects, and mixed compare mode
- **Regression tests**: Existing 405 tests still pass after any refactoring
- **Validation tests**: Profile output matches manual calculation from `bench inspect stats` for known model; agent profile output matches agent eval log data

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

5. **Harness regression significance**: How to determine if a harness change caused a real improvement vs noise? → **Resolution: Compare per-cluster CI overlap.** If 90% CIs don't overlap, the change is significant. If they overlap, report as "not significant." Same Agresti-Coull framework handles this naturally — no additional statistical machinery needed.

6. **Cross-subject comparison fairness**: Is comparing a model (single generate() call) to an agent (multi-turn with tools) meaningful? → **Resolution: Compare within subject-type by default.** Cross-type comparison is allowed but clearly labeled as "model vs agent — different measurement conditions." Cost and latency dimensions are never compared cross-type.

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
- **Gotcha**: Agent eval variance is higher than model eval — same agent+model may score differently across runs due to tool call non-determinism. Report this honestly via CI width.
- **Gotcha**: Cross-subject comparison (model vs agent) is not apples-to-apples for cost and latency — agents use tool calls which inflate both. Label clearly.
- **Idea**: Future: accumulate data across 50+ models, then revisit IRT using `IRTorch` or Python `mirt` package.
- **Idea**: Future: hold out 5-10 secret tasks not in the repo to prevent benchmark gaming.
- **Idea**: Future: multi-turn agent-specific tasks that test self-correction and reasoning recovery.
- **Idea**: The pipeline is subject-type-agnostic by design — when new agent types are added to `bench_cli/agents.py`, the discriminative module picks them up automatically from eval logs. No code changes needed.
- **Idea**: Future: hold out 5-10 secret tasks not in the repo to prevent benchmark gaming.
