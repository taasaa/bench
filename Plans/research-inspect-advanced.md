# Inspect AI Advanced Capabilities Research

**Researched:** 2026-04-10
**Domain:** Inspect AI framework -- advanced features, extension points, lesser-known capabilities
**Confidence:** HIGH (official docs + PyPI verification + GitHub README)

## Summary

This document covers 10 advanced areas of Inspect AI (v0.3.205, latest as of 2026-04-10) that go beyond the basics of tasks, solvers, scorers, EvalLog, sandboxing, and multi-provider support. The framework is significantly more capable than a simple "prompt in, score out" system -- it provides a full evaluation platform with agent scaffolding, approval systems, extension hooks, epoch-based variance measurement, and a large ecosystem of pre-built benchmarks via `inspect_evals`.

**Primary recommendation:** Bench should leverage Inspect as a full evaluation platform rather than just a runner. The extension model (hooks, custom model APIs, custom approvers) and the `inspect_evals` package provide capabilities that would be expensive to rebuild. The approval system and epoch/reducer system are particularly relevant for Bench's safety gating and statistical rigor goals.

---

## 1. inspect_evals (The Package)

**Confidence: HIGH** -- verified from GitHub README and PyPI

`inspect_evals` is a companion Python package containing 100+ community-contributed benchmark evaluations, all compatible with the Inspect framework. It is installable alongside `inspect_ai` and runs through the same CLI/API.

### Installation and Usage

```bash
pip install inspect-evals

# Run a specific benchmark against any model
inspect eval inspect_evals/humaneval --model openai/gpt-4o

# Run with Anthropic
inspect eval inspect_evals/gsm8k --model anthropic/claude-sonnet-4-20250514

# In Python
from inspect_evals.humaneval import humaneval
eval(humaneval(), model="anthropic/claude-sonnet-4-20250514")
```

### Available Benchmarks by Category

**Coding:**
- HumanEval, MBPP, APPS, BigCodeBench, ClassEval, DS-1000, SciCode, USACO
- SWE-bench Verified, SWE-Lancer, MLE-bench, MLRC-Bench, PaperBench
- KernelBench, ComputeEval (CUDA code), LiveCodeBench-Pro
- Frontier-CS, IFEvalCode, CORE-Bench, scBench

**Reasoning:**
- ARC (Abstraction and Reasoning Corpus)
- Needle-in-a-haystack benchmarks
- GAIA (General AI Assistants)
- Logic-heavy multiple-choice tasks

**Mathematics:**
- GSM8K (grade-school math)
- AIME 2024/2025/2026 (competition math)
- MATH benchmark

**Knowledge:**
- MMLU, MMLU-Pro (Massive Multitask Language Understanding)
- GPQA (graduate-level Q&A)
- CommonsenseQA

**Safety & Safeguards:**
- XSTest (exaggerated safety behaviors)
- AgentHarm (harmfulness in AI agents)
- APE (Attempt to Persuade Eval)
- Sycophancy Eval
- AgentDojo (prompt injection/defense testing)

**Agents:**
- AgentBench, BrowseComp, AssistantBench
- Mind2Web, OSWorld (multimodal computer interaction)

**Cybersecurity:**
- CyBench, CVE_bench, SEvenLLM

**Tool Use:**
- BFCL (Berkeley Function-Calling Leaderboard)

### Relevance to Bench

You can use `inspect_evals` benchmarks as reference points alongside custom Bench tasks. For example, run `inspect_evals/humaneval` and your custom tasks in the same eval set, then compare scores. This gives you standard benchmarks without writing any task code.

Note: Some agentic benchmarks (SWE-bench, OSWorld) require Docker and significant disk space (up to 100GB recommended for full setup). For Phase 1 with local sandbox, stick to simpler benchmarks.

---

## 2. Multi-Turn Evaluations

**Confidence: HIGH** -- verified from official docs

### How It Works

Inspect handles multi-turn evaluations through two mechanisms:

