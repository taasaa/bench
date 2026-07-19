# Phase 3–4: IRT Engine & Preset Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Load subagent-driven-development/SKILL.md (recommended) or executing-plans/SKILL.md to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `bench irt fit`, `bench irt item-analysis`, and `bench recommend-preset --preset {best,cheap-fast,balanced}` — the IRT discrimination engine and per-use-case routing commands from the scoring redesign spec (Phases 3–4).

**Architecture:** IRT lives in `bench_cli/irt/` with lazy PyMC import. Model identities are reconciled to canonical backing model names via a shared utility in `bench_cli/identity.py`. The outcome matrix builder (`bench_cli/irt/utils.py`) filters monikers via `is_moniker_alias()`, reconciles identities, and maps tasks to pillars via `_load_pillar_map()`. The 2PL model (`bench_cli/irt/fit.py`) fits per-pillar, extracting true posterior credible intervals for θ, a, and b. It falls back to a single general-θ fit if any pillar fit fails to converge. The preset router (`bench_cli/recommend/presets.py`) ranks models by capability (θ if IRT results are available, falling back to pass@1 otherwise) and efficiency columns computed by `_aggregate_model_pillars()`.

**Tech Stack:** Python 3.14, PyMC (optional `[irt]` extra), numpy (transitive via inspect-ai), Click 8, pytest.

## Global Constraints

- Use the project `.venv`: `.venv/bin/python` and `.venv/bin/pytest`. No system python.
- `bench_cli/run/` and `bench_cli/compare/` are packages: `from bench_cli.<name>.core import ...`, NOT `from bench_cli.<name> import ...`.
- Scorers live in `scorers/` at repo root. `bench_cli/scorers/` does NOT exist.
- Models route through a LiteLLM proxy as `openai/<alias>`. `.env` holds credentials.
- The PRD Test Plan locks IRT tests into `tests/test_irt.py` and isolation tests into `tests/test_irt_isolation.py`.
- PyMC is an OPTIONAL dependency. `bench_cli/irt/` uses lazy imports behind `_check_pymc()`. All core commands (run/compare/rescore) MUST work without PyMC installed.
- Moniker aliases (`default`, `thinking`, `heavy`, `background`, `smart-router`) must NEVER enter the IRT model or preset router as respondents. Filter at data acquisition via `bench_cli.results.core.is_moniker_alias`.
- `nan`/`inf` handling: render as `n/a` — never show raw `nan` or `inf` in user-facing output.
- Existing tests must remain green after every task.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `bench_cli/irt/__init__.py` | Package init + `_check_pymc()` lazy guard | Create (Task 1) |
| `bench_cli/irt/types.py` | `OutcomeMatrix`, `IRTFit`, `ItemAnalysis` dataclasses | Create (Task 1) |
| `bench_cli/identity.py` | `reconcile_identities()` — canonical name reconciliation | Create (Task 2) |
| `bench_cli/irt/utils.py` | `build_outcome_matrix()` — log scanning → dense matrix | Create (Task 3) |
| `bench_cli/irt/fit.py` | `fit_2pl()`, `fit_all_pillars()` — PyMC model spec | Create (Task 4) |
| `bench_cli/irt/items.py` | `item_analysis()`, `classify_discrimination()` | Create (Task 5) |
| `bench_cli/irt/cli.py` | `bench irt fit`, `bench irt item-analysis` Click commands | Create (Task 6) |
| `bench_cli/main.py` | Register `irt_group` and `recommend_preset` commands | Modify (Task 6, Task 9) |
| `bench_cli/recommend/__init__.py` | Package init | Create (Task 7) |
| `bench_cli/recommend/presets.py` | `recommend_preset()` — preset logic | Create (Task 7) |
| `bench_cli/recommend/pareto.py` | `compute_pareto_front()` — flat-array Pareto | Create (Task 8) |
| `bench_cli/recommend/cli.py` | `bench recommend-preset` Click command | Create (Task 9) |
| `pyproject.toml` | Add `[irt]` optional dependency | Modify (Task 1) |
| `tests/test_irt.py` | IRT tests (SC4, SC5, SC10, SC13) | Create (Tasks 1–6) |
| `tests/test_irt_isolation.py` | PyMC isolation test (SC13) | Create (Task 6) |
| `tests/test_recommend_preset.py` | Preset router tests (SC9) | Create (Tasks 7–9) |

---

### Task 1: IRT Types + Lazy Import Guard + PyMC Optional Dependency

**Files:**
- Create: `bench_cli/irt/__init__.py`
- Create: `bench_cli/irt/types.py`
- Modify: `pyproject.toml` (add `[irt]` optional dependency)
- Create: `tests/test_irt.py` (initial test)

**Interfaces:**
- Consumes: nothing (foundational)
- Produces:
  - `bench_cli.irt._check_pymc() -> None` (raises `ImportError` with clear message if PyMC not installed)
  - `bench_cli.irt.types.OutcomeMatrix` dataclass:
    - `matrix: list[list[float]]` — shape (n_models, n_tasks), values 0.0–1.0 (pass@1 per sample average)
    - `models: list[str]` — row labels (canonical model names)
    - `tasks: list[str]` — column labels (task names)
    - `pillars: dict[str, str]` — task_name → pillar name
  - `bench_cli.irt.types.IRTFit` dataclass:
    - `theta: list[float]` — posterior mean ability per model (length n_models)
    - `theta_ci: list[tuple[float, float]]` — 95% credible interval per model
    - `a: list[float]` — discrimination per task (length n_tasks)
    - `a_ci: list[tuple[float, float]]` — 95% credible interval per task for discrimination
    - `b: list[float]` — difficulty per task
    - `b_ci: list[tuple[float, float]]` — 95% credible interval per task for difficulty
    - `models: list[str]`
    - `tasks: list[str]`
    - `pillar: str | None`
    - `converged: bool`
    - `n_divergences: int`
  - `bench_cli.irt.types.ItemAnalysis` dataclass:
    - `task: str`, `pillar: str`, `a: float`, `a_ci: tuple[float, float]`, `b: float`, `b_ci: tuple[float, float]`, `band: str`

- [ ] **Step 1: Write the failing test for the lazy import guard**

Append to a new `tests/test_irt.py`:

```python
"""Tests for the IRT engine (SC4, SC5, SC10, SC13)."""

from __future__ import annotations

import pytest


def test_check_pymc_raises_when_missing(monkeypatch):
    """SC13 partial: _check_pymc() raises ImportError with install hint."""
    import builtins
    real_import = builtins.__import__

    def _block_pymc(name, *args, **kwargs):
        if name == "pymc" or name.startswith("pymc."):
            raise ImportError("no pymc")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_pymc)
    # Force reimport
    import importlib
    import bench_cli.irt
    importlib.reload(bench_cli.irt)
    with pytest.raises(ImportError, match="PyMC is required"):
        bench_cli.irt._check_pymc()


def test_outcome_matrix_dataclass():
    """OutcomeMatrix holds the expected fields."""
    from bench_cli.irt.types import OutcomeMatrix

    om = OutcomeMatrix(
        matrix=[[1.0, 0.0], [0.5, 0.5]],
        models=["model-a", "model-b"],
        tasks=["task-1", "task-2"],
        pillars={"task-1": "analysis", "task-2": "execution"},
    )
    assert len(om.models) == 2
    assert len(om.tasks) == 2
    assert om.matrix[0][1] == 0.0


def test_irt_fit_dataclass():
    """IRTFit holds posterior estimates."""
    from bench_cli.irt.types import IRTFit

    fit = IRTFit(
        theta=[0.5, -0.3],
        theta_ci=[(0.1, 0.9), (-0.7, 0.1)],
        a=[1.2, 0.8],
        a_ci=[(0.8, 1.6), (0.4, 1.2)],
        b=[-0.5, 0.3],
        b_ci=[(-1.0, 0.0), (-0.2, 0.8)],
        models=["m1", "m2"],
        tasks=["t1", "t2"],
        pillar=None,
        converged=True,
        n_divergences=0,
    )
    assert fit.converged
    assert len(fit.theta) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_irt.py -v`
