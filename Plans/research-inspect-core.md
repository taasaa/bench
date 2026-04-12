# Inspect AI Core Framework -- Deep Feature Research

**Researched:** 2026-04-10
**Domain:** Inspect AI evaluation framework (v0.3.205)
**Confidence:** HIGH (sourced from official docs, GitHub source, and PyPI)

## Summary

Inspect AI v0.3.205 is a substantially more capable framework than the tasks/solvers/scorers pattern we currently leverage. Beyond the core evaluation pipeline, Inspect provides a complete ecosystem for running, analyzing, monitoring, and visualizing evaluations. The most impactful features we are NOT currently using fall into these categories: (1) a rich Hooks system for custom lifecycle events, (2) a powerful Dataframe analysis API with direct DuckDB integration, (3) built-in caching with both local and provider-side strategies, (4) comprehensive error handling with per-sample retries and multiple execution limits, (5) eval sets for batch-running many tasks with automatic retries, and (6) structured output support for enforcing JSON schemas on model responses.

**Primary recommendation:** Bench should adopt Inspect's hooks system for real-time scoring analytics, use the dataframe API for result comparison, leverage caching for development iterations, and use eval sets for tier-based batch execution.

---

## 1. Logging & Analytics

### What We Know
- EvalLog JSON captures: version, status, eval spec, plan, results, stats, errors, tags, metadata, samples
- Two formats: `.eval` (binary, compressed, 1/8 size of JSON -- default since v0.3.46) and `.json` (text)

### What We're Missing

**Log Viewer (`inspect view`)**
- Interactive web-based dashboard for exploring eval logs
- Shows task summaries, individual sample drill-downs, message histories, scoring details
- Live view tracks progress during running evaluations
- Supports filtering by score (correct/incorrect), sorting
- Can be bundled as static HTML for deployment (GitHub Pages, S3)
- Accessible via VS Code extension or CLI

**Log File API (Python)**
```python
from inspect_ai.log import (
    list_eval_logs,           # enumerate logs in a directory
    read_eval_log,            # read full log or header only
    read_eval_log_sample,     # read a single sample by ID
    read_eval_log_samples,    # stream all samples via generator
    read_eval_log_sample_summaries,  # fast summary read (no full sample load)
    write_eval_log,           # write back modified logs
    edit_score,               # edit scores with provenance tracking
    edit_eval_log,            # edit tags/metadata with audit trail
    recompute_metrics,        # recompute after edits
)
```

**Score Editing with Provenance**
- `edit_score()` modifies individual sample scores while preserving full edit history
- Each edit includes `ProvenanceData` (author, reason)
- Original scores preserved in `score.history`
- `ScoreEditEvent` added to sample event log for audit trail
- `recompute_metrics` automatically recalculates aggregate metrics

**Tags & Metadata Editing**
- `edit_eval_log()` adds/removes tags and sets/removes metadata keys
- All edits recorded in `log.log_updates` as append-only history with provenance
- Original eval-time values preserved in `log.eval.tags` and `log.eval.metadata`

**Remote Storage**
- S3: `INSPECT_LOG_DIR=s3://bucket-name`
- Azure Blob: `INSPECT_LOG_DIR=az://container/path`
- Any fsspec-compatible filesystem
- FUSE mounting for local browsing of remote logs

**CLI Log Commands**
- `inspect log list --json --status success` -- structured listing
- `inspect log dump <uri>` -- print any log as JSON (handles binary + remote)
- `inspect log convert` -- convert between .eval and .json formats
- `inspect log schema` -- print JSON schema for log format

### Confidence: HIGH (source: official docs + GitHub source)

---

## 2. Datasets

### What We Know
- Basic Sample-based datasets

### Full Capabilities

**Loading Functions**
```python
from inspect_ai.dataset import (
    csv_dataset,      # load from CSV files
    json_dataset,     # load from JSON/JSONL files
    hf_dataset,       # load from HuggingFace Hub
    MemoryDataset,    # in-memory from list of Sample objects
    Sample,           # individual sample with input/target/metadata
)
```

