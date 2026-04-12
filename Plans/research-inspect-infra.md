# Inspect AI Infrastructure, Integration, and Operational Capabilities

**Researched:** 2026-04-10
**Domain:** Inspect AI evaluation framework operations
**Confidence:** HIGH

## Summary

Inspect AI (v0.3.205, released Apr 4, 2026) provides a mature operational layer for evaluation workflows. It includes a built-in web-based log viewer (`inspect view`), a CLI for log management, Pandas dataframe APIs for programmatic analysis, and hooks for experiment tracking (W&B, MLflow). The framework does NOT provide built-in statistical comparison or diff tools between runs -- that requires custom code using the dataframe API. The release cadence is extremely fast (near-daily minor versions), which has implications for pinning and stability.

**Primary recommendation:** Use Inspect's built-in log viewer as the dashboard for individual run inspection. Build `bench compare` using the Pandas dataframe API (`evals_df()`, `samples_df()`) with DuckDB for cross-run analysis. Do NOT try to build a custom log viewer -- Inspect View already handles this well.

---

## 1. EvalLog Viewer (`inspect view`)

**What it is:** A web-based viewer that runs locally, serving on port 7575 by default.

**Launch:** `inspect view` from CLI, or via the VS Code extension (Inspect AI extension).

**Configuration:**
- `--log-dir` -- point at any log directory
- `--port` / `--host` -- for remote access
- `--log-shared` -- for S3-backed logs

**What it shows:**
- Main summary panel: evaluation results overview, scores, token usage
- Sample details: drill into each sample with tabs for messages, scoring (input/target/answer/explanation), metadata
- History panel: browse past evals, see summaries of multiple log files
- Task info panel: dataset, solver, scorer, git revision, token usage
- Live progress tracking for running evaluations
- Python logging output captured inline
- Filtering by scores, sorting by sample or score

**VS Code integration:** Dedicated extension provides a Logs pane for browsing local or remote log files, inline log viewing in editor panes, and links to evaluation logs in task output.

**Verdict for Bench:** Use Inspect View as-is for day-to-day inspection of individual runs. No need to build a custom viewer. The VS Code integration is a bonus.

**Confidence:** HIGH -- verified against official docs at inspect.aisi.org.uk/log-viewer.html

---

## 2. Log Format Details

### Formats

Two log formats:
- **`.eval` (binary)**: Compact, ~1/8 the size of JSON. Supports incremental access. **Default since v0.3.46.**
- **`.json` (text)**: Human-readable, larger. Use for debugging or manual inspection.

### Log Structure (EvalLog)

```
EvalLog
  version: int
  status: str ("success" | "error" | "cancelled")
  eval: EvalSpec
    task: str
    model: str
    model_roles: dict
    revision: EvalRevision
      origin: str (git remote URL)
      commit: str (SHA)
      dirty: bool (uncommitted changes?)
    created: str (timestamp)
    packages: dict (dependency versions)
    config: dict (task config)
  plan: EvalPlan
    solvers: list (solver names/configs)
    scorer: dict
  results: EvalResults
    scores: list (per-scorer results with metrics)
  stats: EvalStats
    total_tokens: int
    model_usage: dict (per-model token breakdown)
  error: EvalError (if failed)
  tags: list[str]
  metadata: dict
  samples: list[EvalSample]
    id: str/int
    epoch: int
    input: str (prompt)
    target: str
    messages: list[Message] (full conversation history)
    output: ModelOutput
    scores: dict (per-scorer score + explanation)
    events: list[Event] (tool calls, model calls, etc.)
    metadata: dict
    error: str (if sample failed)
    usage: dict (token counts)
  reductions: dict (for multi-epoch aggregation)
```

### Schema

Print the JSON schema with: `inspect log schema`

### Format Handling

- NaN and Inf values are present in JSON -- need JSON5 parser for JS consumption
- Convert between formats: `inspect log convert logs --to eval --output-dir logs-eval`
- Stream conversion for large files: `--stream 10`
- Read programmatically: `read_eval_log()`, `read_eval_log_sample_summaries()`, `read_eval_log_samples()` (generator)

### Format Stability

No formal schema stability guarantee documented. The framework is at v0.3.x (pre-1.0), so breaking changes to the log format are possible between versions. The `version` field in EvalLog enables forward-compatible reading.

**Confidence:** HIGH -- verified against official docs at inspect.aisi.org.uk/eval-logs.html and `inspect log schema` documentation.

---

## 3. Logdir and Organization

### Default Location

`./logs` relative to the working directory.

### Configuration Methods

