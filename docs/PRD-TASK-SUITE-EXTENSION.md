# PRD: Extend Bench Task Suite — Infrastructure + Context Hygiene Tasks

**Status:** draft
**Project:** bench
**Owner:** Michael Mazyar
**Scope:** feature + refactor
**Date:** 2026-04-20
**Tier:** deep

---

## Problem Statement

Bench has 34 tasks evaluating model competence across 4 tiers, but the suite has three significant gaps: (1) it cannot evaluate how models handle messy, realistic work contexts — stale summaries, prior failed attempts, noisy repos — because every existing task presents a clean single-shot scenario, and (2) the scoring system uses a single correctness scorer per task (either `verify_sh` or `llm_judge`) with no way to combine deterministic checks with qualitative judgment, which means judge-scored tasks have ±0.15 variance on answers that are sometimes machine-checkable. Additionally, the `generate()` solver is single-shot — the model receives one prompt and produces one response — which prevents evaluating multi-step reasoning with file exploration, creating a fundamental asymmetry between model eval and agent eval.

This PRD addresses all three: new infrastructure (multi-shot solver, hybrid scoring, discrete judge scale, rich fixtures) and two genuinely new tasks (u17-dirty-workspace-triage, u18-resume-after-bad-attempt) plus merged samples into existing tasks (f23, f21).

**Pre-alpha context:** No legacy constraints. Build the right system. Old artifacts don't matter — we move forward.

---

## First Principles Analysis

### Deconstruction

| Constituent Part | Current State | Gap | Proposed State |
|-----------------|---------------|-----|----------------|
| Solver | `generate()` — single-shot, no tool calls | Model can't explore files; agent can | Multi-shot solver with read-only tools, configurable max turns |
| Correctness scoring | One scorer per task: verify_sh OR llm_judge | Deterministic answers get ±0.15 judge variance | Hybrid: verify_sh (deterministic) + llm_judge (qualitative), weighted combination |
| Judge scale | 0-10 continuous, normalized to 0-1 | Ambiguous boundaries, compressed mid-range | Discrete 5-point scale with explicit per-level descriptions |
| Fixtures | Text prompts in dataset.json | No file state to verify against | Rich fixtures: repo directories with files, transcripts, summaries |
| Task coverage | 34 tasks, zero context-hygiene coverage | Stale context, prior attempts, noisy repos are untested | 2 new tasks + merged samples |
| compare.py | Single correctness column per task | Can't show verify_sh vs judge breakdown | Weighted correctness with sub-score metadata |

### Constraint Classification

| Constraint | Type | Evidence | If Removed? |
|-----------|------|----------|-------------|
| Inspect AI framework | Hard | All tasks, scorers, runners depend on it | Full rewrite |
| 4-pillar scoring (no composites) | Hard | Core design principle, compare.py depends on it | All comparison logic breaks |
| LiteLLM proxy routing | Hard | All model calls go through it | No model access |
| Task budget calibration (minimax m2.7) | Hard | Cost/latency/token ratio references depend on it | Ratio pillars produce NaN |

### Reconstruction

**Option A: Minimal — only new tasks, existing infrastructure**
Add u17 and u18 using current generate() + llm_judge. Quick but doesn't fix the systemic problems.

**Option B: Full rebuild — infrastructure + tasks (Recommended)**
Fix the solver, scoring, scale, and fixtures as general-purpose infrastructure. Rework all 15 judge tasks to discrete scale. Apply hybrid scoring to tasks that benefit from it. Add 2 new tasks + merged samples.

**Recommended: Option B** — there is no reason to carry known-bad patterns forward.

---

## Hidden Requirements

*(From 8-lens Iterative Depth + Council + RedTeam synthesis)*

| # | Requirement | Source |
|---|-------------|--------|
| 1 | Multi-shot solver must support per-task max_turns config (1 for existing tasks, 3-10 for new tasks) | META lens |
| 2 | verify_sh must work in two modes: file-state (agent mode) and text-output (model mode) | CONSTRAINT INVERSION lens |
| 3 | Discrete scale rubrics must have explicit descriptions for all 5 levels, not just boundaries | FAILURE lens |
| 4 | Rich fixture system must be discoverable by the solver, not hardcoded per task | STAKEHOLDER lens |
| 5 | compare.py must decompose hybrid scores into sub-components for display | EXPERIENTIAL lens |
| 6 | Weighted combination defaults must favor verify_sh (higher weight) but be overridable per task | User requirement |
| 7 | Task tier assignments must be universal for context-hygiene tasks, not analysis | META lens |
| 8 | Runtime targets for new tasks should be 3-8 minutes, not 8-20 | TEMPORAL lens |
| 9 | Judge outputs SCORE: N on 0-10 scale (0, 2.5, 5, 7.5, 10) — `_parse_score()` divides by 10 | Council + RedTeam |
| 10 | Multi-shot solver MUST set `state.output.completion = state.messages[-1].text` before returning | RedTeam fatal flaw |
| 11 | Hybrid scorer must register with a name compare.py recognizes | RedTeam fatal flaw |
| 12 | Tool implementations must sandbox file access to fixture directory | RedTeam |
| 13 | All 15 rubrics rewritten at once — no phased rollout needed | Council + user decision |