**Sample Fields**
- `input` -- string or list of ChatMessage objects
- `target` -- expected output (string or list)
- `choices` -- multiple-choice options
- `id` -- unique identifier (auto-assigned if missing)
- `metadata` -- arbitrary dict, supports typed Pydantic models
- `sandbox`, `files`, `setup` -- sandbox environment configuration

**Manipulation**
- `dataset.filter(fn)` -- subset based on metadata or fields
- `dataset[0:100]` -- slicing
- `dataset.shuffle()` or `shuffle=True` -- randomize order with optional seed
- `shuffle_choices()` -- reorder multiple-choice options and update targets

**HuggingFace Integration**
```python
dataset = hf_dataset(
    "openai_humaneval",
    split="test",
    sample_fields=FieldSpec(...)
)
```

**No built-in versioning or splitting** -- filtering provides selective access. No explicit train/test split primitives.

### Confidence: HIGH (source: official docs)

---

## 3. Parallelism & Distribution

### Per-Sample Concurrency
- Samples run asynchronously by default
- `--max-samples` (default: max_connections + 1) limits concurrent samples
- `--max-connections` (default: 10) caps model API connections per model
- `--max-subprocesses` (default: os.cpu_count()) limits subprocess calls

### Per-Task Concurrency
- `--max-tasks` or `max_tasks` in eval() runs tasks in parallel
- Useful when samples per task are low

### Per-Model Concurrency
- Pass a list of models to eval(), concurrent evaluation per provider's limits

### Eval Sets (Batch Multi-Task Execution)
```python
from inspect_ai import eval_set
success, logs = eval_set(
    tasks=[task1, task2, task3],
    model=["openai/gpt-4o", "anthropic/claude-sonnet-4-20250514"],
    log_dir="./logs/experiment-1",
    max_tasks=4,
    retry_attempts=10,
    retry_wait=30,
)
```
- `eval_set()` / `inspect eval-set` runs multiple tasks across multiple models
- Automatic retries with exponential backoff
- Sample preservation: re-runs pick up where they left off
- Can be amended with additional tasks/models post-run
- Tasks can be filtered by attributes: `@task(light=True)`

### No Multi-Machine Distribution
- Inspect does NOT include built-in multi-machine or GPU allocation
- Single-machine async only
- Could be combined with external orchestration (e.g., Ray, Kubernetes jobs)

### Confidence: HIGH (source: official docs + source code)

---

## 4. Caching

### Local Caching (Exact Match)
- Matches on: model name, base URL, prompt, epoch number, generation config, tools/tool_choice
- Default 1-week expiry
- `--cache` CLI flag or `cache=True` in eval()
- `--cache-prompt` for prompt-level caching only

### Provider-Side Caching
- Anthropic: `"auto"` enables if tools are defined; `"true"` or `"false"` forces
- OpenAI: automatic prompt caching
- Configured via `GenerateConfig(cache="auto"|"true"|"false")`

### Cache Control
- Explicit model versions (e.g., `gpt-4-turbo-2024-04-09`) avoid alias issues
- Custom scopes for grouping cached responses
- Epoch-scoped caching (default) or disabled per-epoch scoping
- `--no-cache` to disable entirely

### Relevance to Bench
- **Critical for development iterations**: avoid re-running unchanged samples
- Model eval tier runs would benefit from caching across development
- Agent evals less cacheable (tool calls vary), but prompt caching still helps

### Confidence: HIGH (source: official docs)

---

## 5. Error Handling & Retries

### Eval-Level Retries
- `eval_retry()` / `inspect eval-retry` preserves completed samples
- Failed evaluations can be resumed from where they stopped

### Sample-Level Retries
- `retry_on_error` retries failed samples up to N times (default: 0)
- Original errors recorded in `error_retries` field
- Warning: may cause distribution shift if errors correlate with inputs
- CLI: `--retry-on-error=3`

### Failure Threshold
- `fail_on_error` accepts: `True`/`False`, proportion (e.g., `0.1` for 10%), count (e.g., `5`)
- Failed samples are not scored; warnings appear in logs

### Execution Limits (All Built-In)

| Limit Type | Config Key | Description |
|-----------|-----------|-------------|
| Time limit | `time_limit` | Wall-clock time per sample (e.g., 15 min) |
| Working limit | `working_limit` | Time excluding retries/wait |
| Message limit | `message_limit` | Max messages in conversation |
| Token limit | `token_limit` | Max total tokens across all generate() calls |
| Cost limit | `cost_limit` | Max cost in dollars (requires pricing config) |
| Custom limit | `LimitExceededError` | Raise in custom checks |

