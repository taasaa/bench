# Pipeline Extension Points — IRT, EFA, and Future Psychometric Methods

**Status:** Draft — Phase 3 documentation
**Date:** 2026-04-22

This document describes where future psychometric methods (IRT, EFA) would
plug into the discriminative pipeline when sufficient data becomes available.
The pipeline is designed with explicit extension points — no architectural
changes needed to add these stages.

---

## Current Pipeline (Phases 1-3)

```
Input: eval logs (.eval files)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Stage 0: Subject Resolution                        │
│  resolve_subject_from_log() → SubjectID            │
│  Input: log paths                                   │
│  Output: SubjectID (model / agent / agent+harness)  │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Stage 1: Data Extraction                           │
│  Extract correctness + pillar scores per task      │
│  Input: eval logs                                   │
│  Output: {task_id: score}, pillar_data, metadata    │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Stage 2: Diagnostics                               │
│  run_diagnostics() — difficulty + discrimination   │
│  Input: {subject_id: {task_id: score}}            │
│  Output: DiagnosticReport (ceiling/floor/non-disc) │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Stage 3: Safety Gates                             │
│  run_gates() — non-compensatory correctness gates  │
│  Input: SubjectProfile                             │
│  Output: list[GateResult]                          │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Stage 4: Profile Building                          │
│  build_profile() — cluster scores + CI + verdict  │
│  Input: scores, clusters, pillar_data              │
│  Output: SubjectProfile                            │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Stage 5: Multi-Subject Analysis (Phase 3)         │
│  compare_matrix(), compute_task_correlation()     │
│  Input: list[SubjectProfile]                       │
│  Output: CompareMatrix, list[TaskCorrelation]      │
└─────────────────────────────────────────────────────┘
    │
    ▼
Output: SubjectProfile + DiagnosticReport + Matrix + Correlations
```

---

## Extension Point A: IRT Stage (Item Response Theory)

### When to Add

**Gate:** N >= 50 evaluated models with consistent scoring.

At N=50+, IRT parameter estimation (difficulty b, discrimination a, ability θ)
becomes statistically valid. Below that threshold, the model is entirely
prior-dominated — any IRT output would be noise.

### What It Does

IRT models each task's difficulty and discrimination parameters, then estimates
each model's ability (θ) on a latent scale. This enables:
- Adaptive task selection (most informative task per model)
- Fine-grained ability estimates with proper uncertainty
- Task informativeness ranking for benchmark efficiency

### Where It Inserts

Insert between **Stage 4** and **Stage 5** in the pipeline:

```
Stage 4 output (SubjectProfile)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Stage 4a: IRT Parameter Estimation               │
│  Input: {subject_id: {task_id: score}}, N >= 50   │
│  Output: {task_id: {b: difficulty, a: discrimination}} │
│          {subject_id: θ (ability estimate)}         │
│  Package: IRTorch (PyTorch, v0.5.3+) or mirt      │
└─────────────────────────────────────────────────────┘
    │
    ▼
Stage 5 (compare_matrix, etc.)
```

### Implementation Sketch

```python
# bench_cli/discriminative/irt.py (future)

from dataclasses import dataclass

@dataclass
class IRTResult:
    task_params: dict[str, dict[str, float]]  # {task_id: {b, a}}
    subject_abilities: dict[str, float]       # {subject_id: θ}

def fit_irt_model(
    all_scores: dict[str, dict[str, float]],
    n_subjects: int,
) -> IRTResult:
    """Fit 2PL IRT model using IRTorch or mirt.

    Requires N >= 50 subjects for stable parameter estimates.
    """
    if n_subjects < 50:
        raise ValueError(
            f"IRT requires N >= 50 subjects (got {n_subjects}). "
            "Run more model evaluations before fitting IRT."
        )
    # ... fit model, return results
```

### Key Design Decisions

- **2PL model only** (difficulty + discrimination). 3PL (guessing) adds a third
  parameter that is harder to estimate and not needed for coding tasks.
- **IRTorch (PyTorch)** is the preferred package — actively maintained (v0.5.3,
  Feb 2026), GPU-accelerated for faster fitting.
- **IRT θ is not mixed into existing profiles** — it coexists as a parallel
  ability estimate. The cluster-based profiles remain the primary output.
- **Validate against profiles**: Compare IRT θ estimates to profile cluster
  scores to check convergence. Report any large discrepancies.

---

## Extension Point B: EFA Stage (Exploratory Factor Analysis)

### When to Add

**Gate:** N >= 100 evaluated models.

EFA requires N >> p (subjects >> tasks) to avoid a singular correlation matrix.
At N=8 (current), the correlation matrix has rank at most 8, making factor
analysis mathematically impossible.

### What It Does

EFA discovers empirically-derived capability dimensions from task response patterns,
independent of the manual 4-tier taxonomy. This can reveal:
- Whether the current taxonomy (competence/execution/analysis/universal) matches
  the factor structure
