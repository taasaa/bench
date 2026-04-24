# Architectural Refactor Backlog

**Status:** draft  
**Date:** 2026-04-24  
**Scope:** follow-up refactoring tasks from quick architecture pass  
**Excluded:** packaging/installability and AGENT.md documentation drift

This document captures the current architectural findings that should become
separate refactoring tasks. Each section is intentionally scoped as an
independent piece of work so future changes can be planned, implemented, and
verified one at a time.

The current project state is operationally healthy:

- `python -m pytest -q`: `532 passed, 1 skipped`
- `ruff check bench_cli scorers tests`: `All checks passed!`

The remaining issues are not emergency defects. They are boundary, semantics,
and maintainability risks that will become more expensive as Bench grows.

---

## Task 1: Make Task Root Resolution Explicit

### Finding

Task discovery is still coupled to the process working directory:

```python
tasks_root = Path("tasks")
```

This appears in `bench_cli/run/core.py` inside `_discover_tasks()`. It means
`bench run` works when launched from the repository root, but task discovery is
implicitly dependent on where the shell happens to be.

### Why This Matters

Bench has two identities:

1. A repository-local evaluation harness.
2. A Python CLI package with a `bench` console entry point.

Those identities have different path expectations. A repo-local tool can assume
`./tasks`. A package CLI generally cannot. Right now, the code behaves as a
repo-local tool, while the project shape suggests a reusable command.

This ambiguity leaks into multiple places:

- `_discover_tasks()` looks for `tasks` relative to CWD.
- `_resolve_task()` receives relative task specs produced by discovery.
- Fixture injection depends on task directories derived from those specs.
- Docker and local agent behavior assumes fixture paths were resolved correctly.

The risk is not just "run from another directory and get no tasks." The deeper
risk is silent mis-targeting: if another directory contains a `tasks/` tree, the
CLI may discover the wrong suite.

### Design Goal

There should be one explicit source of truth for the Bench project root and task
root. Every caller should either:

- use that default root, or
- intentionally pass a different root.

### Suggested Mitigations

#### Option A: Repo-Local Root Detection

Resolve the root by walking upward from CWD until a Bench marker is found:

- `pyproject.toml` with `[project].name == "bench"`
- or a required `tasks/` plus `bench_cli/` layout
- or a `.bench-root` marker file if one is added later

Then set:

```python
bench_root = find_bench_root(Path.cwd())
tasks_root = bench_root / "tasks"
```

This keeps the repo-local workflow, but makes the assumption explicit and more
robust.

#### Option B: Configurable Root

Add a root option or environment variable:

```bash
bench run --bench-root /path/to/bench
BENCH_ROOT=/path/to/bench bench run
```

This is useful if users maintain multiple task suites or run Bench from
automation that does not control CWD.

#### Option C: Hybrid

Use automatic root detection by default, with an override:

1. CLI `--bench-root`
2. `BENCH_ROOT`
3. upward search from CWD
4. clear error if no root is found

This is the most flexible and probably the best long-term shape.

### Refactor Shape

Create a small root-resolution helper, for example:

```python
def resolve_bench_root(root: str | Path | None = None) -> Path:
    ...

def resolve_tasks_root(root: str | Path | None = None) -> Path:
    return resolve_bench_root(root) / "tasks"
```

Then thread the root through:

- `_discover_tasks(tier, ..., bench_root=None)`
- task listing
- `_resolve_task()` if relative specs are still allowed
- tests that create temporary task trees

### Acceptance Criteria

- Running `bench run --list-tasks` from the repo root still works.
- Running from a subdirectory inside the repo still finds the repo task suite.
- Running from outside the repo produces a clear error or works with
  `--bench-root`.
- Existing tests remain green.
- Add at least one test covering non-root CWD behavior.

### Risks

- Test fixtures currently assume simple relative `tasks` paths.
- Inspect task loading may still need task-local CWD for relative
  `dataset.json` paths.
- Too much configurability can obscure the common local workflow.

The mitigation is to keep the public behavior simple: default to the current
repo task suite, but make the root deterministic.

---

## Task 2: Split Task Loading, Metadata Injection, Fixture Mounting, and Config Defaults

### Finding

`_resolve_task()` in `bench_cli/run/core.py` is a dense integration point. It
currently does all of the following:

- turns a spec into an absolute path
- imports a Python module with `importlib`
- registers it in `sys.modules`
- finds the Inspect `@task` factory
- temporarily changes CWD so `dataset.json` resolves
- calls the task factory
- mutates each sample's metadata
- injects agent metadata
- resolves fixture paths
- mutates `sample.files` for Docker workspace mounting
- adds an empty workspace file when no fixture exists
- constructs a new `GenerateConfig`
- reconstructs an Inspect `Task` field by field

Each individual operation is understandable. The issue is that they are all
hidden behind one function named `_resolve_task()`.

### Why This Matters

This function is on the critical path for every eval run. It is also coupled to
several independent domains:

- Inspect task loading
- Bench scoring metadata
- fixture conventions
- Docker sandbox initialization
- local and Docker agent modes
- model timeout defaults

When a future change touches any one of those domains, it has to reason through
the whole function. That raises the chance of accidental regressions.

The current implementation also reconstructs an Inspect `Task` by copying many
attributes manually. That is fragile because it depends on the exact fields
available on Inspect's `Task` object. A future Inspect release could add or
change task attributes, and Bench might silently drop them.

### Design Goal

The run pipeline should make each stage explicit:

1. Load the task.
2. Enrich samples with Bench metadata.
3. Prepare fixture/workspace files.
4. Apply default eval config.
5. Return the final task object.

Each stage should be small enough to test directly.

### Suggested Mitigations

#### Step 1: Extract Pure Helpers

Start by extracting without changing behavior:

```python
def load_task_from_spec(spec: str) -> tuple[Task, Path]:
    ...

def inject_bench_metadata(task: Task, task_dir: Path, agent_context: AgentContext | None) -> None:
    ...

def attach_fixture_workspace(task: Task, task_dir: Path) -> None:
    ...

def with_default_generate_config(task: Task) -> Task:
    ...
```

This creates seams for tests without changing the external CLI behavior.

#### Step 2: Introduce an Agent Context Object

Instead of passing `agent`, `agent_mode`, and `cc_model` separately through
metadata injection, use a small dataclass:

```python
@dataclass(frozen=True)
class AgentContext:
    agent: str
    mode: str
    cc_model: str | None = None
```

This reduces parameter drift and makes future agent metadata additions more
obvious.

#### Step 3: Avoid Field-by-Field Task Reconstruction If Possible

Investigate whether Inspect provides a supported way to update config or clone
a task. If not, isolate the reconstruction in one helper:

```python
def clone_task_with_config(task: Task, config: GenerateConfig) -> Task:
    ...
```

That keeps the fragility in one named place, with tests around it.

### Acceptance Criteria

- `_resolve_task()` becomes an orchestration wrapper, not the implementation of
  every step.
- Fixture mounting behavior remains unchanged.
- `bench_task_dir` still reaches `state.metadata`.
- Docker agent workspace behavior still works.
- Tests cover each extracted helper or the major observable outcomes.
- Full test suite remains green after each extraction.

### Risks

- Relative `dataset.json` resolution depends on task-local CWD. Do not remove
  that behavior until there is a verified Inspect-native alternative.
- Inspect task objects may not be safe to mutate in every context. Preserve the
  current mutation behavior initially, then improve only with tests.
- Fixture mounting is easy to break for agent modes because it relies on
  `sample.files` shape.

### Recommended First PR

Do the smallest extraction first:

1. Extract task module loading into `load_task_from_spec()`.
2. Extract sample metadata injection into `inject_bench_metadata()`.
3. Leave fixture mounting and config cloning inside `_resolve_task()`.
4. Run tests.

That reduces cognitive load while avoiding a large behavioral refactor.

---

## Task 3: Fix Compare `latest` Semantics

### Finding

`load_compare_data(log_dir, latest=N)` currently slices the newest `N` logs
globally:

```python
infos = list_eval_logs(log_dir=str(log_path), descending=True)
if latest is not None:
    infos = infos[:latest]
```

This does not match the user-facing meaning implied by the CLI and docs:

```bash
bench compare --latest 1
```

The expected meaning is usually "latest run per task/model" or "latest N runs
per task/model." The current implementation means "latest N log files total."

### Why This Matters

`bench run` calls:

```python
load_compare_data(log_dir, latest=1)
```

after a batch run. If Inspect writes one EvalLog per task, `latest=1` can show
only the newest task from the batch, not the full result set from the run.

That makes the automatic compare output potentially misleading. A user can run
a full tier and see a compare table that appears complete but only contains a
single task or incomplete subset.

This is a semantic bug more than a code organization issue.

### Design Goal

The compare layer should support clear selection modes:

- latest log files globally
- latest run per task/model
- latest N runs per task/model
- maybe latest run group if Inspect exposes a shared run identifier

The CLI should name and document whichever mode it uses.

### Suggested Mitigations

#### Option A: Change `latest` To Mean Per Pair

Keep the public option name but change implementation:

1. Read logs newest first.
2. Group by `(task, model)`.
3. Keep the first `N` logs per group.
4. Aggregate from those selected logs.

This matches the existing help text better.

#### Option B: Split Into Two Parameters

Make the distinction explicit:

```python
load_compare_data(log_dir, latest_per_pair=1)
load_compare_data(log_dir, latest_logs=None)
```

CLI examples:

```bash
bench compare --latest 1          # latest per task/model
bench compare --latest-logs 20    # newest 20 logs globally
```

This avoids overloading one option.

#### Option C: Run-Aware Compare

If Inspect EvalLogs can be associated with the same batch invocation, compare
should select by batch/run identity. That would make post-run auto-compare exact:

```python
load_compare_data_for_run(log_dir, run_id)
```

This may be more work and depends on Inspect metadata availability.

### Acceptance Criteria

- After a batch eval, auto-compare includes all tasks from that batch or clearly
  says it is showing a partial/global-latest view.
- `bench compare --latest 1` behavior is documented and tested.
- Add tests with multiple tasks and multiple models where global latest slicing
  would produce the wrong matrix.
- Existing compare output remains compatible unless intentionally changed.

### Risks

- Changing `--latest` semantics may surprise anyone relying on global slicing.
- Reading more logs may make compare slower in large log directories.
- If multiple reruns exist for the same task/model, aggregation rules must be
  explicit.

### Recommended First PR

Add a failing test that demonstrates the current ambiguity:

- create fake EvalLogs or mocked log infos for two tasks
- call `load_compare_data(..., latest=1)`
- assert that latest per task/model behavior is desired

Then implement the grouping behavior.

---

## Task 4: Isolate Legacy Manual Pricing From Compare Extraction

### Finding

`bench_cli/compare/core.py` contains `_MANUAL_PRICES` and `_recalc_cost()`.
Those are used to recover cost values for historical logs whose scorer metadata
was missing or had pre-fix price units.

This fallback is useful, but it is mixed directly into compare extraction. The
compare module now owns both:

- reading and formatting EvalLog comparison data
- legacy price repair logic

### Why This Matters

Pricing already has a dedicated module:

- `bench_cli/pricing/price_cache.py`
- `bench_cli/pricing/litellm_config.py`
- `bench_cli/pricing/model_aliases.py`
- `scorers/price_ratio.py`

Keeping a second price table inside compare creates a conceptual split:

- current eval scoring uses one pricing path
- historical compare repair uses another

That makes future pricing changes harder. A contributor changing model pricing
must know to check compare internals as well as pricing modules.

It also makes compare harder to test because cost extraction is no longer just
"read the log"; it can synthesize data from manual model aliases.

### Design Goal

Compare should not own pricing policy. It should either:

- read cost values that are already present in logs, or
- call a clearly named legacy repair helper.

Historical compatibility is valid, but it should be isolated and documented as
historical compatibility.

### Suggested Mitigations

#### Option A: Move Manual Prices To Pricing Module

Create a module such as:

```python
bench_cli/pricing/legacy_prices.py
```

with:

```python
def recalc_legacy_cost(model_alias: str, input_tokens: int, output_tokens: int) -> float | None:
    ...
```

Then compare imports that helper. The manual table is still code, but it lives
with pricing concerns.

#### Option B: Move To Data File

Store historical price repair entries in JSON or YAML:

```text
bench_cli/pricing/config/legacy_prices.json
```

This makes it clearer that the values are data, not compare logic.

This is only worth doing if the table is expected to grow.

#### Option C: Drop Automatic Repair Behind A Flag

If historical logs are not important forever, compare could stop repairing by
default and expose an explicit migration path:

```bash
bench results migrate-costs --legacy-prices
```

This is cleaner long term but heavier operationally.

### Acceptance Criteria

- `compare/core.py` no longer defines manual model prices.
- Cost repair behavior remains tested.
- The fallback is named as legacy or historical repair.
- Current `price_ratio_scorer` behavior is unchanged.
- Compare still displays old logs correctly if that remains a requirement.

### Risks

- Moving the table can break historical result display if tests do not cover it.
- A data-file approach adds package data concerns.
- Removing repair behavior may make old reports look worse or incomplete.