### Scoped Limits
```python
from inspect_ai.util import token_limit
with token_limit(1000):
    # code block with reduced token budget
```

### Tool Timeouts
```python
bash(timeout=120)  # 2-minute timeout for bash tool calls
```

### Confidence: HIGH (source: official docs + source code)

---

## 6. Hooks & Callbacks

### Overview
This is the most powerful extensibility point we are not using. The Hooks system provides 15 lifecycle events for custom behavior during eval runs.

### Available Hook Events

| Hook Event | When Fired | Data Provided |
|-----------|-----------|---------------|
| `on_eval_set_start` | eval_set() begins | eval_set_id, log_dir |
| `on_eval_set_end` | eval_set() completes | eval_set_id, log_dir |
| `on_run_start` | eval() or eval_retry() begins | run_id, task_names |
| `on_run_end` | run completes | run_id, logs, exception |
| `on_task_start` | individual task begins | eval_id, spec |
| `on_task_end` | individual task completes | eval_id, log |
| `on_sample_init` | sample scheduled (before sandbox) | sample_id, summary |
| `on_sample_start` | sample begins execution | sample_id, summary |
| `on_sample_event` | every event during sample | event (ModelEvent, ToolEvent, etc.) |
| `on_sample_end` | sample completes or fails finally | sample_id, full EvalSample |
| `on_sample_attempt_start` | every attempt (including retries) | attempt number |
| `on_sample_attempt_end` | every attempt ends | attempt, error, will_retry |
| `on_before_model_generate` | right before model API call | input messages, tools, config, cache state |
| `on_model_usage` | model API call completes | model_name, usage (tokens), call_duration, retries |
| `on_model_cache_usage` | cache hit (no API call) | model_name, usage |
| `on_sample_scoring` | before scoring begins | eval_id, sample_id |
| `override_api_key` | during model init or auth errors | env_var_name, value |

### Registration
```python
from inspect_ai.hooks import Hooks, hooks, RunStart, RunEnd, SampleEnd

@hooks(name="bench_monitor", description="Bench real-time monitoring")
class BenchMonitor(Hooks):
    def enabled(self) -> bool:
        return True  # or check env var

    async def on_run_start(self, data: RunStart) -> None:
        # initialize monitoring

    async def on_sample_end(self, data: SampleEnd) -> None:
        # track scores in real-time

    async def on_model_usage(self, data) -> None:
        # track token usage and cost
```

### Distribution via Python Package
- Register via setuptools entry points in `pyproject.toml`:
```toml
[project.entry-points.inspect_ai]
bench_monitor = "bench._registry"
```

### Relevance to Bench
- **Real-time progress tracking** during long eval runs
- **Token/cost monitoring** with automatic alerts
- **Custom notification system** (Slack, webhook) on completion
- **Metrics export** to external systems (W&B, MLflow)
- **Sample-level event streaming** for live dashboards

### Confidence: HIGH (source: GitHub source code, `_hooks.py`)

---

## 7. Metadata & Tagging

### Eval-Time Tags
```python
eval(task, model="openai/gpt-4o", tags=["experiment-1", "baseline"])
# CLI: --tags experiment-1 baseline
```

### Eval-Time Metadata
```python
eval(task, model="openai/gpt-4o", metadata={"variant": "cot", "version": "2"})
# CLI: --metadata variant=cot version=2
```

### Post-Eval Editing
```python
edit_eval_log(log, [
    TagsEdit(tags_add=["qa_passed"], tags_remove=["needs_qa"]),
    MetadataEdit(metadata_set={"reviewer": "alice"}, metadata_remove=["draft_notes"]),
], ProvenanceData(author="alice", reason="QA complete"))
```

### Typed Metadata
```python
from pydantic import BaseModel

class BenchMetadata(BaseModel):
    tier: str
    variant: str
    commit: str

# Access typed metadata from logs
metadata = log.samples[0].metadata_as(BenchMetadata)
```