**a) Solver-level multi-turn via `generate_loop()`:**
The `generate_loop()` function runs the model repeatedly until tool calls cease. This is the foundation of agent evaluations -- the model calls a tool, Inspect executes it and feeds the result back, and the model continues.

```python
from inspect_ai.model import get_model

# generate_loop runs until no more tool calls
messages, output = await get_model().generate_loop(
    state.messages,
    tools=[web_search()]
)
```

**b) Agent protocol for persistent multi-turn:**
The Agent system (`@agent` decorator) maintains `AgentState` across turns. This is the recommended way to build multi-turn evaluations:

```python
from inspect_ai.agent import Agent, AgentState, agent
from inspect_ai.model import ChatMessageSystem, get_model
from inspect_ai.tool import web_search

@agent
def web_surfer() -> Agent:
    async def execute(state: AgentState) -> AgentState:
        state.messages.append(
            ChatMessageSystem(content="You are a web research assistant.")
        )
        messages, output = await get_model().generate_loop(
            state.messages, tools=[web_search()]
        )
        state.output = output
        state.messages.extend(messages)
        return state
    return execute
```

**c) Built-in ReAct agent:**
For common patterns, use the built-in `react()` agent:

```python
from inspect_ai.agent import agent, react
from inspect_ai.tool import web_search

@agent
def web_surfer() -> Agent:
    return react(
        name="web_surfer",
        description="Web research assistant",
        prompt="You are an expert at web browsing.",
        tools=[web_search()]
    )
```

### State Persistence

`TaskState` (for solvers) and `AgentState` (for agents) carry the full message history across turns. You can inspect, modify, or extend the history at any point. State includes:
- `messages`: Full chat history
- `output`: Final model output
- `user_prompt`: First user message text
- `metadata`: Custom metadata dictionary
- `completed`: Boolean flag for early termination

### Tool Use in Multi-Turn

Tools are automatically integrated into multi-turn loops. The model generates a structured tool call request, Inspect executes the Python function, and returns the result to the model. This continues until the model produces a text response without tool calls.

### Relevance to Bench

For agent evaluations (Phase 2+), the multi-turn system is exactly what you need. The `sandbox_agent_bridge()` concept from the PRD maps directly to this architecture. For Phase 1 model evaluations, multi-turn is not needed -- single-turn `generate()` is sufficient.

---

## 3. Tool Use Evaluation

**Confidence: HIGH** -- verified from official docs

### Custom Tools

Tools are Python functions decorated with `@tool`. They require type annotations and docstrings for model guidance:

```python
from inspect_ai.tool import tool

@tool
def add():
    async def execute(x: int, y: int):
        """Add two numbers.
        
        Args:
            x: First number to add.
            y: Second number to add.
        
        Returns:
            The sum of the two numbers.
        """
        return x + y
    return execute
```

### Providing Tools to Models

Tools are given to models via the `use_tools()` solver:

```python
from inspect_ai import Task, task
from inspect_ai.solver import generate, use_tools
from inspect_ai.scorer import match

@task
def addition_problem():
    return Task(
        dataset=[Sample(input="What is 1 + 1?", target=["2"])],
        solver=[use_tools(add()), generate()],
        scorer=match(numeric=True),
    )
```

### Evaluating Tool Use Quality

You can evaluate how well models use tools by:
1. **Scoring the final output** -- did the model reach the correct answer using the tools?
2. **Inspecting the tool call transcript** -- the EvalLog records every tool call with inputs/outputs
3. **Custom scorers that check tool trajectories** -- write a scorer that inspects `state.messages` for tool call patterns

### MCP Tool Integration

Inspect supports MCP (Model Context Protocol) tools, giving access to hundreds of pre-built tool servers for web search, filesystem, databases, etc.

### Built-in Tools

Inspect provides built-in tools for common operations:
- `web_search()` -- web searching
- `bash()` -- shell command execution (with sandboxing)
- `python()` -- Python code execution
- Computer interaction tools

### Tool Viewers

Custom tool viewers improve the display of tool calls in logs:

```python
from inspect_ai.tool import Tool, ToolCall, ToolCallContent, ToolCallView, ToolCallViewer, tool

def bash_viewer() -> ToolCallViewer:
    def viewer(tool_call: ToolCall) -> ToolCallView:
        code = tool_call.arguments.get("cmd", "").strip()
        call = ToolCallContent(
            format="markdown",
            content="**bash**\n\n```bash\n" + code + "\n```\n",
        )
        return ToolCallView(call=call)
    return viewer

@tool(viewer=bash_viewer())
def bash(timeout: int | None = None) -> Tool:
    # Tool implementation
    ...
```

### Relevance to Bench

For Bench's agent eval mode, custom tools are how you define the environment the agent interacts with. For model eval mode, tools let you test whether models can correctly use provided tools. The `sandbox_agent_bridge()` in the PRD is essentially a custom tool.

---

## 4. Subsample / Sample Selection

**Confidence: HIGH** -- verified from official docs

### Python API: Dataset Filtering and Slicing

```python
# Filter by metadata
dataset = dataset.filter(lambda sample: sample.metadata["category"] == "advanced")

# Slice by index
dataset = dataset[0:100]

# Shuffle with seed
dataset = dataset.shuffle(seed=42)

# Shuffle choices (for multiple-choice tasks)
dataset = dataset.shuffle_choices(seed=42)
```

### CLI: Sample Selection

```bash
# Run specific samples by ID
inspect eval task.py --sample-id 44
inspect eval task.py --sample-id 44,63,91

# Run samples matching a glob pattern
inspect eval task.py --sample-id "*_advanced"

# Limit to first N samples
inspect eval task.py --limit 10

# Run a range of samples
inspect eval task.py --limit 10-20
```

### No Built-in Stratified Sampling

Inspect does not provide a built-in stratified sampling function. However, you can achieve the same effect by:
1. Using `dataset.filter()` with custom logic based on metadata fields
2. Using `dataset.shuffle(seed=42)` followed by `dataset[0:N]` for random samples
3. Building a custom dataset loader that implements stratified selection

### Relevance to Bench

This directly supports Bench's "quick tier" (5 tasks) and "full tier" (15-20 tasks). You can tag tasks with metadata and use `--limit` or `filter()` to select subsets. The `bench run --tier quick` command would map to `inspect eval ... --limit 5`.

---

## 5. Epochs and Repetition

**Confidence: HIGH** -- verified from official docs

### Basic Epochs

Run each sample multiple times to measure variance:

```python
Task(
    dataset=read_dataset(),
    solver=solver,
    scorer=includes(),
    epochs=2,  # Run each sample twice
)
```

### Epochs with Reducers

When running multiple epochs, you need a strategy to reduce the multiple scores into one. Inspect provides `Epochs(count, reducer)`:

```python
from inspect_ai import Epochs

Task(
    dataset=read_dataset(),
    epochs=Epochs(5, "mode"),  # 5 runs, use mode (most common)
)
```

### Built-in Reducers

| Reducer | What It Does |
|---------|-------------|
| `mean` | Average of all epoch scores (default) |
| `median` | Median of all epoch scores |
| `mode` | Most common score |
| `max` | Maximum score |
| `pass_at_k` | Probability of at least 1 correct in k attempts |
| `at_least_k` | 1 if at least k samples correct, else 0 |

Multiple reducers compute separate metrics:

```python
epochs=Epochs(5, ["at_least_2", "at_least_5"])
```

### CLI Epochs

```bash
inspect eval task.py --epochs 5
```

### Custom Reducers

```python
from inspect_ai.scorer import score_reducer, ScoreReducer, Score

@score_reducer(name="mean")
def mean_score() -> ScoreReducer:
    to_float = value_to_float()
    def reduce(scores: list[Score]) -> Score:
        values = [to_float(score.value) for score in scores]
        mean_value = statistics.mean(values)
        return Score(value=mean_value)
    return reduce
```

### Relevance to Bench