| Method | Example |
|--------|---------|
| CLI flag | `--log-dir ./experiment-log` |
| Python API | `eval(..., log_dir='./experiment-log')` |
| Environment variable | `INSPECT_LOG_DIR=./experiment-log` in `.env` |
| VS Code | Configured in extension settings |

### File Naming

Default pattern: `{timestamp}_{task}_{id}`

Customize with: `INSPECT_EVAL_LOG_FILE_PATTERN` env var
- Available fields: `{task}`, `{model}`, `{id}`, `{epoch}`
- Example: `INSPECT_EVAL_LOG_FILE_PATTERN={task}_{model}_{id}`

### Log Format Selection

- `--log-format=eval` or `INSPECT_LOG_FORMAT=eval`
- `--log-format=json` or `INSPECT_LOG_FORMAT=json`

### .env File Support

Inspect auto-loads `.env` files from current or parent directories via python-dotenv. Relative paths resolve from the `.env` file's location. Restart VS Code terminals after `.env` changes.

**Confidence:** HIGH -- verified against official docs.

---

## 4. Comparing Evaluations

### Built-in Comparison Tools

**None.** Inspect does NOT provide:
- A `diff` command for comparing two runs
- Built-in statistical comparison (no t-tests, bootstrap CI, effect sizes)
- A UI for side-by-side run comparison
- Built-in score diffing

### What Inspect DOES Provide

1. **Eval Sets** (`inspect eval-set` / `eval_set()`)
   - Run multiple evaluations together (e.g., across models or hyperparameters)
   - Resume incomplete sets from where they left off
   - Returns `list[EvalLog]` for programmatic analysis

2. **Dataframe API** (the primary comparison mechanism)
   - `evals_df("logs")` -- one row per eval run (~51 columns by default)
   - `samples_df("logs")` -- one row per sample
   - `messages_df("logs")` -- one row per message
   - `events_df("logs")` -- one row per event
   - All return Pandas DataFrames
   - Column groups for filtering: `EvalInfo`, `EvalModel`, `EvalResults`
   - Parallel reading: `parallel=True` for large log sets
   - DuckDB integration: `con.register('evals', evals_df("logs"))`

3. **Log listing** (`list_eval_logs()`)
   - Filter by status, task name, other criteria
   - Returns log paths for further processing

### What Bench Needs to Build

