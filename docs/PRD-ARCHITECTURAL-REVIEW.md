# PRD: Comprehensive Architectural Review and Improvement

**Status:** draft
**Project:** bench
**Owner:** Michael Mazyar
**Scope:** refactor
**Date:** 2026-04-21
**Tier:** deep

---

## Problem Statement

Bench has a **shape problem, not a substance problem**. The codebase works correctly (405 tests pass), the scorer modules are well-focused, and the evaluation pipeline is solid. But 54% of bench_cli's lines are concentrated in 4 files (inspect.py 801, compare.py 604, run.py 603, results.py 600), each mixing CLI Click commands with business logic, data models, and I/O. This creates unnecessary cognitive load when modifying any single concern — opening inspect.py requires scanning 800 lines to find the analysis function you need. With F2, F13, U9, U10 still to implement, these files will continue growing unless boundaries are established now.

---

## First Principles Analysis

### Deconstruction

| Constituent Part | Actual Function | Actual Cost | Gap from Stated |
|---|---|---|---|
| Task definitions (36 dirs) | Pure data: prompt + dataset + scoring rubric | No code overhead | Correctly structured |
| Scoring functions (22 files) | Pure functions: (state) → Score | ~15 unique strategies; some 6-line wrappers | Mostly well-isolated — the good part |
| CLI orchestration (4 files) | Command → dispatch → format output | 2608 lines, 4 files mixing 3+ concerns each | Stated "CLI layer" is actually "entire application" |
| Pricing infrastructure | Resolve alias → fetch price → cache | Clean module, but scorers/ imports from bench_cli/ | One cross-boundary violation |
| Agent solvers (3 files) | Subprocess wrapper + output parsing | Well-scoped, <100 lines each | No issue |

**A physicist would see 4 forces at play:**
1. **Gravity**: Concerns cluster — scoring, orchestration, pricing naturally group
2. **Entropy**: Files grow linearly. 800-line inspect.py wasn't born that way — it accreted
3. **Coupling**: Only one cross-boundary import (scorers → bench_cli/pricing). Everything else is loose
4. **Inertia**: Large files resist modification. Opening 800 lines to change line 450 is the real cost

### Constraint Classification

| Constraint | Type | Evidence | If Removed? |
|---|---|---|---|
| Inspect AI framework | **Hard** | Core eval dependency | No evaluation system |
| Click CLI | **Hard** | User-facing contract | Need replacement CLI |
| 36 task directories | **Hard** | Working eval tasks | Lose evaluation suite |
| 405 tests | **Hard** | Regression safety net | Uncontrolled breakage |
| `.eval` binary format | **Hard** | Inspect native format | Can't read results |
| "200-line file limit" | **Soft** | Style preference | Some long cohesive files are fine |
| "CLI separate from logic" | **Soft** | Pattern preference | Click recommends this explicitly |
| "No cross-package imports" | **Soft** | Architecture ideal | The one existing cross-import works |
| "Must refactor all 4 files at once" | **Assumption** | No evidence incremental isn't safer | Incremental is safer |
| "Tiny scorer files must consolidate" | **Assumption** | safety.py=6 lines, efficiency.py=8 lines | Not causing pain |
| "_MANUAL_PRICES must be external config" | **Assumption** | 8 entries, changes with releases | Code constant is fine |
| "More modules = better architecture" | **Assumption** | Intuition | More files = more navigation overhead |

### Reconstruction

**Option A: Minimal Peel** — Extract CLI Click decorators into thin `cli.py` files. Keep business logic in same modules (now ~400 lines). Smallest diff, safest, but doesn't fully separate concerns.

**Option B: Pipeline Architecture** — Decompose into stages (discover → score → aggregate → report). Each stage is a module with clear I/O protocol. Best conceptual clarity but largest refactor, highest risk to 405 tests.

**Option C: Package-per-Command (Recommended)** — Convert each large file into a Python package: `run/`, `inspect/`, `compare/`, `results/`. Each gets `cli.py` (Click wiring, ~50-100 lines) + `core.py` (business logic, ~300-500 lines). Standard Python pattern, incremental per-package, only touches the 4 files that need it.

**Recommended: Option C** because: incremental (one package at a time, tests green between each), proportional (only 4 files get split), familiar (standard Python package pattern), practical (proves value on worst offender before continuing).

---

## Hidden Requirements (from 8-lens IterativeDepth)