Epochs are essential for Bench Phase 2+ when you need statistical rigor. `pass_at_k` is particularly useful for coding tasks where you want to measure "can the model solve this if given k attempts." For Phase 1 with deterministic scoring, epochs=1 is fine.

---

## 6. Model Configuration

**Confidence: HIGH** -- verified from official docs + PyPI

### GenerateConfig Parameters

```python
from inspect_ai.model import get_model, GenerateConfig

config = GenerateConfig(
    temperature=0.7,
    top_p=0.9,
    max_tokens=2048,
    stop_sequences=["\n\n"],
    frequency_penalty=0.0,
    presence_penalty=0.0,
    timeout=120,
    max_retries=3,
    max_connections=10,
)

model = get_model("openai/gpt-4o", config=config)
```

### CLI Configuration

```bash
inspect eval task.py \
  --model openai/gpt-4o \
  --temperature 0.7 \
  --top-p 0.95 \
  --max-tokens 1024 \
  --max-connections 20

# Or via config file
inspect eval task.py --generate-config config.json
```

### Model Roles (Multi-Model Tasks)

Tasks can use multiple models with different roles -- e.g., one model for generation and another for grading:

```python
Task(
    dataset=read_dataset(),
    solver=[generate()],
    scorer=model_graded_qa(model="openai/gpt-4o"),
    # Or via model_roles:
    model_roles={"grader": "openai/gpt-4o"},
)
```

In scorers/solvers, get the role-specific model:

```python
from inspect_ai.model import get_model
grader = get_model(role="grader")
```

### CLI Model Roles

```bash
inspect eval task.py \
  --model anthropic/claude-sonnet-4-20250514 \
  --model-role grader=openai/gpt-4o
```

### Provider-Specific Args

```bash
# Pass provider-specific args
inspect eval task.py -M location=us-east5  # For Google Gemini
```

### Task-Level Config Override

```python
Task(
    ...,
    config=GenerateConfig(temperature=0.0, max_tokens=100),
)
```

### Relevance to Bench

Bench needs `GenerateConfig` for controlling model behavior during evaluations. The `temperature=0` setting is critical for deterministic scoring. Model roles enable using a separate judge model for LLM-graded tasks (Phase 2). The `--generate-config` CLI flag lets Bench store model configs as JSON files.

---

## 7. Custom Solver Pipelines

**Confidence: HIGH** -- verified from official docs

### Solver Composition

Solvers compose via lists (sequential chaining):

```python
@task
def theory_of_mind():
    return Task(
        dataset=json_dataset("theory_of_mind.jsonl"),
        solver=[
            system_message("system.txt"),
            prompt_template("prompt.txt"),
            generate(),
            self_critique(),
        ],
        scorer=model_graded_fact(),
    )
```

### Custom Solvers with @solver

```python
from inspect_ai.solver import Generate, Solver, TaskState, solver

@solver
def prompt_template(template: str, **params: dict[str, Any]):
    prompt_template = resource(template)
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        prompt = state.user_prompt
        kwargs = state.metadata | params
        prompt.text = prompt_template.format(prompt=prompt.text, **kwargs)
        return state
    return solve
```

### Solver Factories (Reusable Pipelines)

The `chain()` function creates reusable solver pipelines:

```python
from inspect_ai.solver import chain

@solver
def critique(system_prompt="system.txt", user_prompt="prompt.txt"):
    return chain(
        system_message(system_prompt),
        prompt_template(user_prompt),
        generate(),
        self_critique(),
    )
```

### Conditional Logic

Solvers can conditionally modify state:
- Set `state.completed = True` for early termination
- Inspect `state.messages` to check conversation history
- Use `state.metadata` for branching decisions

### Built-in Solvers

| Solver | Purpose |
|--------|---------|
| `generate()` | Call the model |
| `system_message()` | Set system prompt |
| `use_tools()` | Provide tools |
| `prompt_template()` | Rewrite user prompt via template |
| `self_critique()` | Critique and regenerate |
| `multiple_choice()` | Handle A/B/C/D choices |
| `chain_of_thought()` | Add CoT reasoning |
| `user_message()` | Append a user message |