---

## Success Criteria

### Infrastructure

1. **Multi-shot solver exists** — `multishot_solver()` in `bench_cli/solvers/` with read-only tools (read_file, list_directory), configurable max_turns, tool sandboxing, and correct state.output handling. max_turns=1 branches to bare `generate()` with no tool injection.
   — verify by: Run existing task with max_turns=1, confirm score matches bare generate(). Run new task with max_turns=5, confirm model makes multiple tool calls and final answer reflects tool discoveries.

2. **Hybrid scoring framework exists** — `hybrid_scorer()` combining verify_sh + llm_judge with configurable weights. Single Score object with sub-scores in metadata. compare.py discovers it correctly.
   — verify by: Create test task with both verify.sh and judge.md. Run eval. Confirm single correctness score with metadata.verify_sh_score and metadata.llm_judge_score. Confirm compare.py displays it.

3. **Discrete judge scale implemented** — All 15 judge.md rubrics rewritten with 5 discrete levels. Judge outputs SCORE: N where N in {0, 2.5, 5, 7.5, 10}. Snap-to-discrete post-processing handles judge models that resist discretization.
   — verify by: Run full eval. Confirm scores cluster at {0.0, 0.25, 0.5, 0.75, 1.0}. Confirm no intermediate values in output.

4. **Rich fixture system exists** — Tasks declare fixtures/ directory. Multi-shot solver provides read-only tool access. Initial context lists available files.
   — verify by: Create test fixture with 3 files. Confirm model discovers and reads files via tool calls.

5. **compare.py updated** — Recognizes hybrid_scorer in extraction chain. Verbose mode shows verify_sh and llm_judge sub-scores.
   — verify by: bench compare after hybrid-scored eval shows weighted score and --verbose shows breakdown.

### Tasks

6. **u18-resume-after-bad-attempt built** — Universal tier, hybrid scoring, 3-5 samples, rich fixtures. verify_sh checks: correct file changed, existing helper imported. llm_judge checks: reasoning quality, dead-end avoidance.
   — verify by: Run eval. Confirm verify_sh catches models that don't reuse helper. Confirm score spread across model tiers.

7. **u17-dirty-workspace-triage built** — Universal tier, hybrid scoring, 4-6 samples, rich fixtures. verify_sh checks: correct config value, untouched distractor files. llm_judge checks: triage quality, scope discipline.
   — verify by: Run eval. Confirm verify_sh catches wrong-value responses. Confirm llm_judge distinguishes clean triage from cleanup theater.

8. **f23-ghost-constraint extended** — 3-4 new samples from u16/u19 proposals (buried constraints, constraint drift). Rich fixtures where appropriate.
   — verify by: f23 eval includes new samples, scores differentiate by constraint depth.

9. **f21-liars-codebase extended** — 2 new samples from u20 proposals (stale summary, stale verification claim). Rich fixtures.
   — verify by: f21 eval includes new samples, scores capture summary-distrust capability.

### System Integrity

10. **All existing tests pass** — 309+ tests. No regressions from infrastructure changes.
    — verify by: pytest passes with zero failures.

11. **Tool sandboxing verified** — Model cannot read paths outside fixture directory during eval.
    — verify by: Include `../../../etc/passwd` in test fixture prompt. Confirm tool rejects it.

12. **EVAL-GUIDE.md and CLAUDE.md updated** — New tasks, new scoring, new architecture documented.
    — verify by: Manual review.

---

## Implementation Approach

### Phase 1: Discrete Judge Scale

Rewrite all 15 judge.md rubrics. Simplest, lowest-risk change.

1. Create rubric template in `scorers/judge_rubric_template.md` with 5 discrete levels (0, 2.5, 5, 7.5, 10 → normalized to 0.0, 0.25, 0.5, 0.75, 1.0)
2. Rewrite all 15 judge.md rubrics using the template
3. Add snap-to-discrete in `_parse_score()`: `round(raw * 2) / 2` — handles judges that output intermediate values
4. Run full eval, verify scores cluster at 5 discrete levels
5. Update EVAL-GUIDE.md