For `bench compare`, we need to build:
- Score extraction from multiple EvalLogs via `evals_df()` or `samples_df()`
- Per-sample score comparison across runs
- Statistical analysis (bootstrap CI, Cohen's d) -- not provided by Inspect
- DuckDB-backed query layer for fast cross-run analysis
- Text/CLI output of comparison results

**Confidence:** HIGH -- verified absence of comparison tools against official docs, verified dataframe API exists.

---

## 5. External Integrations

### Experiment Tracking Hooks

Inspect supports a **hooks system** for experiment tracking integrations:

| Integration | Status | Details |
|------------|--------|---------|
| Weights & Biases | Built-in example | `wandb_weave.py` hook example in docs |
| MLflow | Built-in examples | `mlflow_tracking.py` and `mlflow_tracing.py` hook examples |
| Langfuse | NOT mentioned | No built-in integration |
| Other | Via hooks API | Custom hooks via `@hooks` decorator and setuptools entry points |

### Storage/Filesystem Integrations

| System | Status | Details |
|--------|--------|---------|
| Local filesystem | Default | Standard file I/O |
| Amazon S3 | Built-in | Via s3fs/fsspec |
| Google Cloud Storage | Supported | Via fsspec |
| Azure Blob Storage | Supported | Via fsspec |
| Azure Data Lake | Supported | Via fsspec |
| DVC | Supported | Via fsspec |

Custom filesystems can be registered via setuptools entry points.

### Extension System

Inspect supports custom extensions via setuptools entry points for:
- Model APIs (`@modelapi`)
- Sandbox environments
- Approvers
- Storage systems (fsspec specs)
- Hooks (`@hooks`)

### Export Formats

No dedicated export format. Use the Dataframe API to convert to CSV/Parquet, or use `inspect log dump` to get JSON. No built-in export to MLflow/W&B artifact formats -- hooks handle logging during execution, not post-hoc export.

**Confidence:** HIGH for hooks/storage, MEDIUM for specific W&B/MLflow API details (based on examples, not tested).

---

## 6. Configuration System

### Configuration Layers (highest priority wins)

1. CLI flags / Python `eval()` arguments (highest)
2. Environment variables / `.env` files
3. `task_with()` overrides
4. Task definition defaults (lowest)

### Key Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `INSPECT_EVAL_MODEL` | Default model | `anthropic/claude-sonnet-4-20250514` |
| `INSPECT_LOG_DIR` | Log directory | `./logs` |
| `INSPECT_LOG_FORMAT` | Log format | `eval` or `json` |
| `INSPECT_LOG_LEVEL` | Console verbosity | `warning`, `http`, `debug` |
| `INSPECT_EVAL_MAX_RETRIES` | Max retries | `5` |
| `INSPECT_EVAL_MAX_CONNECTIONS` | Concurrent API calls | `20` |
| `INSPECT_EVAL_LOG_FILE_PATTERN` | Log filename pattern | `{task}_{model}_{id}` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-...` |
| `GOOGLE_API_KEY` | Google API key | `AI...` |

### Config File Support

YAML or JSON config files for:
- `--generate-config` -- generation parameters (useful for reproducibility)
- `--model-config` -- model-specific arguments
- `--task-config` -- task arguments
- `--solver-config` -- solver arguments
- `--model-cost-config` -- model pricing data

### .env File Auto-Loading

Python-dotenv auto-loads `.env` from current or parent directories. Relative paths resolve from `.env` file location.

**Confidence:** HIGH -- verified against official docs at inspect.aisi.org.uk/options.html.

---

## 7. CI/CD Usage

### Official GitHub Action

No dedicated GitHub Action exists. Use standard workflow steps.

### Recommended Pattern

```yaml
name: Run Inspect AI Evals
on:
  pull_request:
    branches: [main]
  workflow_dispatch:

jobs:
  run-evals:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install inspect-ai
      - run: inspect eval my_eval.py --model anthropic/claude-sonnet-4-20250514
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: inspect-logs
          path: logs/
```

### Key Considerations

- API keys in GitHub Secrets, mapped to env vars
- `if: always()` on artifact upload to capture logs even on failure
- Pin inspect-ai version for reproducibility
- Consider cheaper models for PR checks
- Use `--log-format=eval` for smaller artifacts
- Sandbox considerations for untrusted model code

**Confidence:** MEDIUM -- based on community patterns and Inspect CLI design. No official CI/CD guide in docs, but the approach is straightforward.

---

## 8. Performance

### Parallelism Controls

| Setting | Default | Purpose |
|---------|---------|---------|
| `--max-connections` | 10 | Concurrent API connections per model |
| `--max-samples` | max_connections + 1 | Concurrent samples per task |
| `--max-tasks` | 1 | Parallel tasks |
| `--max-subprocesses` | os.cpu_count() | Parallel subprocesses |
| `--max-sandboxes` | 2 * os.cpu_count() | Parallel sandbox environments |
| `--max-dataset-memory` | unlimited | Memory limit before paging to disk |

### Rate Limiting

- Automatic exponential backoff: initial 3 seconds, up to 25 minutes
- Monitor retries: `--log-level=http` or `inspect trace http`
- Cap retries: `--max-retries`, `--timeout`
- Tune `--max-connections` to reduce retries (too high = more rate limit hits)

### Batch Mode

Provider-native batch APIs for OpenAI, Anthropic, Google, xAI, Together AI:
- Enable: `--batch` or `batch=True`
- 50% token cost savings
- Longer processing times (up to 24 hours)
- Best for evaluations with few sequential generations
- Bad for multi-turn evaluations (path dependency extends wait times)
- Configurable: batch size, send delay, tick interval, max in-flight batches

### Large Dataset Handling

- `--max-dataset-memory` pages samples to disk when exceeded
- Parallel log reading: `parallel=True` in dataframe functions
- Binary `.eval` format is ~8x smaller than JSON
- Incremental access for `.eval` format

### Async Backend

- Default: asyncio
- Switchable: `INSPECT_ASYNC_BACKEND` environment variable

**Confidence:** HIGH -- verified against official docs at inspect.aisi.org.uk/parallelism.html and models-batch.html.

---

## 9. Versioning & Reproducibility

### Automatic Capture

Every EvalLog automatically records:
- **Git revision**: `eval.revision` with `origin` (remote URL), `commit` (SHA), `dirty` (bool)
- **Package versions**: `eval.packages` dict of dependency versions
- **Task config**: Full solver/scorer/dataset configuration in `eval.config`
- **Model details**: Model name, provider, generation parameters
- **Timestamps**: Creation time for each eval run

### Model Version Pinning

- Model names like `gpt-4-turbo` are aliases that resolve differently over time
- Pin with explicit names: `openai/gpt-4-turbo-2024-04-09`
- Cache keys include model name, so pinned models get separate cache entries

### Caching for Determinism

- Local cache for all models (keyed on model, prompt, config, tools)
- Provider-level cache for Anthropic (`cache-prompt`, default "auto" when tools defined)
- Default expiry: 1 week, configurable via `CachePolicy(expiry='3h')`
- Epoch-scoped by default: distinct generations per epoch
- Management: `inspect cache list`, `inspect cache prune`, `inspect cache clear`

### Post-Hoc Metadata

- `edit_eval_log()` to update tags/metadata after the fact
- Does not invalidate original results

### Reproducibility Best Practices

1. Pin inspect-ai version in requirements
2. Pin model versions with explicit dated names
3. Commit all changes before production evals (avoid `dirty` state)
4. Use `--generate-config` YAML to bundle generation parameters
5. Rely on cache for deterministic scorer iteration

**Confidence:** HIGH -- verified against official docs and web search results.

---

## 10. Release Cycle & Community

### Current Version

**inspect-ai 0.3.205** (released April 4, 2026), requires Python >=3.10.

### Release Frequency

Extremely high cadence:
- Near-daily minor version releases during active development
- Versions progressed from 0.3.130 (Sep 2025) to 0.3.205 (Apr 2026) -- ~75 versions in 7 months
- Average: ~2-3 releases per week

### Breaking Changes Policy

No documented breaking changes policy. The framework is pre-1.0 (v0.3.x), so:
- API changes happen without major version bumps
- Log format may evolve between versions
- Pin your version for production use

### Community

| Metric | Value |
|--------|-------|
| GitHub stars | ~1,900 |
| Total commits | ~5,150 |
| Open issues | ~106 |
| Maintainer | UK AI Security Institute (AISI) |
| Repo | github.com/UKGovernmentBEIS/inspect_ai |

### Implications for Bench

- Pin inspect-ai version in requirements.txt
- Test before upgrading -- API may change
- The `version` field in EvalLog enables forward-compatible reading
- Active development means features we need (dataframe API, hooks) are well-maintained

**Confidence:** HIGH -- verified against PyPI and GitHub.

---

## Architecture Implications for Bench

### What Inspect Provides (use as-is)

1. **Log viewer** -- `inspect view` for individual run inspection
2. **Log storage** -- `.eval` binary format, configurable logdir
3. **Log reading** -- `read_eval_log()`, dataframe API
4. **Configuration** -- `.env` files, environment variables
5. **Caching** -- automatic model response caching for determinism
6. **Git tracking** -- automatic commit/branch/dirty capture in logs
7. **Eval sets** -- batch running multiple evaluations
8. **Hooks** -- W&B/MLflow integration points

### What Bench Must Build

1. **`bench run`** -- thin wrapper around `inspect eval` with our defaults
2. **`bench compare`** -- uses `evals_df()`/`samples_df()` + DuckDB for cross-run analysis
3. **`bench history`** -- uses `list_eval_logs()` to show run history
4. **Statistical analysis** -- bootstrap CI, Cohen's d (not in Inspect)
5. **Scoring framework** -- custom scorers for our task format
6. **Task format parser** -- task.toml + prompt.md + verify.sh loader
7. **SQLite index** -- optional fast query layer on top of EvalLog files
8. **CLI interface** -- Typer/Click CLI wrapping Inspect commands

### Don't Build

- Custom log viewer (use `inspect view`)
- Log format (use Inspect's `.eval` format)
- Model response caching (use Inspect's built-in cache)
- API rate limiting (use Inspect's built-in backoff)
- Log file management (use Inspect's logdir + naming)

---

## Sources

### Primary (HIGH confidence)
- inspect.aisi.org.uk/log-viewer.html -- Log viewer documentation
- inspect.aisi.org.uk/eval-logs.html -- Log format and management
- inspect.aisi.org.uk/options.html -- Configuration system
- inspect.aisi.org.uk/parallelism.html -- Performance tuning
- inspect.aisi.org.uk/models-batch.html -- Batch mode
- inspect.aisi.org.uk/dataframe.html -- Dataframe API for analysis
- inspect.aisi.org.uk/extensions.html -- Hooks and integrations
- inspect.aisi.org.uk/eval-sets.html -- Eval sets
- inspect.aisi.org.uk/caching.html -- Caching and reproducibility
- pypi.org/project/inspect-ai/ -- Current version info
- github.com/UKGovernmentBEIS/inspect_ai -- Repository metrics

### Secondary (MEDIUM confidence)
- Web search results for CI/CD patterns -- community patterns, not official docs
- Web search results for W&B/MLflow hooks -- based on example code in docs

### Tertiary (LOW confidence)
- Langfuse integration -- assumed absent based on docs not mentioning it; could exist as community extension