### Relevance to Bench

Bench's custom scorers and evaluation flow can be built as solver pipelines. The `sandbox_agent_bridge()` concept is a custom solver that wraps inspect-swe agents. The `chain()` pattern lets you compose Bench-specific evaluation stages (e.g., setup -> generate -> verify -> score).

---

## 8. Scoring Aggregation

**Confidence: HIGH** -- verified from official docs

### Built-in Metrics

| Metric | What It Computes |
|--------|-----------------|
| `accuracy()` | Proportion correct |
| `mean()` | Mean of score values |
| `var()` | Variance |
| `std()` | Standard deviation |
| `stderr()` | Standard error (analytic, via CLT) |
| `bootstrap_stderr()` | Bootstrap standard error (1000 samples default) |

### Grouped Metrics

Aggregate scores by metadata field:

```python
from inspect_ai.scorer import grouped
scorer=includes(metrics=[grouped(accuracy(), "category")])
```

### Clustered Standard Errors

Account for grouping when computing stderr:

```python
scorer=includes(metrics=[stderr(cluster="category")])
```

### Multiple Scorers on One Task

```python
# Independent scores (list)
scorer=[includes(), match(), model_graded_qa()]

# Multi-value scores (dict)
@scorer(metrics=[{"a_count": [mean(), stderr()], "e_count": [mean(), stderr()]}, total_count()])
def letter_count():
    async def score(state: TaskState, target: Target):
        return Score(value={"a_count": a_count, "e_count": e_count})
    return score
```

### Multi-Scorer with Reducer

Combine multiple scorers and reduce:

```python
from inspect_ai.scorer import multi_scorer
# Use "mode" for majority vote across graders
multi_scorer("mode", [model_graded_qa(model="openai/gpt-4o"), model_graded_qa(model="anthropic/claude-sonnet-4-20250514")])
```

### Custom Metrics

```python
from inspect_ai.scorer import metric, Metric

@metric
def mean() -> Metric:
    def metric(scores: list[SampleScore]) -> float:
        return np.mean([score.score.as_float() for score in scores]).item()
    return metric
```

### Post-Hoc Scoring

Score evaluations after they run:

```bash
# Run without scoring
inspect eval task.py --no-score

# Score later
inspect score log_file.eval --scorer model_graded_qa
```

```python
# Append scores without overwriting
score(log, model_graded_qa(model=model), action="append")
```

### Relevance to Bench

Bench's scoring formula `(correctness * 0.67 + efficiency * 0.33) * safety_gate` maps directly to a custom metric. The `grouped()` function enables breaking down results by task category. `bootstrap_stderr()` provides the statistical rigor needed for Phase 2 comparisons. Post-hoc scoring lets you re-score without re-running evaluations.

---

## 9. Approval / Human Review System

**Confidence: HIGH** -- verified from official docs

### What It Is

The approval system controls which tool calls are permitted during evaluations. It provides fine-grained policies for approving, modifying, rejecting, or escalating tool calls -- from fully autonomous to fully human-supervised.

### Approval Policy Configuration

Policies are defined as ordered lists of (approver, tools) pairs, evaluated top to bottom:

```yaml
# approval.yaml
approvers:
  - name: human
    tools: ["web_browser_click", "web_browser_type"]
  - name: auto
    tools: "*"
```

```python
# Or in code
from inspect_ai.approval import ApprovalPolicy, human_approver, auto_approver

approval = [
    ApprovalPolicy(human_approver(), ["web_browser_click", "web_browser_type*"]),
    ApprovalPolicy(auto_approver(), "*")
]
```

### Decision Types

| Decision | Effect |
|----------|--------|
| `approve` | Allow the tool call |
| `modify` | Allow with modified arguments |
| `reject` | Block the tool call |
| `escalate` | Pass to next approver in chain |
| `terminate` | End the evaluation |

### Custom Approvers