### Recommended First PR

Move `_MANUAL_PRICES` and `_recalc_cost()` into
`bench_cli/pricing/legacy_prices.py`, import the helper from compare, and add a
small unit test for the helper. This preserves behavior while cleaning the
boundary.

---

## Task 5: Tighten Agent Solver Boundaries And Workspace Parity

### Finding

The agent abstraction is improved by the new `--cc-model` split, but local and
Docker agent execution still differ in important ways.

Current shape:

- `AgentConfig` defines local CLI command pieces and a `docker_solver` name.
- `local_agent()` runs the CLI as a subprocess on the host.
- `docker_agent()` imports inspect-swe solvers and hardcodes the solver mapping.
- Docker agent mode sets `cwd="workspace"`.
- Local agent mode does not set subprocess `cwd` to the sample fixture
  workspace.

The result is that local and Docker modes may evaluate different operating
conditions even when they are conceptually the same task.

### Why This Matters

Bench is meant to compare model and agent behavior. For agent evals,
environment differences can dominate behavior:

- what files are visible
- current working directory
- whether project instructions are loaded
- whether fixtures are copied or directly referenced
- whether the agent can mutate the real repository

Docker mode starts in a `workspace` populated from `sample.files`. Local mode
passes only the prompt to the CLI and lets the host environment decide the rest.
That makes local agent scores partly a measurement of the developer machine,
not just the agent.

The hardcoded Docker solver mapping is smaller, but related: agent config says
it owns `docker_solver`, while `docker_agent()` does not use that field. That
means adding a new agent still requires edits in multiple places.

### Design Goal

Agent execution should have an explicit environment contract:

- what working directory the agent starts in
- what files it can see
- how fixture files are materialized
- which harness instructions are active
- how model overrides are passed

Local and Docker modes do not need to be identical, but their differences should
be intentional and visible.

### Suggested Mitigations

#### Option A: Document And Preserve Mode Differences

If local mode is intentionally "run the host agent exactly as the user would,"
then codify that:

- local mode uses host CWD and host harness
- Docker mode uses isolated fixture workspace
- local scores are not directly comparable to Docker scores

This is the lowest-code option, but it limits result interpretability.

#### Option B: Add Local Fixture Workspace Materialization

For local agent evals:

1. Create a temporary workspace per sample.
2. Copy fixture files into it.
3. Run the agent subprocess with `cwd=temp_workspace`.
4. Clean up after the sample unless debugging is enabled.

This makes local mode closer to Docker mode while avoiding Docker overhead.

#### Option C: Split Modes More Explicitly

Rename or clarify modes:

- `local-host`: real host environment
- `local-workspace`: temp fixture workspace
- `docker`: isolated container
- `harness`: isolated container plus injected instructions

This avoids hiding major environmental differences under one `local` name.

#### Option D: Use `docker_solver` From AgentConfig

Replace the hardcoded map in `docker_agent()` with a registry keyed by
`AgentConfig.docker_solver`, or store the factory mapping in one place.

This makes adding future agents less error-prone.

### Acceptance Criteria

- Agent mode semantics are explicitly represented in code, not just CLI prose.
- Local agent tests cover fixture workspace behavior or explicitly assert host
  CWD behavior.
- Docker solver selection uses the registry consistently.
- `--cc-model` remains scoped to Claude Code local/bare modes unless expanded
  intentionally.
- Existing agent tests remain green.

### Risks

- Creating temp workspaces for local mode can change existing local-agent
  results.
- Some agents rely on project-level config in the original CWD.
- Cleanup must not delete user files.
- Host subprocess behavior can be hard to test without mocking.

### Recommended First PR

Start with the low-risk registry cleanup:

1. Make `docker_agent()` use `AgentConfig.docker_solver`.
2. Add a test proving the configured solver name is respected.
3. Do not change local workspace behavior yet.

Then handle workspace parity as a separate follow-up.

---

## Sequencing Recommendation

The tasks are intentionally independent, but this order minimizes risk:

1. **Compare latest semantics** — smallest surface, likely user-visible bug.
2. **Legacy pricing isolation** — boundary cleanup with low behavior risk.
3. **Task root resolution** — important but touches CLI/test setup.
4. **Agent solver boundaries** — split into registry cleanup first, workspace
   parity later.
5. **Task resolution decomposition** — most valuable structurally, but touches
   the central eval path and should be done incrementally.

Do not combine these into one refactor. Each one should have its own tests and
its own green test run before moving to the next.