### Log File Naming
- Default: `{timestamp}_{task}_{id}`
- Customizable: `INSPECT_EVAL_LOG_FILE_PATTERN={task}_{model}_{id}`

### Task Attributes
```python
@task(light=True)
def quick_eval():
    ...
```
- Filterable in eval sets: `inspect eval-set --filter light=True`

### Confidence: HIGH (source: official docs)

---

## 8. Human-in-the-Loop

### `input_screen()` Context Manager
- Pauses evaluation, displays console for user input
- Uses Rich library for formatted output (tables, panels, markdown)
- Can prompt for choices, confirmations, text input

```python
from inspect_ai.util import input_screen

async with input_screen() as screen:
    from rich.prompt import Confirm
    proceed = await screen.run(Confirm.ask, "Continue with this result?")
```

### Conversation Display Mode
- `--display=conversation` shows full chat history in terminal
- Limits to 1 task, 1 sample to avoid interleaving

### Human Agent (`human_agent()`)
- Full human baselining for agentic tasks
- Same dataset/sandbox/scorer setup as model agents
- Provides Docker/VS Code container access
- CLI tools: `task submit`, `task quit`, `task instructions`
- Session recording for review
- Headless mode for server-based provisioning

### Tool Approval System
- `approval.yaml` config for approving/rejecting tool calls
- Can require human approval for specific tools
- Custom approvers via `@approver` decorator
- Patterns: auto-approve, human-approve, conditional

### Confidence: HIGH (source: official docs)

---

## 9. Registries & Extensions

### Extension Points
| Extension Type | Decorator | Entry Point |
|---------------|-----------|-------------|
| Model API | `@modelapi` | `[project.entry-points.inspect_ai]` |
| Sandbox | `@sandboxenv` | `[project.entry-points.inspect_ai]` |
| Approver | `@approver` | `[project.entry-points.inspect_ai]` |
| Hooks | `@hooks` | `[project.entry-points.inspect_ai]` |
| Storage | fsspec filesystem | `[project.entry-points."fsspec.specs"]` |

### No Central Task/Scorer Registry
- Inspect does NOT have a public registry of importable tasks or scorers
- Over 100 pre-built evals exist in the `examples/` directory but must be copied
- Extensions are distributed as Python packages via PyPI

### Inspect Ecosystem Tools
| Tool | Purpose | URL |
|------|---------|-----|
| inspect-ai | Core framework | pypi.org/project/inspect-ai |
| inspect-swe | SWE agent solvers | github.com/meridianlabs-ai/inspect_swe |
| inspect-viz | Data visualization | github.com/meridianlabs-ai/inspect_viz |
| inspect-scout | Transcript analysis | meridianlabs-ai.github.io/inspect_scout |
| CJE | Scorer calibration | github.com/cimo-labs/cje |

### Confidence: HIGH (source: official docs + GitHub)

---

## 10. Visualization & Analysis

### Inspect View (`inspect view`)
- Web-based interactive log viewer
- Shows task summaries, sample drill-downs, message transcripts
- Scoring details: inputs, targets, answers, explanations
- Tool metadata (URLs, file paths, etc.)
- Filter by score, sort by score or sample order
- Live progress tracking during evaluations
- Can be bundled for static hosting (GitHub Pages, S3)
- VS Code extension integration

### Dataframe API
```python
from inspect_ai.analysis import (
    evals_df,      # one row per eval log
    samples_df,    # one row per sample
    messages_df,   # one row per message
    events_df,     # one row per event
)
```

**Column Groups (composable)**
- `EvalInfo` -- created, tags, metadata, git commit
- `EvalTask` -- task name, file, args, solver
- `EvalModel` -- model name, args, generation config
- `EvalResults` -- status, errors, headline metric
- `EvalScores` -- all scores and metrics as separate columns
- `SampleSummary` -- fast summary read without full sample load
- `SampleMessages` -- full message content
- `SampleScores` -- score answer, metadata, explanation

**DuckDB Integration**
```python
import duckdb
con = duckdb.connect()
con.register('evals', evals_df("logs"))
con.register('samples', samples_df("logs"))
result = con.execute("""
    SELECT * FROM evals e
    JOIN samples s ON e.eval_id = s.eval_id
    WHERE e.model LIKE 'anthropic/%'
""").fetchdf()
```