```python
from inspect_ai.approval import approver, Approver, Approval

@approver
def bash_allowlist(allowed_commands: list[str]) -> Approver:
    async def approve(message: str, call: ToolCall, view: ToolCallView,
                      history: list[ChatMessage]) -> Approval:
        cmd = call.arguments.get("cmd", "").split()[0]
        if cmd in allowed_commands:
            return Approval(decision="approve", explanation="Command allowed")
        return Approval(decision="reject", explanation="Command not in allowlist")
    return approve
```

### Usage in Evaluations

```python
# Eval-level
eval("task.py", approval="human")

# Task-level
@task
def linux_task():
    return Task(
        dataset=read_dataset(),
        solver=[use_tools([bash(), python()]), generate()],
        scorer=match(),
        approval=human_approver(),
    )

# Context manager for temporary override
with approval([ApprovalPolicy(human_approver(), "*")]):
    # Code requiring approval
    pass
```

### Tool Viewers for Approval UI

Custom viewers format tool calls for human review:

```python
def bash_viewer() -> ToolCallViewer:
    def viewer(tool_call: ToolCall) -> ToolCallView:
        code = tool_call.arguments.get("cmd", "").strip()
        return ToolCallView(
            call=ToolCallContent(format="markdown", content=f"**bash**\n\n```bash\n{code}\n```")
        )
    return viewer
```

### Relevance to Bench

The approval system is highly relevant for Bench's `safety_gate` component. You can create custom approvers that act as safety evaluators -- checking whether agent actions are safe before allowing them. The "reject" and "terminate" decisions map to Bench's safety gate blocking unsafe behavior. For Phase 2+ agent evaluations, approval policies can gate dangerous tool calls during evaluation runs.

---

## 10. Extensions / Plugins

**Confidence: HIGH** -- verified from official docs

### Extension Model

Inspect extends through Python packages registered via setuptools entry points. No special framework setup needed.

```toml
# pyproject.toml
[project.entry-points.inspect_ai]
evaltools = "evaltools._registry"
```

### Extension Points

| Extension Point | Decorator | Purpose |
|----------------|-----------|---------|
| **Model APIs** | `@modelapi` | Add support for new model providers |
| **Sandbox Environments** | `@sandboxenv` | Add new sandbox types (beyond Docker/K8s/local) |
| **Approvers** | `@approver` | Custom approval logic |
| **Hooks** | `@hooks` | Lifecycle event handlers |
| **Storage/Filesystems** | fsspec entry points | Custom log/dataset storage backends (S3, GCS, etc.) |

### Hooks (Lifecycle Events)

Hooks provide event-driven extension points:

```python
from inspect_ai.hooks import Hooks, hooks

@hooks
class MyHooks(Hooks):
    def enabled(self) -> bool:
        return True  # Or conditional
    
    async def on_run_start(self, run_id: str):
        # Called when evaluation run starts
        pass
    
    async def on_run_end(self, run_id: str):
        # Called when evaluation run ends
        pass
    
    async def on_sample_start(self, sample_id: str):
        # Called before each sample
        pass
    
    async def on_sample_end(self, sample_id: str):
        # Called after each sample completes
        pass
```

Hooks can be required via `INSPECT_REQUIRED_HOOKS` environment variable, useful for CI/CD enforcement.

### Custom Model API

```python
from inspect_ai.model import ModelAPI, modelapi

@modelapi
class MyModelAPI(ModelAPI):
    def __init__(self, model_name: str, ...):
        # Initialize provider connection
        pass
    
    async def generate(self, messages, tools, config):
        # Implement generation
        pass
```

Usage: `inspect eval --model custom/my-model`

### Custom Sandbox Environment

```python
from inspect_ai.sandbox import SandboxEnvironment, sandboxenv

@sandboxenv
class PodmanSandbox(SandboxEnvironment):
    # Implement lifecycle and execution methods
    pass
```

Usage: `Task(..., sandbox="podman")`

### Relevance to Bench