Expected: FAIL (modules don't exist yet)

- [ ] **Step 3: Create the package init with lazy guard**

Create `bench_cli/irt/__init__.py`:

```python
"""IRT discrimination engine — optional PyMC dependency.

All PyMC imports are lazy. Core bench commands (run/compare/rescore) work
without PyMC installed. Only ``bench irt *`` commands require it.
"""

from __future__ import annotations


def _check_pymc() -> None:
    """Raise ``ImportError`` with install instructions if PyMC is missing."""
    try:
        import pymc  # noqa: F401
    except ImportError:
        raise ImportError(
            "PyMC is required for IRT analysis. "
            "Install with: pip install 'bench[irt]'"
        ) from None
```

- [ ] **Step 4: Create the types module**

Create `bench_cli/irt/types.py`:

```python
"""Dataclasses for IRT results — no PyMC dependency."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OutcomeMatrix:
    """Binary outcome matrix for IRT fitting.

    Rows = models (respondents), columns = tasks (items).
    Values = per-(model, task) pass@1 rate (0.0–1.0).
    """

    matrix: list[list[float]]  # shape (n_models, n_tasks)
    models: list[str]          # row labels
    tasks: list[str]           # column labels
    pillars: dict[str, str] = field(default_factory=dict)  # task -> pillar


@dataclass
class IRTFit:
    """Posterior estimates from a fitted 2PL IRT model."""

    theta: list[float]                    # posterior mean ability per model
    theta_ci: list[tuple[float, float]]   # 95% credible interval per model
    a: list[float]                        # discrimination per task
    a_ci: list[tuple[float, float]]       # 95% credible interval per task for a
    b: list[float]                        # difficulty per task
    b_ci: list[tuple[float, float]]       # 95% credible interval per task for b
    models: list[str]
    tasks: list[str]
    pillar: str | None                    # None = general (all tasks)
    converged: bool                       # False if Rhat > 1.1 for any param
    n_divergences: int


@dataclass
class ItemAnalysis:
    """Per-task IRT item parameters + discrimination classification."""

    task: str
    pillar: str
    a: float                          # discrimination (posterior mean)
    a_ci: tuple[float, float]         # 95% CI on a
    b: float                          # difficulty (posterior mean)
    b_ci: tuple[float, float]         # 95% CI on b
    band: str                         # "high", "medium", "low", "cull"
```

- [ ] **Step 5: Add `[irt]` optional dependency to pyproject.toml**

In `pyproject.toml`, add to the `[project.optional-dependencies]` section:

```toml
irt = [
    "pymc>=5.10",
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_irt.py -v`
Expected: 4 PASS

- [ ] **Step 7: Commit**

```bash
git add bench_cli/irt/__init__.py bench_cli/irt/types.py tests/test_irt.py pyproject.toml
git commit -m "feat(irt): types + lazy PyMC guard + optional dependency (Phase 3 Task 1)"
```

---

### Task 2: Recorded Identity Reconciliation Utility

**Files:**
- Create: `bench_cli/identity.py`
- Modify: `tests/test_irt.py` (append test)

**Interfaces:**
- Consumes:
  - `bench_cli.run.core.resolve_recorded_name(routed_name: str, as_name: str | None) -> str`
- Produces:
  - `bench_cli.identity.reconcile_identities(log_dir: str, models: list[str] | None = None) -> dict[str, str]`
    - Maps observed/recorded model names to their canonical backing model names. Accepts an optional list of models to avoid redundant log directory scanning.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_irt.py`:

```python
def test_reconcile_identities_basic():
    """Reconcile identities maps aliases to canonical names."""
    from bench_cli.identity import reconcile_identities
    from unittest.mock import patch

    def _mock_resolve(routed, as_name):
        if routed == "openai/thinking":
            return "openai/claude-3-5-sonnet"
        return routed

    with patch("bench_cli.identity.resolve_recorded_name", side_effect=_mock_resolve):
        # When model list is passed, it should reconcile instantly without file scan
        res = reconcile_identities("dummy_dir", models=["openai/thinking", "openai/default"])
        assert res["openai/thinking"] == "openai/claude-3-5-sonnet"
        assert res["openai/default"] == "openai/default"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_irt.py -k "reconcile_identities" -v`
Expected: FAIL (identity module doesn't exist)

- [ ] **Step 3: Implement identity reconciliation**

Create `bench_cli/identity.py`:

```python
"""Canonical identity reconciliation for models.

Resolves raw model names found in logs to their backing canonical identities
using the litellm config mapping. Helps merge duplicate or routed aliases.
"""

from __future__ import annotations

from pathlib import Path
from inspect_ai.log import list_eval_logs, read_eval_log
from bench_cli.run.core import resolve_recorded_name


def reconcile_identities(log_dir: str, models: list[str] | None = None) -> dict[str, str]:
    """Scan log directory or use provided model list and map raw names to canonical backing names.

    Returns:
        dict of raw_model_name -> canonical_model_name.
    """
    if models is not None:
        unique_names = set(models)
    else:
        log_path = Path(log_dir)
        if not log_path.is_dir():
            return {}

        unique_names = set()
        infos = list_eval_logs(log_dir=str(log_path))
        for info in infos:
            try:
                el = read_eval_log(info, header_only=True)
                if el.eval and el.eval.model:
                    unique_names.add(el.eval.model)
            except Exception:
                continue

    mapping: dict[str, str] = {}
    for name in unique_names:
        canonical = resolve_recorded_name(name, None)
        mapping[name] = canonical

    return mapping
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_irt.py -k "reconcile_identities" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bench_cli/identity.py tests/test_irt.py
git commit -m "feat(identity): add recorded identity reconciliation utility (Phase 3 Task 2)"
```

---

### Task 3: Outcome Matrix Builder with Identity Reconciliation

**Files:**
- Create: `bench_cli/irt/utils.py`
- Modify: `tests/test_irt.py` (append tests)

**Interfaces:**
- Consumes:
  - `bench_cli.compare.core.load_compare_data(log_dir: str) -> CompareData`
  - `bench_cli.results.core.is_moniker_alias(bench_alias: str) -> bool`
  - `bench_cli.results.core._build_pillar_map() -> dict[str, str]`
  - `bench_cli.identity.reconcile_identities(log_dir: str, models: list[str]) -> dict[str, str]`
  - `bench_cli.irt.types.OutcomeMatrix`
- Produces:
  - `bench_cli.irt.utils.build_outcome_matrix(log_dir: str, *, filter_monikers: bool = True) -> OutcomeMatrix`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_irt.py`:

```python
from unittest.mock import patch
from bench_cli.compare.core import CompareData, PillarScores


def _make_compare_data(
    models: list[str],
    tasks: list[str],
    scores: dict[tuple[str, str], float],
) -> CompareData:
    """Helper: build CompareData from a sparse (task, model) -> correctness map."""
    matrix: dict[str, dict[str, PillarScores]] = {}
    for task in tasks:
        matrix[task] = {}
        for model in models:
            if (task, model) in scores:
                matrix[task][model] = PillarScores(
                    correctness=scores[(task, model)],
                    token_ratio=1.0,
                    time_ratio=1.0,
                    avg_tokens=100,
                    avg_time=1.0,
                    samples=1,
                )
    return CompareData(matrix=matrix, tasks=tasks, models=models)


def test_build_outcome_matrix_basic():
    """OutcomeMatrix has correct shape and values from CompareData."""
    from bench_cli.irt.utils import build_outcome_matrix

    data = _make_compare_data(
        models=["m1", "m2"],
        tasks=["t1", "t2"],
        scores={("t1", "m1"): 1.0, ("t1", "m2"): 0.0,
                ("t2", "m1"): 0.5, ("t2", "m2"): 0.75},
    )
    with patch("bench_cli.irt.utils.load_compare_data", return_value=data),          patch("bench_cli.irt.utils.reconcile_identities", return_value={"m1": "m1", "m2": "m2"}),          patch("bench_cli.irt.utils._get_pillar_map", return_value={"t1": "analysis", "t2": "execution"}):
        om = build_outcome_matrix("logs")

    assert om.models == ["m1", "m2"]
    assert om.tasks == ["t1", "t2"]
    assert om.matrix[0] == [1.0, 0.5]
    assert om.matrix[1] == [0.0, 0.75]
    assert om.pillars["t1"] == "analysis"


def test_build_outcome_matrix_reconciles_identities():
    """Different recorded names mapping to the same canonical backing name are merged."""
    from bench_cli.irt.utils import build_outcome_matrix

    data = _make_compare_data(
        models=["m1_alias", "m1_canonical"],
        tasks=["t1"],
        scores={("t1", "m1_alias"): 1.0, ("t1", "m1_canonical"): 0.8},
    )
    identity_map = {"m1_alias": "m1_canonical", "m1_canonical": "m1_canonical"}

    with patch("bench_cli.irt.utils.load_compare_data", return_value=data),          patch("bench_cli.irt.utils.reconcile_identities", return_value=identity_map),          patch("bench_cli.irt.utils._get_pillar_map", return_value={"t1": "analysis"}):
        om = build_outcome_matrix("logs")

    assert om.models == ["m1_canonical"]
    assert om.matrix[0] == [0.9]


def test_build_outcome_matrix_filters_monikers():
    """Moniker aliases (default, thinking, heavy) are excluded."""
    from bench_cli.irt.utils import build_outcome_matrix

    data = _make_compare_data(
        models=["m1", "default", "thinking"],
        tasks=["t1"],
        scores={("t1", "m1"): 0.8, ("t1", "default"): 0.7, ("t1", "thinking"): 0.6},
    )
    with patch("bench_cli.irt.utils.load_compare_data", return_value=data),          patch("bench_cli.irt.utils.reconcile_identities", return_value={"m1": "m1", "default": "default", "thinking": "thinking"}),          patch("bench_cli.irt.utils._get_pillar_map", return_value={"t1": "analysis"}):
        om = build_outcome_matrix("logs", filter_monikers=True)

    assert om.models == ["m1"]
    assert len(om.matrix) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_irt.py::test_build_outcome_matrix_reconciles_identities -v`
Expected: FAIL (matrix utils not implemented)

- [ ] **Step 3: Implement outcome matrix builder**

Create `bench_cli/irt/utils.py`:

```python
"""Outcome matrix construction from eval logs for IRT fitting."""

from __future__ import annotations

import math

from bench_cli.compare.core import CompareData, load_compare_data
from bench_cli.identity import reconcile_identities
from bench_cli.irt.types import OutcomeMatrix
from bench_cli.results.core import is_moniker_alias


def _get_pillar_map() -> dict[str, str]:
    """Return task_name -> pillar mapping from the tasks/ directory."""
    from bench_cli.inspect.core import _load_pillar_map

    return _load_pillar_map()


def build_outcome_matrix(
    log_dir: str,
    *,
    filter_monikers: bool = True,
) -> OutcomeMatrix:
    """Build the outcome matrix for IRT fitting from eval logs.

    Rows = models (respondents), columns = tasks (items).
    Values = per-(model, task) mean correctness (0.0–1.0).
    """
    data = load_compare_data(log_dir)
    # Pass pre-loaded models to avoid redundant folder scanning
    identity_map = reconcile_identities(log_dir, models=data.models)

    canonical_models_set: set[str] = set()
    for m in data.models:
        canonical = identity_map.get(m, m)
        if not (filter_monikers and is_moniker_alias(canonical)):
            canonical_models_set.add(canonical)

    models = sorted(list(canonical_models_set))
    tasks = data.tasks

    scores_by_pair: dict[str, dict[str, list[float]]] = {t: {} for t in tasks}

    for task in tasks:
        for raw_model in data.models:
            ps = data.matrix.get(task, {}).get(raw_model)
            if ps is not None and not math.isnan(ps.correctness):
                canonical = identity_map.get(raw_model, raw_model)
                if canonical in canonical_models_set:
                    scores_by_pair[task].setdefault(canonical, []).append(ps.correctness)

    matrix: list[list[float]] = []
    for model in models:
        row: list[float] = []
        for task in tasks:
            vals = scores_by_pair[task].get(model)
            if vals:
                row.append(sum(vals) / len(vals))
            else:
                row.append(float("nan"))
        matrix.append(row)

    pillars = _get_pillar_map()

    return OutcomeMatrix(
        matrix=matrix,
        models=models,
        tasks=tasks,
        pillars=pillars,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_irt.py -k "outcome_matrix" -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add bench_cli/irt/utils.py tests/test_irt.py
git commit -m "feat(irt): outcome matrix with identity reconciliation (Phase 3 Task 3)"
```

---

### Task 4: 2PL Model Fitting + Credible Intervals + Convergence Fallback

**Files:**
- Create: `bench_cli/irt/fit.py`
- Modify: `tests/test_irt.py` (append tests)

**Interfaces:**
- Consumes:
  - `bench_cli.irt.types.OutcomeMatrix`
  - `bench_cli.irt.types.IRTFit`
- Produces:
  - `bench_cli.irt.fit.fit_2pl(outcome: OutcomeMatrix, ...) -> IRTFit`
  - `bench_cli.irt.fit.fit_all_pillars(outcome: OutcomeMatrix, **kwargs) -> dict[str, IRTFit | None]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_irt.py`:

```python
import random

def _generate_synthetic_2pl(
    n_models: int = 20,
    n_tasks: int = 30,
    seed: int = 42,
) -> tuple[list[list[float]], list[float], list[float], list[float]]:
    rng = random.Random(seed)
    true_theta = [rng.gauss(0, 1) for _ in range(n_models)]
    true_a = [abs(rng.gauss(1.0, 0.3)) for _ in range(n_tasks)]
    true_b = [rng.gauss(0, 1.5) for _ in range(n_tasks)]

    def sigmoid(x: float) -> float:
        import math
        return 1.0 / (1.0 + math.exp(-x))

    matrix: list[list[float]] = []
    for i in range(n_models):
        row: list[float] = []
        for j in range(n_tasks):
            p = sigmoid(true_a[j] * (true_theta[i] - true_b[j]))
            row.append(1.0 if rng.random() < p else 0.0)
        matrix.append(row)
    return matrix, true_theta, true_a, true_b


@pytest.mark.slow
def test_2pl_recovers_credible_intervals():
    """SC4: 2PL calculates credible intervals for theta, a, and b."""
    pytest.importorskip("pymc")
    from bench_cli.irt.fit import fit_2pl
    from bench_cli.irt.types import OutcomeMatrix

    matrix, _, _, _ = _generate_synthetic_2pl(n_models=10, n_tasks=10, seed=42)
    tasks = [f"t{i}" for i in range(10)]
    models = [f"m{i}" for i in range(10)]
    outcome = OutcomeMatrix(matrix=matrix, models=models, tasks=tasks, pillars={t: "analysis" for t in tasks})

    fit = fit_2pl(outcome, n_samples=1000, n_chains=2, seed=42)

    assert len(fit.a_ci) == 10
    assert len(fit.b_ci) == 10
    assert all(ci[0] < ci[1] for ci in fit.a_ci)
    assert all(ci[0] < ci[1] for ci in fit.b_ci)


@pytest.mark.slow
def test_fit_all_pillars_convergence_fallback():
    """Pillar fit non-convergence falls back to general fit."""
    pytest.importorskip("pymc")
    from bench_cli.irt.fit import fit_all_pillars
    from bench_cli.irt.types import OutcomeMatrix
    from unittest.mock import patch

    tasks = [f"e{i}" for i in range(10)]
    matrix, _, _, _ = _generate_synthetic_2pl(n_models=5, n_tasks=10, seed=99)
    models = [f"m{i}" for i in range(5)]
    outcome = OutcomeMatrix(matrix=matrix, models=models, tasks=tasks, pillars={t: "execution" for t in tasks})

    with patch("bench_cli.irt.fit.fit_2pl") as mock_fit:
        from bench_cli.irt.types import IRTFit
        bad_fit = IRTFit(
            theta=[0.0]*5, theta_ci=[(0,0)]*5, a=[1.0]*10, a_ci=[(0,0)]*10,
            b=[0.0]*10, b_ci=[(0,0)]*10, models=models, tasks=tasks,
            pillar="execution", converged=False, n_divergences=0
        )
        good_general = IRTFit(
            theta=[0.1]*5, theta_ci=[(0,0)]*5, a=[1.1]*10, a_ci=[(0,0)]*10,
            b=[0.1]*10, b_ci=[(0,0)]*10, models=models, tasks=tasks,
            pillar="general_fallback", converged=True, n_divergences=0
        )
        mock_fit.side_effect = [bad_fit, good_general]

        fits = fit_all_pillars(outcome, n_samples=1000, n_chains=2, seed=99)

        assert fits["execution"] is None
        assert fits["general_fallback"] is not None
        assert fits["general_fallback"].pillar == "general_fallback"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_irt.py -k "credible_intervals or convergence_fallback" -v`
Expected: FAIL

- [ ] **Step 3: Implement the 2PL fitter**

Create `bench_cli/irt/fit.py`:

```python
"""Bayesian 2PL IRT model fitting via PyMC."""

from __future__ import annotations

import math

from bench_cli.irt import _check_pymc
from bench_cli.irt.types import IRTFit, OutcomeMatrix


def fit_2pl(
    outcome: OutcomeMatrix,
    *,
    pillar: str | None = None,
    n_samples: int = 2000,
    n_chains: int = 2,
    seed: int = 42,
) -> IRTFit:
    """Fit a Bayesian 2PL IRT model.

    Extracts true posterior credible intervals for parameters theta, a, and b.
    """
    _check_pymc()
    import numpy as np
    import pymc as pm

    if pillar is not None and pillar != "general_fallback":
        task_indices = [
            j for j, t in enumerate(outcome.tasks)
            if outcome.pillars.get(t) == pillar
        ]
        tasks = [outcome.tasks[j] for j in task_indices]
        data = np.array([[outcome.matrix[i][j] for j in task_indices]
                         for i in range(len(outcome.models))])
    else:
        tasks = outcome.tasks
        data = np.array(outcome.matrix)

    n_models, n_tasks = data.shape

    # Flatten to 1D observed indices to support missing data in PyMC 5.x naturally
    model_indices = []
    task_indices_1d = []
    observed_y = []
    for i in range(n_models):
        for j in range(n_tasks):
            val = data[i, j]
            if not np.isnan(val):
                model_indices.append(i)
                task_indices_1d.append(j)
                observed_y.append(val)

    with pm.Model() as model:
        theta = pm.Normal("theta", mu=0, sigma=1, shape=n_models)
        a = pm.LogNormal("a", mu=0, sigma=0.5, shape=n_tasks)
        b = pm.Normal("b", mu=0, sigma=2, shape=n_tasks)

        # Logit: a_j * (theta_i - b_j) using 1D indexing arrays
        logit_p = a[task_indices_1d] * (theta[model_indices] - b[task_indices_1d])
        pm.Bernoulli(
            "y_obs",
            logit_p=logit_p,
            observed=observed_y,
        )

        trace = pm.sample(
            draws=n_samples,
            chains=n_chains,
            random_seed=seed,
            progressbar=False,
            return_inferencedata=True,
        )

    theta_post = trace.posterior["theta"].values.reshape(-1, n_models)
    a_post = trace.posterior["a"].values.reshape(-1, n_tasks)
    b_post = trace.posterior["b"].values.reshape(-1, n_tasks)

    theta_mean = theta_post.mean(axis=0).tolist()
    a_mean = a_post.mean(axis=0).tolist()
    b_mean = b_post.mean(axis=0).tolist()

    theta_ci = [
        (float(np.percentile(theta_post[:, i], 2.5)),
         float(np.percentile(theta_post[:, i], 97.5)))
        for i in range(n_models)
    ]
    a_ci = [
        (float(np.percentile(a_post[:, j], 2.5)),
         float(np.percentile(a_post[:, j], 97.5)))
        for j in range(n_tasks)
    ]
    b_ci = [
        (float(np.percentile(b_post[:, j], 2.5)),
         float(np.percentile(b_post[:, j], 97.5)))
        for j in range(n_tasks)
    ]

    rhat = pm.stats.rhat(trace)
    max_rhat = max(
        float(rhat["theta"].max()),
        float(rhat["a"].max()),
        float(rhat["b"].max()),
    )
    converged = max_rhat <= 1.1
    n_divergences = int(trace.sample_stats["diverging"].sum())

    return IRTFit(
        theta=theta_mean,
        theta_ci=theta_ci,
        a=a_mean,
        a_ci=a_ci,
        b=b_mean,
        b_ci=b_ci,
        models=outcome.models,
        tasks=tasks,
        pillar=pillar,
        converged=converged,
        n_divergences=n_divergences,
    )


_MIN_PILLAR_TASKS = 8


def fit_all_pillars(
    outcome: OutcomeMatrix,
    **kwargs,
) -> dict[str, IRTFit | None]:
    """Fit 2PL per pillar. Skip pillars with < 8 tasks.

    If any pillar fit fails to converge (converged=False), fall back to
    fitting a single general θ on all tasks.
    """
    all_pillars = sorted({p for p in outcome.pillars.values()})
    fits: dict[str, IRTFit | None] = {}
    any_convergence_failed = False

    for pillar in all_pillars:
        pillar_task_count = sum(
            1 for t in outcome.tasks if outcome.pillars.get(t) == pillar
        )
        if pillar_task_count < _MIN_PILLAR_TASKS:
            fits[pillar] = None
            continue
        fit = fit_2pl(outcome, pillar=pillar, **kwargs)
        if not fit.converged:
            any_convergence_failed = True
            fits[pillar] = None
        else:
            fits[pillar] = fit

    if any_convergence_failed:
        fits["general_fallback"] = fit_2pl(outcome, pillar="general_fallback", **kwargs)

    return fits
```

- [ ] **Step 4: Run the recovery test**

Run: `.venv/bin/pytest tests/test_irt.py::test_2pl_recovers_synthetic_params -v -s`
Expected: PASS

- [ ] **Step 5: Run the all-pillars test**

Run: `.venv/bin/pytest tests/test_irt.py::test_fit_all_pillars_skips_small -v -s`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add bench_cli/irt/fit.py tests/test_irt.py
git commit -m "feat(irt): Bayesian 2PL model fitting with per-pillar support (Phase 3 Task 4)"
```

---

### Task 5: Item Analysis using Posterior Credible Intervals

**Files:**
- Modify: `bench_cli/irt/items.py`
- Modify: `tests/test_irt.py` (append tests)

**Interfaces:**
- Consumes:
  - `bench_cli.irt.types.IRTFit`
  - `bench_cli.irt.types.ItemAnalysis`
- Produces:
  - `bench_cli.irt.items.item_analysis(fit: IRTFit) -> list[ItemAnalysis]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_irt.py`:

```python
def test_item_analysis_extracts_ci():
    """Item analysis maps estimated a_ci and b_ci from IRTFit."""
    from bench_cli.irt.items import item_analysis
    from bench_cli.irt.types import IRTFit

    fit = IRTFit(
        theta=[0.0], theta_ci=[(-0.1, 0.1)],
        a=[1.5], a_ci=[(1.2, 1.8)],
        b=[0.5], b_ci=[(0.2, 0.8)],
        models=["m1"], tasks=["t1"],
        pillar=None, converged=True, n_divergences=0
    )
    items = item_analysis(fit)
    assert items[0].a_ci == (1.2, 1.8)
    assert items[0].b_ci == (0.2, 0.8)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_irt.py -k "item_analysis_extracts_ci" -v`
Expected: FAIL

- [ ] **Step 3: Implement item analysis CI mapping**

Create `bench_cli/irt/items.py`:

```python
"""IRT item analysis — difficulty, discrimination, and classification."""

from __future__ import annotations

from bench_cli.irt.types import IRTFit, ItemAnalysis


def classify_discrimination(
    a: float,
    *,
    high_threshold: float = 1.0,
    medium_threshold: float = 0.5,
    low_threshold: float = 0.2,
) -> str:
    """Classify discrimination parameter into bands."""
    if a >= high_threshold:
        return "high"
    if a >= medium_threshold:
        return "medium"
    if a >= low_threshold:
        return "low"
    return "cull"


def item_analysis(fit: IRTFit) -> list[ItemAnalysis]:
    """Extract per-task item parameters + credible intervals from a fitted IRT model."""
    items: list[ItemAnalysis] = []
    pillar_label = fit.pillar or "general"

    for j, task in enumerate(fit.tasks):
        a_val = fit.a[j]
        b_val = fit.b[j]
        a_ci_val = fit.a_ci[j]
        b_ci_val = fit.b_ci[j]

        items.append(ItemAnalysis(
            task=task,
            pillar=pillar_label,
            a=a_val,
            a_ci=a_ci_val,
            b=b_val,
            b_ci=b_ci_val,
            band=classify_discrimination(a_val),
        ))

    return items


def in_discriminating_band(
    b: float,
    mean_theta: float,
    tolerance: float = 0.5,
) -> bool:
    """Check if task difficulty is in the discriminating band."""
    return abs(b - mean_theta) <= tolerance
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_irt.py -k "item_analysis_extracts_ci" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bench_cli/irt/items.py tests/test_irt.py
git commit -m "feat(irt): map true posterior CIs in item analysis (Phase 3 Task 5)"
```

---

### Task 6: IRT CLI Commands + Registration + General Fallback Warning

**Files:**
- Create: `bench_cli/irt/cli.py`
- Modify: `bench_cli/main.py` (import + register `irt_group`)
- Create: `tests/test_irt_isolation.py`
- Modify: `tests/test_irt.py` (append CLI test)

**Interfaces:**
- Consumes:
  - `bench_cli.irt.utils.build_outcome_matrix(log_dir) -> OutcomeMatrix`
  - `bench_cli.irt.fit.fit_all_pillars(outcome, ...) -> dict`
- Produces:
  - `bench irt fit` / `bench irt item-analysis` commands

- [ ] **Step 1: Write the failing tests**

Ensure `tests/test_irt.py` has the CLI error tests from Task 5 in the original plan.

- [ ] **Step 2: Run tests to verify they fail**

Run tests and check that CLI commands are missing.

- [ ] **Step 3: Implement CLI commands with fallback logging**

Create `bench_cli/irt/cli.py`:

```python
"""CLI commands for IRT discrimination analysis."""

from __future__ import annotations

import json
import click


@click.group("irt")
def irt_group():
    """IRT discrimination analysis (requires PyMC)."""
    pass


@irt_group.command("fit")
@click.option("--log-dir", default="logs", help="Directory containing .eval logs.")
@click.option("--pillar", default=None, help="Fit single pillar (default: all).")
@click.option("--n-samples", default=2000, type=int, help="MCMC draw count.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def irt_fit(log_dir: str, pillar: str | None, n_samples: int, as_json: bool) -> None:
    """Fit Bayesian 2PL IRT model on eval logs."""
    from bench_cli.irt import _check_pymc
    _check_pymc()

    from bench_cli.irt.fit import fit_2pl, fit_all_pillars
    from bench_cli.irt.utils import build_outcome_matrix

    outcome = build_outcome_matrix(log_dir)
    if not outcome.models:
        click.echo("No model data found in logs.")
        return

    if pillar is not None:
        fits = {pillar: fit_2pl(outcome, pillar=pillar, n_samples=n_samples)}
    else:
        fits = fit_all_pillars(outcome, n_samples=n_samples)
        if "general_fallback" in fits:
            click.echo("WARNING: Convergence failure detected in pillar fitting (Rhat > 1.1).")
            click.echo("Falling back to fitting a single general θ model across all tasks.")
        else:
            fits["general"] = fit_2pl(outcome, n_samples=n_samples)

    if as_json:
        out: dict = {}
        for p, fit in fits.items():
            if fit is None:
                continue
            out[p] = {
                "converged": fit.converged,
                "n_divergences": fit.n_divergences,
                "models": [
                    {"name": m, "theta": fit.theta[i],
                     "ci_low": fit.theta_ci[i][0], "ci_high": fit.theta_ci[i][1]}
                    for i, m in enumerate(fit.models)
                ],
            }
        click.echo(json.dumps(out, indent=2))
    else:
        for p, fit in fits.items():
            if fit is None:
                continue
            click.echo(f"\n{'=' * 60}")
            click.echo(f"Pillar: {p}")
            click.echo(f"{'=' * 60}")
            click.echo(f"  Converged: {fit.converged}  Divergences: {fit.n_divergences}")
            click.echo(f"  {'Model':<35} {'θ':>8} {'95% CI':>18}")
            click.echo(f"  {'-' * 35} {'-' * 8} {'-' * 18}")
            ranked = sorted(range(len(fit.models)), key=lambda i: fit.theta[i], reverse=True)
            for i in ranked:
                m = fit.models[i]
                t = fit.theta[i]
                lo, hi = fit.theta_ci[i]
                click.echo(f"  {m:<35} {t:>8.3f} [{lo:>7.3f}, {hi:>7.3f}]")


@irt_group.command("item-analysis")
@click.option("--log-dir", default="logs", help="Directory containing .eval logs.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def irt_item_analysis(log_dir: str, as_json: bool) -> None:
    """Report per-task difficulty and discrimination parameters."""
    from bench_cli.irt import _check_pymc
    _check_pymc()

    from bench_cli.irt.fit import fit_2pl
    from bench_cli.irt.items import item_analysis
    from bench_cli.irt.utils import build_outcome_matrix

    outcome = build_outcome_matrix(log_dir)
    if not outcome.models:
        click.echo("No model data found in logs.")
        return

    fit = fit_2pl(outcome)
    items = item_analysis(fit)

    if as_json:
        out = [
            {"task": ia.task, "pillar": ia.pillar,
             "a": ia.a, "a_ci_low": ia.a_ci[0], "a_ci_high": ia.a_ci[1],
             "b": ia.b, "b_ci_low": ia.b_ci[0], "b_ci_high": ia.b_ci[1],
             "band": ia.band}
            for ia in items
        ]
        click.echo(json.dumps(out, indent=2))
    else:
        click.echo(f"\n{'Task':<35} {'Pillar':<12} {'a (disc)':>10} {'b (diff)':>10} {'Band':<8}")
        click.echo(f"{'-' * 35} {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 8}")
        for ia in sorted(items, key=lambda x: x.a, reverse=True):
            click.echo(
                f"{ia.task:<35} {ia.pillar:<12} {ia.a:>10.3f} {ia.b:>10.3f} {ia.band:<8}"
            )

        high = sum(1 for ia in items if ia.band == "high")
        med = sum(1 for ia in items if ia.band == "medium")
        low = sum(1 for ia in items if ia.band == "low")
        cull = sum(1 for ia in items if ia.band == "cull")
        click.echo(f"\nSummary: {high} high, {med} medium, {low} low, {cull} cull")
```

- [ ] **Step 4: Register in main.py**

In `bench_cli/main.py`:

```python
from bench_cli.irt.cli import irt_group
cli.add_command(irt_group)
```

- [ ] **Step 5: Create tests/test_irt_isolation.py**

Create `tests/test_irt_isolation.py` to verify PyMC is not eagerly imported when other bench commands run (SC13):

```python
"""SC13: Core bench commands work without PyMC installed."""

from __future__ import annotations

from click.testing import CliRunner


def test_compare_works_without_pymc(monkeypatch, tmp_path):
    """bench compare runs fine even if pymc is not importable."""
    import builtins
    real_import = builtins.__import__

    def _block_pymc(name, *args, **kwargs):
        if name == "pymc" or name.startswith("pymc."):
            raise ImportError("no pymc in this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_pymc)

    from bench_cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["compare", "--log-dir", str(tmp_path)])
    assert result.exit_code == 0
```

- [ ] **Step 6: Commit**

```bash
git add bench_cli/irt/cli.py bench_cli/main.py tests/test_irt_isolation.py tests/test_irt.py
git commit -m "feat(irt): add CLI interface with convergence warning (Phase 3 Task 6)"
```

---

### Task 7: Preset Router Core Logic with Capability θ Integration

**Files:**
- Create: `bench_cli/recommend/__init__.py`
- Create: `bench_cli/recommend/presets.py`
- Create: `tests/test_recommend_preset.py`

**Interfaces:**
- Consumes:
  - `bench_cli.compare.core.load_compare_data`
  - `bench_cli.irt.fit.fit_2pl` (via imports if PyMC available)
- Produces:
  - `bench_cli.recommend.presets.RankedModel` dataclass (contains `dominated_by: list[str]`)
  - `bench_cli.recommend.presets.RecommendResult` dataclass (contains `used_irt: bool`)
  - `bench_cli.recommend.presets.recommend_preset(data, preset, *, log_dir="logs", use_irt=True) -> RecommendResult`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_recommend_preset.py` from scratch, defining the mock cohort helper `_make_cohort()` (including a strictly dominated model `"dominated-worst"` to assert on Pareto domination listing) and all preset/θ validation test cases:

```python
"""Tests for the preset router (SC9)."""

from __future__ import annotations

import math
import pytest
from bench_cli.compare.core import CompareData, PillarScores


def _make_cohort() -> CompareData:
    """Synthetic cohort: 5 models, 2 tasks, varying capability and cost."""
    models = ["fast-cheap", "slow-expensive", "balanced-a", "balanced-b", "dominated-worst"]
    tasks = ["t1", "t2"]
    matrix: dict[str, dict[str, PillarScores]] = {}
    for task in tasks:
        matrix[task] = {}

    for t in tasks:
        matrix[t]["fast-cheap"] = PillarScores(
            correctness=0.5, token_ratio=1.0, time_ratio=1.0,
            avg_tokens=50, avg_time=1.0, samples=1,
            avg_cost_usd=0.001,
        )
        matrix[t]["slow-expensive"] = PillarScores(
            correctness=0.9, token_ratio=1.0, time_ratio=1.0,
            avg_tokens=500, avg_time=10.0, samples=1,
            avg_cost_usd=0.05,
        )
        matrix[t]["balanced-a"] = PillarScores(
            correctness=0.75, token_ratio=1.0, time_ratio=1.0,
            avg_tokens=200, avg_time=4.0, samples=1,
            avg_cost_usd=0.01,
        )
        matrix[t]["balanced-b"] = PillarScores(
            correctness=0.7, token_ratio=1.0, time_ratio=1.0,
            avg_tokens=150, avg_time=6.0, samples=1,
            avg_cost_usd=0.005,
        )
        matrix[t]["dominated-worst"] = PillarScores(
            correctness=0.4, token_ratio=1.0, time_ratio=1.0,
            avg_tokens=600, avg_time=12.0, samples=1,
            avg_cost_usd=0.06,
        )

    return CompareData(matrix=matrix, tasks=tasks, models=models)


def test_best_preset_ranks_by_capability():
    from bench_cli.recommend.presets import recommend_preset
    data = _make_cohort()
    result = recommend_preset(data, "best")
    assert result.preset == "best"
    assert result.models[0].model == "slow-expensive"


def test_cheap_fast_filters_below_median_cost():
    from bench_cli.recommend.presets import recommend_preset
    data = _make_cohort()
    result = recommend_preset(data, "cheap-fast")
    model_names = [m.model for m in result.models]
    assert "slow-expensive" not in model_names
    assert result.models[0].model == "fast-cheap"


def test_preset_rankings_deterministic():
    from bench_cli.recommend.presets import recommend_preset
    data = _make_cohort()
    r1 = recommend_preset(data, "best")
    r2 = recommend_preset(data, "best")
    assert [m.model for m in r1.models] == [m.model for m in r2.models]


def test_different_presets_different_top3():
    from bench_cli.recommend.presets import recommend_preset
    data = _make_cohort()
    best = recommend_preset(data, "best")
    cheap = recommend_preset(data, "cheap-fast")
    assert best.models[0].model != cheap.models[0].model


def test_preset_router_uses_theta_when_pymc_available():
    """Preset router uses IRT θ as capability measure when use_irt=True and PyMC is available."""
    from bench_cli.recommend.presets import recommend_preset
    from unittest.mock import patch
    from bench_cli.irt.types import IRTFit

    data = _make_cohort()
    mock_fit = IRTFit(
        theta=[1.5, 0.0, 0.5, 0.1, -1.0],
        theta_ci=[(0,0)]*5, a=[1.0], a_ci=[(0,0)], b=[0.0], b_ci=[(0,0)],
        models=["fast-cheap", "slow-expensive", "balanced-a", "balanced-b", "dominated-worst"],
        tasks=["t1"], pillar=None, converged=True, n_divergences=0
    )

    with patch("bench_cli.recommend.presets.fit_2pl", return_value=mock_fit), \
         patch("bench_cli.recommend.presets._has_pymc", return_value=True):
        result = recommend_preset(data, "best", use_irt=True)
        assert result.models[0].model == "fast-cheap"
        assert result.used_irt is True


def test_balanced_preset_populates_dominated_by():
    """balanced preset populates dominated_by list with model names."""
    from bench_cli.recommend.presets import recommend_preset

    data = _make_cohort()
    result = recommend_preset(data, "balanced", use_irt=False)
    dominated = [m for m in result.models if m.model == "dominated-worst"]
    if dominated:
        # dominated-worst is dominated by slow-expensive, balanced-a, balanced-b
        assert len(dominated[0].dominated_by) >= 1
        assert "slow-expensive" in dominated[0].dominated_by
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_recommend_preset.py -v`
Expected: FAIL (presets.py doesn't exist)

- [ ] **Step 3: Implement preset router core logic**

Create `bench_cli/recommend/presets.py` containing clean dataclasses and preset capability routing:

```python
"""Preset router — rank models by use-case preset."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from bench_cli.compare.core import CompareData, _aggregate_model_pillars
from bench_cli.results.core import is_moniker_alias


@dataclass
class RankedModel:
    model: str
    rank: int
    capability: float
    ci: tuple[float, float] | None
    cost_per_task: float
    time_per_task: float
    on_pareto: bool = False
    dominated_by: list[str] = field(default_factory=list)


@dataclass
class RecommendResult:
    preset: str
    models: list[RankedModel]
    used_irt: bool = False


def _has_pymc() -> bool:
    try:
        import pymc  # noqa: F401
        return True
    except ImportError:
        return False


def _gather_model_stats(
    data: CompareData,
    log_dir: str,
    *,
    use_irt: bool = True,
) -> tuple[list[dict], bool]:
    from bench_cli.identity import reconcile_identities
    # Reconcile identities to ensure consistent model cohort mapping
    identity_map = reconcile_identities(log_dir, models=data.models)

    stats: list[dict] = []
    theta_map: dict[str, float] = {}
    theta_ci_map: dict[str, tuple[float, float]] = {}
    actually_used_irt = False

    # Filter out monikers and group raw models by their canonical identities
    canonical_models_set: set[str] = set()
    for m in data.models:
        canonical = identity_map.get(m, m)
        if not is_moniker_alias(canonical):
            canonical_models_set.add(canonical)

    models_to_fit = sorted(list(canonical_models_set))

    if use_irt and _has_pymc():
        try:
            from bench_cli.irt.fit import fit_2pl
            from bench_cli.irt.types import OutcomeMatrix
            
            tasks = data.tasks
            matrix: list[list[float]] = []
            for model in models_to_fit:
                row = []
                for task in tasks:
                    vals = []
                    for raw_model in data.models:
                        if identity_map.get(raw_model, raw_model) == model:
                            ps = data.matrix.get(task, {}).get(raw_model)
                            if ps is not None and not math.isnan(ps.correctness):
                                vals.append(ps.correctness)
                    if vals:
                        row.append(sum(vals) / len(vals))
                    else:
                        row.append(float("nan"))
                matrix.append(row)
            
            outcome = OutcomeMatrix(matrix=matrix, models=models_to_fit, tasks=tasks)
            fit = fit_2pl(outcome, n_samples=1000, n_chains=2)
            if fit.converged:
                for i, m in enumerate(fit.models):
                    theta_map[m] = fit.theta[i]
                    theta_ci_map[m] = fit.theta_ci[i]
                actually_used_irt = True
        except Exception:
            pass

    # Build merged stats for each canonical model
    canonical_stats: dict[str, list[dict]] = {}
    for raw_model in data.models:
        canonical = identity_map.get(raw_model, raw_model)
        if canonical not in canonical_models_set:
            continue
        agg = _aggregate_model_pillars(data, raw_model)
        if agg is None:
            continue
        canonical_stats.setdefault(canonical, []).append({
            "correct_mean": agg["correct_mean"],
            "cost_per_task": agg["cost_per_task"],
            "time_per_task": agg["time_per_task"],
            "ci_low": agg["ci_low"],
            "ci_high": agg["ci_high"],
        })

    for model in models_to_fit:
        entries = canonical_stats.get(model, [])
        if not entries:
            continue
        
        # Merge by taking the average across raw models that mapped to this canonical name
        mean_cap = sum(e["correct_mean"] for e in entries) / len(entries)
        valid_costs = [e["cost_per_task"] for e in entries if not math.isnan(e["cost_per_task"])]
        mean_cost = sum(valid_costs) / len(valid_costs) if valid_costs else float("nan")
        valid_times = [e["time_per_task"] for e in entries if not math.isnan(e["time_per_task"])]
        mean_time = sum(valid_times) / len(valid_times) if valid_times else float("nan")

        cap = theta_map.get(model, mean_cap)
        ci = theta_ci_map.get(model, (entries[0]["ci_low"], entries[0]["ci_high"]) if entries[0]["ci_low"] is not None else None)

        stats.append({
            "model": model,
            "capability": cap,
            "ci": ci,
            "cost_per_task": mean_cost,
            "time_per_task": mean_time,
        })

    return stats, actually_used_irt


def recommend_preset(
    data: CompareData,
    preset: str,
    *,
    log_dir: str = "logs",
    use_irt: bool = True,
) -> RecommendResult:
    """Rank models by preset logic."""
    stats, actually_used_irt = _gather_model_stats(data, log_dir, use_irt=use_irt)

    if preset == "best":
        ranked = sorted(stats, key=lambda s: s["capability"], reverse=True)
        models = [
            RankedModel(
                model=s["model"], rank=i + 1,
                capability=s["capability"], ci=s["ci"],
                cost_per_task=s["cost_per_task"],
                time_per_task=s["time_per_task"],
            )
            for i, s in enumerate(ranked)
        ]
    elif preset == "cheap-fast":
        costs = [s["cost_per_task"] for s in stats if not math.isnan(s["cost_per_task"])]
        median_cost = statistics.median(costs) if costs else float("inf")
        filtered = [s for s in stats if not math.isnan(s["cost_per_task"]) and s["cost_per_task"] < median_cost]
        ranked = sorted(filtered, key=lambda s: (s["time_per_task"], -s["capability"]))
        models = [
            RankedModel(
                model=s["model"], rank=i + 1,
                capability=s["capability"], ci=s["ci"],
                cost_per_task=s["cost_per_task"],
                time_per_task=s["time_per_task"],
            )
            for i, s in enumerate(ranked)
        ]
    elif preset == "balanced":
        from bench_cli.recommend.pareto import compute_pareto_front
        model_names = [s["model"] for s in stats]
        capabilities = [s["capability"] for s in stats]
        costs = [s["cost_per_task"] if not math.isnan(s["cost_per_task"]) else float("inf") for s in stats]
        times = [s["time_per_task"] for s in stats]
        pareto_indices, dominated_by_indices = compute_pareto_front(model_names, capabilities, costs, times)
        pareto_set = set(pareto_indices)
        pareto_models = sorted([i for i in range(len(stats)) if i in pareto_set], key=lambda i: stats[i]["capability"], reverse=True)
        dominated_models = sorted([i for i in range(len(stats)) if i not in pareto_set], key=lambda i: stats[i]["capability"], reverse=True)
        
        models = []
        for rank, i in enumerate(pareto_models + dominated_models, 1):
            s = stats[i]
            dom_models = [model_names[d] for d in dominated_by_indices[i]]
            models.append(RankedModel(
                model=s["model"], rank=rank,
                capability=s["capability"], ci=s["ci"],
                cost_per_task=s["cost_per_task"],
                time_per_task=s["time_per_task"],
                on_pareto=i in pareto_set,
                dominated_by=dom_models,
            ))
    else:
        raise ValueError(f"Unknown preset: {preset}")

    return RecommendResult(preset=preset, models=models, used_irt=actually_used_irt)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_recommend_preset.py -v`
Expected: FAIL on balanced test (pareto module missing) — others pass.

- [ ] **Step 5: Commit**

```bash
git add bench_cli/recommend/presets.py tests/test_recommend_preset.py
git commit -m "feat(recommend): preset router core logic (Phase 4 Task 7)"
```

---

### Task 8: Pareto Front Computation

**Files:**
- Create: `bench_cli/recommend/pareto.py`
- Modify: `tests/test_recommend_preset.py` (append tests)

**Interfaces:**
- Consumes: nothing (standalone computation)
- Produces:
  - `bench_cli.recommend.pareto.compute_pareto_front(models: list[str], capability: list[float], cost: list[float], time: list[float]) -> tuple[list[int], list[list[int]]]`
    - Returns `(pareto_indices, dominated_by)` indexes where objectives are maximizing capability, minimizing cost, minimizing time.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_recommend_preset.py`:

```python
def test_pareto_front_basic():
    from bench_cli.recommend.pareto import compute_pareto_front

    pareto_idx, dominated_by = compute_pareto_front(
        models=["a", "b", "c"],
        capability=[0.9, 0.5, 0.4],
        cost=[0.05, 0.001, 0.06],
        time=[10.0, 1.0, 12.0],
    )
    assert 0 in pareto_idx  # a is Pareto-optimal
    assert 1 in pareto_idx  # b is Pareto-optimal
    assert 2 not in pareto_idx  # c is dominated by a (better cap, lower cost, lower time)
```

- [ ] **Step 2: Implement Pareto front computation**

Create `bench_cli/recommend/pareto.py`:

```python
"""Pareto front computation on flat arrays — (capability, -cost, -time)."""

from __future__ import annotations


def compute_pareto_front(
    models: list[str],
    capability: list[float],
    cost: list[float],
    time: list[float],
) -> tuple[list[int], list[list[int]]]:
    """Compute Pareto front across (capability, -cost, -time).

    A model dominates another if it is >= on all axes and > on at least one.
    Objectives: maximize capability, minimize cost, minimize time.
    """
    n = len(models)
    dominated_by: list[list[int]] = [[] for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            
            cap_ge = capability[j] >= capability[i]
            cost_ge = cost[j] <= cost[i]
            time_ge = time[j] <= time[i]

            cap_gt = capability[j] > capability[i]
            cost_gt = cost[j] < cost[i]
            time_gt = time[j] < time[i]

            if cap_ge and cost_ge and time_ge and (cap_gt or cost_gt or time_gt):
                dominated_by[i].append(j)

    pareto_indices = [i for i in range(n) if not dominated_by[i]]
    return pareto_indices, dominated_by
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_recommend_preset.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add bench_cli/recommend/pareto.py tests/test_recommend_preset.py
git commit -m "feat(recommend): Pareto front computation for balanced preset (Phase 4 Task 8)"
```

### Task 9: Preset Router CLI with `--use-irt` Flag

**Files:**
- Create: `bench_cli/recommend/cli.py`
- Modify: `bench_cli/main.py` (register CLI)
- Modify: `tests/test_recommend_preset.py` (append test)

**Interfaces:**
- Consumes:
  - `bench_cli.recommend.presets.recommend_preset`
- Produces:
  - `bench recommend-preset --preset {best,cheap-fast,balanced} [--log-dir] [--use-irt/--no-use-irt] [--json]`

- [ ] **Step 1: Write the failing tests**

Ensure `tests/test_recommend_preset.py` verifies the Click command can accept `--use-irt/--no-use-irt`.

- [ ] **Step 2: Implement CLI command**

Create `bench_cli/recommend/cli.py`:

```python
"""CLI command for preset-based model recommendations."""

from __future__ import annotations

import json
import math
import click


def _fmt_cost(cost: float) -> str:
    if math.isnan(cost):
        return "n/a"
    return f"${cost:.4f}"


def _fmt_time(t: float) -> str:
    if math.isnan(t):
        return "n/a"
    if t < 60:
        return f"{t:.1f}s"
    return f"{int(t // 60)}m{t % 60:.0f}s"


@click.command("recommend-preset")
@click.option(
    "--preset",
    type=click.Choice(["best", "cheap-fast", "balanced"]),
    required=True,
    help="Recommendation preset.",
)
@click.option("--log-dir", default="logs", help="Directory containing .eval logs.")
@click.option(
    "--use-irt/--no-use-irt",
    default=True,
    help="Use θ from IRT fit as capability measure if PyMC is available; else pass@1.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def recommend_preset_cmd(preset: str, log_dir: str, use_irt: bool, as_json: bool) -> None:
    """Rank models by use-case preset."""
    from bench_cli.compare.core import load_compare_data
    from bench_cli.recommend.presets import recommend_preset

    data = load_compare_data(log_dir)
    if not data.models:
        click.echo("No model data found in logs.")
        return

    result = recommend_preset(data, preset, use_irt=use_irt)

    if not result.models:
        click.echo(f"No models match the '{preset}' preset criteria.")
        return

    if as_json:
        out = {
            "preset": result.preset,
            "used_irt": result.used_irt,
            "models": [
                {
                    "rank": m.rank,
                    "model": m.model,
                    "capability": m.capability,
                    "cost_per_task": m.cost_per_task,
                    "time_per_task": m.time_per_task,
                    "on_pareto": m.on_pareto,
                    "dominated_by": m.dominated_by,
                }
                for m in result.models
            ],
        }
        click.echo(json.dumps(out, indent=2))
    else:
        cap_header = "θ" if result.used_irt else "Cap"

        click.echo(f"\nPreset: {preset}")
        click.echo(f"{'#':>3}  {'Model':<35} {cap_header:>6} {'Cost/task':>10} {'Time/task':>10} {'Pareto':>7}")
        click.echo(f"{'---':>3}  {'-' * 35} {'-' * 6} {'-' * 10} {'-' * 10} {'-' * 7}")
        for m in result.models:
            pareto_mark = "  ★" if m.on_pareto else ""
            cap_val = f"{m.capability:.3f}" if result.used_irt else f"{m.capability:.1%}"
            click.echo(
                f"{m.rank:>3}  {m.model:<35} {cap_val:>6} "
                f"{_fmt_cost(m.cost_per_task):>10} {_fmt_time(m.time_per_task):>10}"
                f"{pareto_mark:>7}"
            )
```

- [ ] **Step 3: Register in main.py with alias**

In `bench_cli/main.py`, register the command under its full name and its `rp` alias:

```python
from bench_cli.recommend.cli import recommend_preset_cmd
cli.add_command(recommend_preset_cmd, name="recommend-preset")
cli.add_command(recommend_preset_cmd, name="rp")
```

- [ ] **Step 4: Run tests and check regressions**

- [ ] **Step 5: Commit**

```bash
git add bench_cli/recommend/cli.py bench_cli/main.py tests/test_recommend_preset.py
git commit -m "feat(recommend): add CLI command with use-irt flag (Phase 4 Task 9)"
```

---

## Verification Commands

After all tasks are complete:

```bash
# Phase 3 — IRT
bench irt fit                        # per-pillar θ + CI
bench irt item-analysis              # task difficulty/discrimination
bench irt fit --pillar analysis      # single pillar
bench irt fit --json                 # JSON output

# Phase 4 — Preset Router
bench recommend-preset --preset balanced
bench rp --preset balanced           # verify rp alias works
bench recommend-preset --preset best --json

# Regression
.venv/bin/pytest -q                  # all tests green

# Isolation (SC13)
# Temporarily: pip uninstall pymc && .venv/bin/pytest -q (non-IRT tests pass)
```

## Success Criteria Traceability

| SC | Task | Test |
|----|------|------|
| 4 | Task 4 | `test_2pl_recovers_synthetic_params` |
| 5 | Task 5 | `test_item_analysis_labels_cull` |
| 9 | Task 7 | `test_preset_rankings_deterministic`, `test_different_presets_different_top3` |
| 10 | Task 4+5 | `test_2pl_recovers_synthetic_params` + live `bench irt item-analysis` after B2 evals |
| 13 | Task 6 | `test_compare_works_without_pymc`, `test_irt_fit_cli_requires_pymc` |