**Data Preparation Operations**
```python
from inspect_ai.analysis import prepare, model_info, frontier, score_to_float, log_viewer

df = evals_df("logs")
df = prepare(df, [
    model_info(),           # adds org name, display name, release date
    frontier(),             # adds "frontier" boolean column
    score_to_float("score_includes"),
    log_viewer("eval", {"logs": "https://logs.example.com"}),
])
```

**Parallel Reading** for large log sets:
```python
events_df("logs", parallel=True)       # auto worker count
events_df("logs", parallel=16)         # explicit worker count
```

### Inspect Viz
- Separate package: `pip install inspect-viz`
- Interactive visualizations from Inspect log data
- Score timelines, heatmaps, radar charts, comparison tables
- Agent observability: tool call analysis, trace visualization
- Works in Jupyter, VS Code, Quarto

### Tracing System
- `inspect trace` CLI for runtime debugging
- Captures JSON Lines logs of all events
- `inspect trace anomalies` -- find running/cancelled/stalled actions
- `inspect trace dump` -- filtered log inspection
- `inspect trace http` -- inspect HTTP requests
- Preserves logs from last 10 evaluations automatically
- Custom: `trace_action()` and `trace_message()` in Python

### Confidence: HIGH (source: official docs + source code)

---

## 11. Additional Features Not in Original 10 Questions

### Structured Output
- Enforce JSON schema on model responses via `ResponseSchema`
- Supports OpenAI, Anthropic, Google, Mistral, Grok, Groq, vLLM, SGLang
- Uses Pydantic models for schema definition
- vLLM/SGLang also support regex, choice, and grammar constraints

```python
from inspect_ai.model import GenerateConfig, ResponseSchema
from inspect_ai.util import json_schema

config = GenerateConfig(
    response_schema=ResponseSchema(
        name="result",
        json_schema=json_schema(MyResultModel),
    )
)
```

### Batch Mode
- 50% cost reduction for supported providers
- Automatic request batching with configurable size and timing
- Supports: OpenAI, Anthropic, Google, xAI, Together AI
- CLI: `--batch` or `--batch 1000`
- Not suitable for agentic tasks (path dependency between batches)

### Compaction (Long-Running Agents)
- Automatic context management when approaching context window limits
- Default threshold: 90% of context window
- Strategies: Auto, Native (provider API), Summary, Edit, Trim
- Built into react() agent and agent bridge
- The `memory()` tool offloads context to files before compaction

### Reasoning Model Support
- `reasoning_effort`: minimal/low/medium/high/xhigh (multi-provider)
- `reasoning_tokens`: max tokens for thinking (Claude 3.7+, Gemini 2.5+)
- `reasoning_summary`: concise/detailed/auto (OpenAI o-series)
- `reasoning_history`: none/all/last/auto (all models)
- `ContentReasoning` blocks normalized across providers

### Multi-Agent System
- `handoff()` -- delegate to sub-agent with full message history
- `run()` -- invoke agents sequentially or in parallel
- `as_tool()` -- expose agent as single-input/output tool
- Built-in filters: `content_only()`, `remove_tools()`, `last_message()`

### Standard Tools (Built-In)

**Computing Tools:**
- `web_search()` -- search + summarize
- `bash()` / `python()` -- code execution
- `bash_session()` -- stateful bash shell
- `text_editor()` -- file viewing/editing
- `computer()` -- desktop interaction via screenshots
- `code_execution()` -- sandboxed provider-side execution
- `web_browser()` -- headless Chromium

**Agentic Tools:**
- `skill()` -- agent skill specifications
- `update_plan()` -- task progress tracking
- `memory()` -- persistent key-value memory across turns
- `think()` -- extra thinking step before answering

### MCP Tool Integration
- Model Context Protocol tools integrate seamlessly
- Hundreds of MCP servers available (search, filesystem, database, git, etc.)

### Early Stopping
- Implement `EarlyStopping` protocol for adaptive testing
- `schedule_sample()` decides whether to run or skip each sample
- Results logged as `EarlyStoppingSummary`

### Typed Store
```python
from pydantic import BaseModel
from inspect_ai.util import store_as

class Activity(BaseModel):
    steps: list[str]
    result: str

activity = store_as(Activity)
```