| # | Requirement | Supporting Lenses |
|---|---|---|
| 1 | CLI commands are thin adapters delegating to core functions | LITERAL, EXPERIENTIAL, ANALOGICAL, META |
| 2 | Each module has ≤2 concerns | LITERAL, FAILURE, TEMPORAL, EXPERIENTIAL |
| 3 | New scorers require no bench_cli code changes | FAILURE, STAKEHOLDER, TEMPORAL |
| 4 | No file exceeds 400 lines | LITERAL, TEMPORAL, EXPERIENTIAL |
| 5 | Import count does not increase by >20% | CONSTRAINT INVERSION, META, EXPERIENTIAL |
| 6 | Adding a new task modifies ≤2 files | TEMPORAL, STAKEHOLDER, FAILURE |
| 7 | Each split has documented "why" tied to real DX pain | META, EXPERIENTIAL, FAILURE |

---

## Council Synthesis

### Convergence Points (all 4 agents agree)
- Only split the 4 files that are >500 lines
- CLI is a thin adapter — Click decorators call core functions, no business logic in CLI layer
- Tiny scorer files stay as-is
- Tests are the contract — preserve all 405 tests
- Do it incrementally, one file at a time, tests green between each

### Disagreements

| Topic | Position A | Position B | Resolution |
|---|---|---|---|
| Do all 4 or just 2 worst? | All 4 for consistency | Just inspect.py + run.py | **All 4, phased** — worst first, verify DX, continue |
| Consolidate tiny scorers? | Leave them | Merge into groups | **Leave them** — no pain, adds risk |
| Externalize _MANUAL_PRICES? | Move to JSON | Leave as code constant | **Leave as code** — changes with releases anyway |

### Final Synthesis
Split 4 large files into packages. Each package: `cli.py` (Click adapters) + `core.py` (business logic). Keep scorers flat. Fix the one cross-boundary import with a thin adapter. Incremental, one package at a time.

---

## RedTeam Counter-Arguments

### Steelman
1. **Cognitive load reduction**: Opening `inspect/core.py` (500 lines) instead of `inspect.py` (801 lines mixed CLI+logic) is measurably better
2. **Test preservation**: Refactor doesn't change public API — only internal file organization
3. **Growth accommodation**: F2, F13, U9, U10 will add lines. Splitting now is preventive
4. **Python convention**: Package-per-concern is how pytest, Django, and mature Python projects work

### Fatal Flaws & Mitigations

| Counter-Argument | Severity | Mitigation |
|---|---|---|
| "This is cosplay refactoring — no visible outcome" | **Fatal if unaddressed** | Tie each split to an adjacent feature: run.py split as part of F2, inspect.py as part of U9/U10. Refactoring without adjacent feature work is architecture astronautics |
| "You'll break tests in subtle ways" | **Major** | Run full test suite after EACH file split. No batching. Green between every step |
| "Navigation cost increases — more files to search" | **Minor** | Consistent naming: always `cli.py` + `core.py`. Convention eliminates search |
| "Single-developer over-engineering" | **Major** | Valid critique. Only split files that are actively painful. If inspect.py wasn't painful last session, question whether this is needed now |

---

## Success Criteria

### Goal
Reduce maximum file size in bench_cli/ from 801 to ≤400 lines while maintaining 405/405 tests passing, without circular dependencies or >20% import count increase.

### Verification Methods

1. **No file in bench_cli/ exceeds 400 lines** — verify by: `find bench_cli -name "*.py" -exec wc -l {} + | sort -rn | head -10`
2. **All 405 tests pass after each split** — verify by: `pytest --tb=short -q` after each package conversion
3. **CLI functions contain no business logic** — verify by: each `cli.py` function only does arg parsing and delegates to `core.py` functions (no Inspect API calls, no file I/O, no data processing)
4. **Import count stays within 120% of current** — verify by: `grep -r "^import\|^from" bench_cli/ | wc -l` before and after
5. **No circular dependencies** — verify by: `import graph` — cli.py imports core.py, never reverse
6. **Each split is independently deployable** — verify by: convert one file, run tests, commit. Next file starts from green.
7. **Cross-boundary import (scorers→pricing) resolved** — verify by: `grep -r "bench_cli" scorers/` returns zero results

---

## Science Cycle Documentation

### Goal
Max file size ≤400 lines in bench_cli/, all 405 tests passing, no architectural violations.

### Hypotheses

| Hypothesis | Expected Outcome | Verification |
|---|---|---|
| H1: Package-per-command split preserves all tests | 405/405 pass | `pytest` after each file |
| H2: CLI/logic separation reduces time-to-locate | <30s to find any function | Pick 10 functions, time before/after |
| H3: Refactor doesn't increase cognitive complexity | Import count ≤120% of current | Count imports before/after |