**Files:** 15 judge.md files, 1 new template, `scorers/llm_judge.py` (snap logic), EVAL-GUIDE.md

### Phase 2: Rich Fixture System

Fixture directory convention and loading utilities.

1. Define convention: `tasks/{tier}/{task}/fixtures/{scenario_id}/`
2. Create `bench_cli/fixtures.py` with `load_fixtures(task_dir, scenario_id)`
3. Extend dataset.json with optional `"fixture": "scenario_id"` field
4. In `_resolve_task()`, inject fixture path into sample metadata
5. Write tests with a minimal test fixture

**Files:** New `bench_cli/fixtures.py`, modified `bench_cli/run.py`, modified dataset.json files

### Phase 3: Multi-Shot Solver

New solver with read-only tool access. The most architecturally significant change.

1. Create `bench_cli/solvers/multishot.py` with `multishot_solver(max_turns=1, tools=None)`
2. Default tools: `read_file(path)` and `list_directory(path)` — read-only, sandboxed to fixture dir
3. **Tool sandboxing:** `resolved = (fixture_dir / path).resolve(); assert resolved.is_relative_to(fixture_dir)` — reject any escape
4. **Inspect integration:** Use Inspect's native `use_tools()` + `generate(tool_calls='loop')` — not a custom turn loop
5. **max_turns=1 bypass:** Code-level branch — `if max_turns <= 1: return generate()` with zero tool injection
6. **Output fix:** `state.output = ModelOutput(model=str(state.model), completion=state.messages[-1].text)` — Inspect's tool loop doesn't update state.output
7. Inject initial context listing available fixture files
8. Wire into task.py: tasks specify `solver=multishot_solver(max_turns=5)`
9. **Prerequisite:** Validate 2+ models support tool calling through LiteLLM proxy

**Files:** New `bench_cli/solvers/multishot.py`, modified `bench_cli/run.py`

### Phase 4: Hybrid Scoring

Combines verify_sh + llm_judge into single weighted correctness score.

1. Create `scorers/hybrid.py` with `hybrid_scorer(verify_weight=0.7, judge_weight=0.3)`
2. Runs both verify_sh and llm_judge, combines: `value = v_weight * v_score + j_weight * j_score`
3. Sub-scores in metadata: `verify_sh_score`, `llm_judge_score`, `verify_weight`, `judge_weight`
4. **compare.py discovery:** Add `hybrid_scorer` to `_extract_from_scorers()` priority chain
5. Verbose mode shows sub-score breakdown
6. Allow `verify_weight=0` for pure llm_judge fallback

**Files:** New `scorers/hybrid.py`, modified `bench_cli/compare.py`

### Phase 5: Build u18-resume-after-bad-attempt

Highest-value new task. Tests recovery from partially-correct prior attempt.

1. Create `tasks/universal/u18-resume-after-bad-attempt/`
2. Build canonical fixture: scheduler.py (unwired helper), duration.py (correct helper), ATTEMPT_NOTES.md (false lead)
3. task.py: `solver=multishot_solver(max_turns=5)`, `scorer=hybrid_scorer()`
4. verify.sh: checks scheduler imports from duration.py, tests would pass, no unnecessary changes
5. judge.md: discrete scale — reasoning quality, state inspection, dead-end avoidance
6. dataset.json: canonical + 2-4 variants (varying prior attempt quality, different false leads)
7. task_budgets.py: `reference_cost_usd=None` — populated later

**Files:** New task directory, modified `scorers/task_budgets.py`

### Phase 6: Build u17-dirty-workspace-triage

Tests triage in noisy repo without cleanup theater.

1. Create `tasks/universal/u17-dirty-workspace-triage/`
2. Build fixture: config.py (wrong timeout), http_client.py, test_timeout.py, distractor files
3. task.py: `solver=multishot_solver(max_turns=5)`, `scorer=hybrid_scorer()`
4. verify.sh: config.py has correct timeout, distractor files unchanged
5. judge.md: discrete scale — triage quality, scope discipline, efficiency
6. dataset.json: canonical + 3-5 variants
7. task_budgets.py: `reference_cost_usd=None` — populated later

**Files:** New task directory, modified `scorers/task_budgets.py`

### Phase 7: Extend f23 and f21

Merge u16/u19 into f23, u20 into f21 as new samples.

1. Add 3-4 samples to f23: buried constraints, constraint drift, combined
2. Build rich fixtures for new f23 samples
3. Add 2 samples to f21: stale summary, stale verification claim
4. Build rich fixtures for new f21 samples
5. Update both task.py to use `multishot_solver(max_turns=5)` where fixtures exist
6. Both already converted to discrete scale in Phase 1

