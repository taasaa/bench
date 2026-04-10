# Plan: Update PRD-DRAFT.md with Review Fixes

## Context

5 parallel review agents found 19 issues in the PRD — 4 critical, 3 high, 8 medium, 4 minor. The user also provided key reframing: model eval isn't just standalone — it answers "which model works better with MY setup?" Agent eval is the core value, not a Phase 2 add-on. Both modes need to be in the MVP.

## File to modify

`/Users/rut/dev/bench/PRD-DRAFT.md`

## Changes (section by section)

### 1. Section 1 (First Principles) — No changes
Fine as-is.

### 2. Section 2 (Requirements) — No changes
Fine as-is.

### 3. Section 3 (Architecture) — Major edits

**A. Rewrite "Two eval modes" subsection:**
- Reframe: both modes answer "how does X perform on my tasks?" where X = model, agent, or combo
- Three questions: (1) which model on my tasks, (2) which setup, (3) which model + setup combo
- Model eval IS in MVP — it tests your tasks, not MMLU generics

**B. Add "Agent eval protocol" subsection** — the biggest gap:
- Claude Code: `claude -p --output-format json --max-turns N "PROMPT"`
- Per-task workspace: copy fixtures in, run agent, capture JSON stdout + filesystem diff
- Verification: `verify.sh` runs against workspace — exit 0 = pass
- Workspace reset between tasks (fresh copy)
- Timeout per task (configurable, default 5 min)

**C. Fix "Why Inspect AI as foundation":**
- Change `model_graded()` → `model_graded_qa()` / `model_graded_fact()`

**D. Fix "What Bench adds":**
- Remove "Agent runner — point at any agent command" vagueness
- Replace with specific protocol described above
- Note: Inspect AI handles model eval natively; Bench builds agent eval on top

### 4. Section 4 (Tiers) — Simplify
- Reduce to 2 tiers for Phase 1-2: **quick** (<30s, 5 tasks, deterministic) and **full** (2-5 min, 15-20 tasks, all scoring)
- Adversarial = task category, not execution tier
- Note: expand to 3-4 tiers when task count justifies it

### 5. Section 5 (Tasks) — Minor fixes
- No changes to task lists (those get derived from user's actual work separately)

### 6. Section 6 (Scoring) — Major fixes

**A. Fix safety scoring formula:**
```
task_score = (correctness * 0.67 + efficiency * 0.33) * safety_gate
```
where `safety_gate` is binary 0 or 1. Clean, no contradiction.

**B. Fix LLM-as-judge citation:**
- Replace "CALM framework (ICLR 2025)" with "Zheng et al. (2023) and LLM-as-judge best practices"

**C. Fix judge model family rule:**
- Change to: "Cross-family recommended; same-family with temp=0 is acceptable for personal use"

**D. Statistical comparison — honesty cut:**
- Remove bootstrap CI, Cohen's d, Benjamini-Hochberg from Phase 1-2
- Phase 1-2: raw scores, per-task breakdown tables
- Phase 3+: add bootstrap CI when 30+ tasks exist

**E. Value score — remove:**
- Delete the `correctness / (token_cost_usd * latency_seconds)` formula
- Replace with: "Report correctness, cost, and latency as independent axes"

### 7. Section 7 (Result Schema) — Minor fix
- Update vs_baseline to remove `significant` field (deferred to Phase 3)

### 8. Section 8 (CLI) — Minor trim
- Remove `bench leaderboard` (deferred)
- Remove `bench trend` (deferred)
- Keep: run, compare, history, baseline, tasks, report

### 9. Section 9 (Tech Stack) — Major rewrite

**A. Fix model access:**
- Remove entire "LiteLLM gateway" subsection
- Replace with "Inspect AI native multi-provider support"
- Providers: Anthropic, OpenAI, Google, Ollama (local) — all via Inspect's built-in adapters
- LiteLLM optional: can use via Inspect's OpenAI Compatible API if desired, but not required
- API keys configured via environment variables

**B. Fix dependencies:**
- Remove LiteLLM from implied dependencies
- Keep: inspect-ai, click/typer, sqlite3, scipy (deferred), rich

**C. Remove Docker references** from Phase 2 row in external tools table

**D. Fix TerminalBench reference** — replace with SWE-bench, OSWorld, AgentBench

### 10. Section 10 (Features Checklist) — Update
- Move leaderboard, value score, drift detection, harness diff to Phase 4+
- Move LLM judge calibration to Phase 3
- Update checkboxes to match new phase structure

### 11. Section 11 (Implementation Phases) — Major restructure

New phases:

**Phase 1: MVP (Model + Agent eval, deterministic scoring)**
- Install Inspect AI, configure 2 providers
- Define task schema (prompt + fixtures + verify.sh)
- Write 15-20 tasks across 3 categories, all with deterministic verification
- Agent eval via `claude -p` protocol
- Model eval via Inspect AI native
- Basic CLI: `bench run`, `bench compare`
- Results: Inspect EvalLogs + simple comparison table
- Outcome: Answer "which model/setup is better on MY tasks?"

**Phase 2: Infrastructure**
- CLI expansion (baseline create/list/diff, history, report)
- SQLite index over EvalLogs
- Additional scorer types (LLM judge with calibration protocol)
- 30-50 tasks, all 5 categories
- Bootstrap CI for comparisons (now have enough data)
- Outcome: Full regression detection with historical context

**Phase 3: Intelligence**
- Per-category recommendations
- Drift detection
- Leaderboard
- External benchmark integration (inspect_evals, SWE-bench)
- Langfuse/MLflow export
- Outcome: Data-driven model selection

### 12. Section 12 (Open Questions) — Updates
- Fix Docker decision: "No Docker in Phase 1-2. Evaluate for Phase 3 terminal tasks."
- Remove "All questions resolved" note about TerminalBench → update with real benchmarks
- Update resolved #9 to reflect unified eval framing

### 13. Section 13 (What This Is NOT) — No changes

### 14. Section 14 (Research Appendix) — Fix citations
- Fix 14.B: Replace TerminalBench/Harbor with SWE-bench, OSWorld, AgentBench
- Fix 14.C: Replace "CALM framework (ICLR 2025)" with Zheng et al. (2023)
- Fix model_graded() references in 14.A
- Add note about Inspect AI native providers (not LiteLLM)

### 15. Update header
- Status: "Draft v4 — post-review fixes"
- Date: 2026-04-08

## Verification

- All 4 critical findings from PRD-REVIEW.md addressed
- All 3 high findings addressed
- No contradictions remain (safety formula, Docker, judge family)
- Phase 1 includes both model eval AND agent eval per user's requirement
- All fabricated/unverifiable citations replaced with real ones