### Measurement Framework
- **Primary**: Max file line count in bench_cli/ (target: ≤400)
- **Secondary**: Files >200 lines, import count, test pass rate
- **Guardrail**: Test count (≥405), total line count (≤110% of current)

---

## Implementation Approach

### Phase 1: inspect.py → inspect/ package (worst offender, 801 lines)

Convert `bench_cli/inspect.py` into `bench_cli/inspect/` package:
- `cli.py` — 4 Click commands (inspect, stats, compare_cmd, deep_check) as thin adapters (~100 lines)
- `core.py` — Analysis functions: _load_pillar_map, _get_task_dir, stats logic, compare logic, deep_check logic (~500 lines)
- `models.py` — SampleScore dataclass, PillarMap helper (~30 lines, if it makes sense; otherwise keep in core.py)

**Steps:**
1. Create `bench_cli/inspect/` directory
2. Move Click commands to `cli.py` — each command does arg parsing and calls core functions
3. Move analysis functions to `core.py` — all business logic
4. Create `__init__.py` re-exporting public API so external imports (`from bench_cli.inspect import ...`) still work
5. Run tests — fix any import path issues
6. Commit when green

### Phase 2: run.py → run/ package (603 lines)

Convert `bench_cli/run.py` into `bench_cli/run/`:
- `cli.py` — `run()` Click command as thin adapter (~80 lines)
- `core.py` — _discover_tasks, _resolve_task, _resolve_agent_solver, eval execution (~400 lines)
- `docker.py` — _docker_available, _requires_docker (~30 lines, only if it's truly separate)

### Phase 3: compare.py → compare/ package (604 lines)

Convert `bench_cli/compare.py` into `bench_cli/compare/`:
- `cli.py` — `compare()` Click command (~60 lines)
- `core.py` — load_compare_data, format_pillar_table, _extract_from_scorers, geometric_mean (~400 lines)
- `models.py` — PillarScores, CompareData dataclasses (~50 lines)

### Phase 4: results.py → results/ package (600 lines)

Convert `bench_cli/results.py` into `bench_cli/results/`:
- `cli.py` — `results()`, `generate_cmd()` Click commands (~60 lines)
- `core.py` — generate_card, _generate_summary, data processing (~400 lines)

### Phase 5: Cross-boundary import cleanup

- Move pricing resolution logic that scorers need into `bench_cli/pricing/resolve.py`
- `scorers/price_ratio.py` imports from `bench_cli/pricing/resolve.py` instead of directly from cache/config
- Or: create `scorers/_pricing_adapter.py` as a thin interface so scorers don't know about bench_cli internals

### Phase 6: main.py registration update

- Update `bench_cli/main.py` to import Click groups from new package `cli.py` files
- Verify all 7 subcommands still work: run, baseline, compare, inspect, results, prices

---

## Edge Cases & Gotchas

- **__init__.py re-exports**: When converting a `.py` file to a package, existing imports like `from bench_cli.inspect import stats` must still work. The `__init__.py` must re-export public symbols.
- **Test import paths**: Tests that import from `bench_cli.inspect` will work if `__init__.py` re-exports, but tests importing `bench_cli.inspect.specific_function` may need path updates if the function moved to `core.py`.
- **Click command registration**: `main.py` imports Click commands by reference. When inspect.py becomes inspect/cli.py, the import path changes but Click's `@click.group()` registration pattern stays the same.
- **Module-level side effects**: If any of the 4 files have module-level code that runs on import (e.g., config loading, cache initialization), it must be preserved in the new package structure.
- **conftest.py fixtures**: Test fixtures may reference the old module paths. Check conftest.py imports after each split.

---

## Anti-Patterns to Avoid

- **Don't split for the sake of splitting** — Rich's `console.py` is 1200 lines and that's fine because it's one cohesive concern. Only split where there are genuinely 2+ separable concerns.
- **Don't consolidate tiny scorer files** — safety.py (6 lines) and efficiency.py (8 lines) aren't causing pain. Merging them adds risk for zero gain.
- **Don't externalize _MANUAL_PRICES** — It's 8 entries that change with code releases. A JSON file adds I/O complexity without benefit.
- **Don't add abstraction layers** — No adapters, no facades, no dependency injection. Just move functions to the right file.
- **Don't batch the splits** — Do one file, verify tests, commit. Then next file. Batching makes debugging harder.
- **Don't change public API** — External callers (`from bench_cli.run import run`) must still work. Use `__init__.py` re-exports.

---

## Acceptance Checklist

- [ ] No file in bench_cli/ exceeds 400 lines — verify by: `find bench_cli -name "*.py" -exec wc -l {} + | sort -rn | head -10`
- [ ] All 405 tests pass — verify by: `pytest --tb=short -q`
- [ ] CLI functions contain no business logic — verify by: review each cli.py for Inspect API calls, file I/O, data processing
- [ ] Import count within 120% of current — verify by: `grep -rc "^import\|^from" bench_cli/ | awk -F: '{s+=$2}END{print s}'`
- [ ] No circular dependencies — verify by: cli.py imports core.py, never reverse
- [ ] Cross-boundary import resolved — verify by: `grep -r "bench_cli" scorers/` returns zero
- [ ] All 7 CLI subcommands work — verify by: `python -m bench_cli run --help`, `python -m bench_cli compare --help`, etc.
- [ ] Each split committed independently — verify by: `git log --oneline` shows 4+ separate commits

## Test Plan

- [ ] Unit tests: Run full 405-test suite after each file split — no batching
- [ ] Integration tests: Verify CLI commands still work end-to-end (run, compare, inspect, results, baseline, prices)
- [ ] Import regression: `python -c "from bench_cli.run import run; from bench_cli.inspect import stats; from bench_cli.compare import compare; from bench_cli.results import results"` succeeds
- [ ] No new test files needed — existing tests cover the behavior, only import paths may change

## Docs to Update

- [ ] CLAUDE.md — update Architecture section with new package structure
- [ ] docs/IMPLEMENTATION-NOTES.md — add architectural review notes
- [ ] No external API changes — no user-facing docs need updating

---

## Open Questions

- **Q: Should we tie splits to adjacent feature work?** → RedTeam's strongest critique is "no visible outcome." If there's no feature work pending, a standalone refactor is still justified if inspect.py was genuinely painful in recent sessions. If it wasn't painful, consider deferring.
- **Q: What's the right line count target?** → Research confirms: no magic number. 200 is cargo cult. Organize by semantics. 400 is a reasonable ceiling for this codebase because the 4 files all exceed it AND have identifiable concern boundaries.
- **Q: models.py or keep dataclasses in core.py?** → Only extract if there are 3+ dataclass definitions. If just 1-2 (like SampleScore), keep in core.py. Don't create a file for its own sake.

---

## Skill Integration Log

- **Thinking/FirstPrinciples**: Identified that the problem is shape (packaging), not substance (logic). Classified 12 constraints as hard/soft/assumption. Generated 3 reconstruction options.
- **Thinking/IterativeDepth**: Ran 8 lenses, generated 22 ISC criteria, identified 7 highest-confidence requirements appearing across 3+ lenses.
- **Thinking/Council**: 4-agent debate converged on "package-per-command for 4 large files only." Disagreement on scope (2 vs 4 files) resolved as "all 4, phased." Consensus: leave tiny scorers, leave _MANUAL_PRICES as code.
- **Thinking/RedTeam**: 32-agent attack surfaced fatal flaw: "no visible outcome." Mitigation: tie splits to adjacent feature work or document specific DX pain points.
- **Thinking/Science**: Goal: max file ≤400 lines. 3 hypotheses tested via measurement framework. Guardrail: 405 tests must pass.
- **Research**: Confirmed: (1) "200 lines" is cargo cult — organize by semantics not line count, (2) pytest uses pluggy plugin system with clear hookspec contracts, (3) Click docs recommend writing logic first then wrapping with decorators, (4) Rich keeps single-file modules when cohesion is high, (5) AI context windows provide a functional reason for file size limits (150-500 lines fits in context).

## Implementation Notes

- **Decision:** Package-per-command (Option C) over Pipeline (B) or Minimal Peel (A) — because it's the standard Python pattern, incremental, and only touches what needs touching.
- **Decision:** Leave tiny scorer files alone — not causing pain, consolidation adds risk for zero gain.
- **Decision:** Leave _MANUAL_PRICES as code constant — 8 entries that change with releases, externalizing adds I/O overhead.
- **Gotcha:** When converting .py to package/, existing `from bench_cli.X import Y` imports break unless `__init__.py` re-exports Y.
- **Gotcha:** conftest.py and test files may import internal functions by full path — need grep for `bench_cli.inspect.` / `bench_cli.run.` / etc.
- **Idea:** Phase 5 (cross-boundary import) could be done as part of Phase 3 (compare split) since compare.py is where pricing import complexity lives.