**Files:** Modified dataset.json, task.py, new fixture dirs for f23 and f21

### Phase 8: Rework Existing Tasks (Opportunistic)

While infrastructure is fresh, improve tasks that would benefit from the new systems.

1. **Apply hybrid scoring** to existing judge-scored tasks where deterministic checks are possible (e.g., f22-error-spiral could verify "no unrelated files changed" deterministically)
2. **Apply multi-shot solver** to tasks where file exploration adds value (f1-multi-file-verify, f21-liars-codebase)
3. **Improve verify_sh tasks** where the discrete judge scale could add a qualitative dimension alongside the binary check
4. This phase is discretionary — each task evaluated individually for improvement ROI

**Files:** Various task directories, task.py files, potentially new verify.sh scripts

### Future Phase: Marathon Task (Placeholder)

- **Goal:** One 30-minute multi-phase task testing sustained agent reliability over 15+ tool call rounds
- **Requirements:** Extended timeout, parallel execution with other tasks, time-aware scheduling
- **Not in scope.** Design when Phase 1-8 are complete.

---

## Edge Cases & Gotchas

- **max_turns=1 must branch to bare generate()**: Not a parameter — a code-level branch. Tool schema injection changes model behavior even at 1 turn.
- **state.output is stale after tool loops**: Inspect doesn't update it. Solver must set `state.output.completion = state.messages[-1].text`.
- **Judge output format**: SCORE: 7.5 (0-10 scale), NOT SCORE: 0.75. `_parse_score()` divides by 10.
- **Tool sandboxing is non-negotiable**: read_file and list_directory chrooted to fixture dir. No path escapes.
- **verify_sh dual mode**: Model mode checks text patterns. Agent mode checks file state. Task designers choose which checks go where.
- **Fixture token budget**: 5+ files could be 3000-5000 tokens. Track per sample.
- **os.chdir() race condition**: `_resolve_task()` uses `os.chdir()` (not thread-safe). Fixture system uses absolute paths throughout.

---

## Anti-Patterns to Avoid

- **Don't output SCORE on 0-1 scale from rubrics.** Judge outputs 0-10. Parser divides by 10.
- **Don't inject tool schemas when max_turns=1.** Code-level branch, not parameter.
- **Don't create a fifth pillar.** Hybrid scoring is one correctness Score with metadata.
- **Don't hardcode fixture paths in task.py.** Use fixture system (metadata injection).
- **Don't make multi-shot the default.** Opt-in per task.
- **Don't carry forward bad patterns for compatibility.** If a task's verify.sh is weak, rewrite it. If a rubric is vague, sharpen it.

---

## Acceptance Checklist

### Infrastructure
- [ ] Multi-shot solver branches to bare generate() at max_turns=1 — verify by: diff eval scores
- [ ] Multi-shot solver with max_turns=5 produces tool calls, correct state.output — verify by: inspect eval log
- [ ] Hybrid scorer produces weighted mean with sub-scores in metadata — verify by: inspect Score.metadata
- [ ] Hybrid scorer discovered by compare.py — verify by: bench compare shows non-zero correctness
- [ ] All 15 judge.md rubrics use discrete 5-level format — verify by: grep for old format, zero hits
- [ ] Discrete scores cluster at {0.0, 0.25, 0.5, 0.75, 1.0} — verify by: score histogram
- [ ] Tool sandboxing blocks path escapes — verify by: test with `../../../etc/passwd`
- [ ] Rich fixture loading works — verify by: test fixture with 3 files, model reads them

### Tasks
- [ ] u18 built with 3-5 samples, hybrid scoring, rich fixtures — verify by: eval run produces sub-score metadata
- [ ] u17 built with 4-6 samples, hybrid scoring, rich fixtures — verify by: eval run produces sub-score metadata
- [ ] f23 extended with 3-4 new samples — verify by: f23 eval includes new samples
- [ ] f21 extended with 2 new samples — verify by: f21 eval includes new samples

### System
- [ ] 309+ tests pass — verify by: pytest
- [ ] EVAL-GUIDE.md updated — verify by: manual review
- [ ] CLAUDE.md updated — verify by: manual review

---

## Test Plan

- [ ] **Unit tests**: hybrid.py weighted combination, fixtures.py loading, multishot.py turn loop at max_turns=1 and 5, tool sandboxing, _parse_score() snap-to-discrete
- [ ] **Integration tests**: multi-shot + fixtures end-to-end, hybrid scorer + verify_sh + llm_judge, compare.py hybrid display
- [ ] **Regression tests**: Full eval on qwen-local after each phase. All tasks produce valid scores (no NaN, no errors).
- [ ] **Manual verification**: u17 and u18 produce score distributions that differentiate model tiers.