- Hidden dimensions not captured by the manual clusters
- Tasks that load on unexpected factors

### Where It Inserts

Insert between **Stage 2** (Diagnostics) and **Stage 4** (Profile Building):

```
Stage 2 output (DiagnosticReport)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Stage 2a: EFA / Factor Analysis                   │
│  Input: {subject_id: {task_id: score}}, N >= 100  │
│  Output: Factor loadings, suggested cluster updates │
│  Package: sklearn.decomposition.PCA (stdlib)       │
│  Note: PCA on transposed matrix (tasks x subjects)  │
│        is valid at smaller N than full EFA         │
└─────────────────────────────────────────────────────┘
    │
    ▼
Stage 4 (profile building — uses EFA-derived clusters if available)
```

### Implementation Sketch

```python
# bench_cli/discriminative/efa.py (future)

from dataclasses import dataclass

@dataclass
class EFAResult:
    factor_loadings: dict[str, list[float]]  # {task_id: [loading_f1, f2, ...]}
    suggested_clusters: dict[str, list[str]]  # new cluster → task_ids
    explained_variance: list[float]

def run_efa(
    all_scores: dict[str, dict[str, float]],
    n_subjects: int,
) -> EFAResult:
    """Run PCA/EFA on task response patterns.

    Uses PCA on transposed matrix (tasks × subjects) which is valid
    at smaller N than standard EFA on subjects × tasks.
    Requires N >= 100 for stable factor solutions.
    """
    if n_subjects < 100:
        raise ValueError(
            f"EFA requires N >= 100 subjects (got {n_subjects}). "
            "Run more model evaluations before running EFA."
        )
    # ... fit PCA/EFA, return results
```

### Key Design Decisions

- **PCA first**: Run PCA on the transposed matrix (25 tasks × N subjects) which
  has rank at most min(25, N). This provides factor structure insights even at
  smaller N than full EFA requires.
- **Validate with Cronbach's alpha**: Compare EFA-derived clusters against the
  current YAML clusters using Cronbach's alpha. If EFA clusters score higher,
  recommend the switch.
- **YAML override**: EFA suggestions are advisory — the YAML cluster file
  remains the system of record. Users choose whether to adopt EFA recommendations.

---

## Extension Point C: Adaptive Task Selection

### When to Add

**Prerequisite:** IRT model fitted (Stage 4a above, N >= 50).

Adaptive selection uses Fisher Information from the IRT model to pick the most
informative tasks per model. Research shows 90% cost reduction while maintaining
precision.

### What It Does

Instead of running all 36 tasks, select the 10-15 most informative tasks per model
based on each model's estimated ability θ and each task's difficulty/discrimination
parameters.

### Where It Inserts

```
Stage 4a output (IRTResult)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Stage 4b: Adaptive Task Selection                 │
│  Input: IRTResult, current_task_suite             │
│  Output: Ordered list of tasks to run per model   │
└─────────────────────────────────────────────────────┘
    │
    ▼
Stage 4 (profile building — on reduced task set)
```

---

## Extension Point D: Use-Case Recommendation Engine

### When to Add

**Gate:**
1. Profile-based output used for >= 5 real model selection decisions
2. User tracks whether chosen model performed as predicted
3. Prediction accuracy >= 80%

### What It Does

Maps task/cluster profiles to real-world use cases ("code assistant",
"research", "surgical edits") based on validated user feedback, not subjective
expert judgment.

### Key Design Decision

**Defer until validated.** Building a recommendation engine without validation
data creates false authority. The current profile + decision-support output is
honest — the user makes the final decision.

---

## Data Requirements Summary

| Method | Minimum N | Current N | Gap | Status |
|--------|-----------|----------|-----|--------|
| Cluster profiles | 1 | 8 | — | ✅ Done (Phase 1) |
| Safety gates | 1 | 8 | — | ✅ Done (Phase 2) |
| Pareto frontier | 1 | 8 | — | ✅ Done (Phase 2) |
| Task correlation | 2 | 8 | — | ✅ Done (Phase 3) |
| **IRT (2PL)** | **50** | **8** | **42** | 🔒 Gate: N >= 50 |
| **EFA** | **100** | **8** | **92** | 🔒 Gate: N >= 100 |
| **Adaptive selection** | **50** | **8** | **42** | 🔒 Gate: IRT first |
| **Recommendation engine** | **5 validated decisions** | **0** | **5** | 🔒 Gate: user feedback |

---

## No New Dependencies Policy

All extension methods use stdlib or established packages:
- **IRT:** IRTorch (PyTorch) or mirt (Rust-backed) — both installed only when needed
- **EFA:** sklearn.decomposition.PCA — already available in standard Python envs
- **Correlation:** stdlib statistics + math — no external dependencies

No scipy, no statsmodels, no girth package (unmaintained). The pipeline
remains dependency-light until a method is actually warranted by data.