The extension model is how Bench should integrate with Inspect:
1. **Custom Model API** -- if Bench needs to wrap model calls with custom behavior (timing, logging)
2. **Hooks** -- for `bench history` tracking, pre/post evaluation actions, CI integration
3. **Custom Approvers** -- for safety gate implementation
4. **Storage** -- for Bench's SQLite index integration alongside Inspect's native log files

---

## Cross-Cutting Features

### EvalLog Programmatic API

```python
from inspect_ai.log import list_eval_logs, read_eval_log, read_eval_log_sample_summaries

# List all logs
logs = list_eval_logs()

# Read full log
log = read_eval_log(log_file)

# Read header only (fast)
log = read_eval_log(log_file, header_only=True)

# Read sample summaries (no full messages)
summaries = read_eval_log_sample_summaries(log_file)

# Stream samples (memory-efficient for large logs)
for sample in read_eval_log_samples(log_file):
    process(sample)
```

Key `EvalLog` fields:
- `status`: "success" or "error"
- `results`: Aggregated scores/metrics
- `stats`: Token usage, timing
- `samples`: Individual sample results with full message history
- `eval`: Task configuration
- `plan`: Solver and model config used

Log format: `.eval` (binary, zstd compressed, default since v0.3.46) or `.json` (text). Convert with `inspect log convert`.

### Analysis via DataFrames

```python
from inspect_ai.analysis import evals_df

df = evals_df("./logs")
variance = df.groupby("sample_id")["score"].var()
```

### Log Viewer

```bash
inspect view  # Launches on http://localhost:7575
```

Provides interactive visualization of results, message histories, scoring decisions, and metadata.

### Inspect View Bundle

Package logs for sharing:
```bash
inspect view bundle  # Creates standalone HTML viewer
```

---

## Version and Ecosystem Status

| Component | Version | Status |
|-----------|---------|--------|
| `inspect_ai` | 0.3.205 (2026-04-10) | Actively developed, ~200 patch releases |
| `inspect_evals` | Available on PyPI | 100+ benchmarks, community maintained |
| `inspect-swe` | Available | Agent eval solvers for Claude Code, Codex CLI, Gemini CLI |
| Python | 3.11 or 3.12 recommended | 3.13 untested, 3.14 unsupported |

---

## Summary Table: Relevance to Bench

| Feature | Bench Phase 1 | Bench Phase 2+ | Priority |
|---------|---------------|----------------|----------|
| inspect_evals | Reference benchmarks | Standard comparison suite | MEDIUM |
| Multi-turn evaluations | Not needed | Agent eval core | HIGH (Phase 2) |
| Tool use evaluation | Not needed | Agent eval core | HIGH (Phase 2) |
| Sample selection | `--limit` for quick/full tiers | Same | HIGH |
| Epochs/repetition | Not needed | Statistical rigor | MEDIUM |
| Model configuration | `temperature=0`, `max_tokens` | Full GenerateConfig | HIGH |
| Custom solver pipelines | Custom scorers | Agent bridge, multi-stage eval | HIGH |
| Scoring aggregation | Custom metric for Bench formula | `bootstrap_stderr`, `grouped()` | HIGH |
| Approval system | Not needed | Safety gate implementation | MEDIUM |
| Extensions/hooks | Hooks for history tracking | Custom model API, approvers | MEDIUM |

---

## Sources

### Primary (HIGH confidence)
- [Inspect AI Official Docs](https://inspect.aisi.org.uk/) -- solvers, scorers, tasks, models, tools, approval, extensions, agents, datasets, eval-logs pages
- [inspect_ai on PyPI](https://pypi.org/project/inspect-ai/) -- version 0.3.205 verified 2026-04-10
- [inspect_evals GitHub](https://github.com/UKGovernmentBEIS/inspect_evals) -- README with full benchmark list

### Secondary (MEDIUM confidence)
- WebSearch results verified against official docs URLs for CLI flags, GenerateConfig details, epoch reducers
- WebSearch results for inspect_evals benchmark categories cross-referenced with GitHub repo structure