---

## Docs to Update

- [ ] `docs/EVAL-GUIDE.md` — u17, u18 descriptions, task count (36), hybrid + discrete scoring
- [ ] `CLAUDE.md` — Current Focus, task count, architecture (multi-shot, hybrid, fixtures)
- [ ] `scorers/judge_rubric_template.md` — New: canonical discrete 5-level rubric template

---

## Open Questions

- **Multi-shot solver: done signal?** → Resolved: use Inspect's native tool-use termination. No custom done signal.
- **verify_sh in model mode: what can it check?** → Text patterns. Task designers choose what's deterministic vs qualitative.
- **Fixture token budget?** → Out of scope. Track when building fixtures.
- **Should existing tasks opt into multi-shot?** → Phase 8 (discretionary). Evaluate per-task ROI.

---

## Council Synthesis

*(4-agent debate: Requirements Engineer, Developer, PM, AI Architect)*

### Convergence Points
- Discrete judge scale ships first — highest priority, lowest risk
- Judge must output 0-10 scale values (0, 2.5, 5, 7.5, 10)
- Hybrid scoring metadata approach: one Score, sub-scores in metadata
- Multi-shot solver has unvalidated model-compatibility risk — prerequisite gate required
- This is a first step toward context-hygiene coverage

### Key Disagreements

| Topic | Resolution |
|-------|------------|
| Multi-shot in scope? | **Kept** — tasks need it, prerequisite gate de-risks |
| Fixture system now or later? | **Now** — dual-mode parity requires it |
| Phase ordering | **Hybrid scoring before tasks, multi-shot when ready** |

---

## RedTeam Counter-Arguments

### Steelman
PRD correctly identifies three real deficits. Phased approach is sound. Phase 1 is genuinely low-risk. Two new tasks test novel capabilities with zero existing coverage.

### Fatal Flaws & Mitigations

| Counter-Argument | Severity | Mitigation |
|-----------------|----------|------------|
| state.output.completion stale after tool loops | Fatal | Solver sets state.output = ModelOutput(..., completion=state.messages[-1].text) |
| compare.py cannot discover hybrid scorer | Fatal | Add hybrid_scorer to _extract_from_scorers() priority chain |
| Tool schemas injected at max_turns=1 | Major | Code-level branch: if max_turns <= 1: return generate() |
| No security model for tool access | Major | Tool sandboxing: chroot to fixture dir, reject escapes |
| Judge outputs 0-1 scale instead of 0-10 | Major | Rubrics specify 0-10 values explicitly |
| Fixtures inject tokens with no discovery mechanism | Major | Solver injects initial file listing context |

---

## Science Cycle Documentation

### Hypotheses

| ID | Hypothesis | Verification |
|----|-----------|-------------|
| H1 | max_turns=1 produces identical results to bare generate() | Pairwise diff on all 34 tasks. Target: zero delta. |
| H2 | Discrete scale reduces judge variance | 15 tasks x 3 reps. Target: >= 3x variance reduction vs expected ±0.15 continuous ceiling. |
| H3 | Hybrid scoring more reliable than pure llm_judge | 5 tasks x 3 reps. Target: hybrid variance < 50% of judge variance. |
| H4 | u18 differentiates model quality | 3 model tiers. Target: score range >= 0.5. |
| H5 | Judge model respects discrete scale | 20 test prompts. Target: >= 90% output at discrete values. |

### Measurement Framework
- **Primary:** All tasks produce valid scores. New tasks differentiate models.
- **Secondary:** Variance reduction, score spread, rank ordering stability
- **Guardrails:** 309+ tests pass, runtime < 8 min per sample, judge cost <= 1.1x current

---

## Skill Integration Log

- **Thinking/IterativeDepth**: 8-lens analysis. 14 hidden requirements. Overlap quantification. Scoring variance analysis. Statistical power analysis.
- **Thinking/Council**: 4-agent debate, 3 rounds. Discrete scale priority, judge format, hybrid metadata approach. 10 specific changes.
- **Thinking/RedTeam**: 2 fatal flaws, 6 major flaws. All mitigated: state.output fix, compare.py discovery, tool sandboxing, max_turns bypass, scale format.
- **Thinking/Science**: 5 hypotheses with experiment designs. H1 highest risk, H3 highest value.

---

## Implementation Notes

*(Fill during implementation)*

- **Decision:**
- **Gotcha:**
- **Idea:**