### VS Code Extension
- Full eval authoring support
- Integrated log viewer
- Debug capabilities
- MyPy type checking integration

---

## Direct Impact on Bench Architecture

### Features to Adopt Immediately (Phase 1)

| Feature | Why | How |
|---------|-----|-----|
| **Caching** | Save API costs during development iterations | `--cache` flag, enable for quick tier |
| **Execution Limits** | Prevent runaway agent evals | `time_limit`, `token_limit`, `message_limit` per task |
| **Sample Retries** | Handle transient API failures | `retry_on_error=2` for agent evals |
| **Tags & Metadata** | Organize runs by tier, variant, commit | `--tags` and `--metadata` on every eval call |
| **Log Format (.eval)** | 8x smaller log files | `INSPECT_LOG_FORMAT=eval` in .env |
| **Sample Summaries** | Fast result comparison without loading full samples | `read_eval_log_sample_summaries()` |

### Features to Adopt in Phase 2

| Feature | Why | How |
|---------|-----|-----|
| **Hooks** | Real-time monitoring, cost tracking, notifications | Custom `BenchHooks` class |
| **Dataframe API** | Result comparison, statistical analysis | `samples_df()` + `evals_df()` |
| **Eval Sets** | Batch tier execution (quick + full) | `eval_set()` with task attributes |
| **Structured Output** | Enforce JSON from model eval responses | `ResponseSchema` for custom scorers |
| **Score Editing** | Manual correction of bad scores with audit trail | `edit_score()` with provenance |

### Features for Future Consideration

| Feature | Why | How |
|---------|-----|-----|
| **Batch Mode** | 50% cost reduction for model evals | `--batch` for non-agent evals |
| **Inspect Viz** | Interactive result exploration | `pip install inspect-viz` |
| **Compaction** | Long agent runs staying in context window | Built into agent bridge |
| **Human Agent** | Human baselines for comparison | `human_agent()` in separate task |
| **Early Stopping** | Skip clearly passing/failing samples | Custom EarlyStopping implementation |
| **Remote Log Storage** | Persistent log archive | S3 or Azure Blob storage |

---

## Built-In Scorers (Complete List)

| Scorer | Purpose | Metrics |
|--------|---------|---------|
| `match()` | Positional text match (beginning/end) | accuracy |
| `includes()` | Substring inclusion check | accuracy |
| `pattern()` | Regex extraction from free-form text | accuracy |
| `answer()` | Parse "ANSWER:" prefixed responses | accuracy |
| `exact()` | Normalized exact text match | accuracy |
| `f1()` | F1 score (precision/recall balance) | mean F1 |
| `choice()` | Multiple-choice scoring | accuracy |
| `math()` | Mathematical equivalence via SymPy | accuracy |
| `model_graded_qa()` | LLM-judged open-ended QA | configurable |
| `model_graded_fact()` | LLM-judged factual inclusion | configurable |
| `multi_scorer()` | Combine multiple scorers with reducer | varies |

**Score Reducers:** majority vote, mean, at_least (partial credit), etc.

**Grouped Metrics:**
```python
from inspect_ai.scorer import grouped
@scorer(metrics=[grouped(mean(), "category", all="groups")])
```
Computes metrics per subgroup based on sample metadata.

---

## Version Information

| Package | Latest Version | Verified Date |
|---------|---------------|---------------|
| inspect-ai | 0.3.205 | 2026-04-10 |
| inspect-swe | Latest from GitHub | 2026-03-18 (last PyPI release) |
| inspect-viz | Available on PyPI | 2026 |

---

## Sources

### Primary (HIGH confidence)
- Official docs: https://inspect.aisi.org.uk/ -- all major sections
- GitHub source: https://github.com/UKGovernmentBEIS/inspect_ai -- `src/inspect_ai/hooks/_hooks.py`, scorer modules, analysis module
- PyPI: pip index verification of v0.3.205

### Secondary (MEDIUM confidence)
- WebSearch for Inspect Viz, Inspect Scout details -- verified against GitHub links
- inspect-swe package info from PyPI

### Not Verified
- Docker/Kubernetes multi-machine distribution (confirmed NOT built-in)
- Any unreleased features in development branch
