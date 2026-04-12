# Research Report: Inspect AI Capabilities for Evaluating External CLI Agents

## Executive Summary

**Inspect AI has comprehensive, first-class support for evaluating external CLI agents including Claude Code, Codex CLI, and Gemini CLI.** This is not a hack or workaround -- it is a core architectural feature built into the framework via the `sandbox_agent_bridge()` system, with a dedicated extension package (`inspect-swe`) that provides production-ready integrations for all three major CLI agents.

The implications for Bench are significant: Inspect AI already provides the infrastructure Bench was planning to build. The question shifts from "can Inspect AI do this?" to "what should Bench layer on top?"

---

## Detailed Answers to Each Question

### 1. Does Inspect AI have built-in support for evaluating external CLI agents (Claude Code, Codex, Gemini)?

**YES -- first-class support via the `inspect-swe` package.**

The `inspect-swe` package (by Meridian Labs, a core Inspect contributor) provides ready-to-use agents:

| Agent | Function | Source |
|-------|----------|--------|
| Claude Code | `claude_code()` | Anthropic |
| Codex CLI | `codex_cli()` | OpenAI |
| Gemini CLI | `gemini_cli()` | Google |
| Mini SWE Agent | `mini_swe_agent()` | SWE-agent project |

Install: `pip install inspect-swe`

Usage (Claude Code example):
```python
from inspect_ai import Task, task
from inspect_ai.dataset import json_dataset
from inspect_ai.scorer import model_graded_qa
from inspect_swe import claude_code

@task
def system_explorer() -> Task:
    return Task(
        dataset=json_dataset("dataset.json"),
        solver=claude_code(),
        scorer=model_graded_qa(),
        sandbox="docker",
    )
```

Can also be used from CLI:
```bash
inspect eval ctf.py --solver inspect_swe/claude_code
inspect eval ctf.py --solver inspect_swe/codex_cli
inspect eval ctf.py --solver inspect_swe/gemini_cli
```

Each agent supports options: `system_prompt`, `skills`, `mcp_servers`, `bridged_tools`, `disallowed_tools`, `centaur`, `attempts`, `model`, `cwd`, `env`, `version`, `retry_refusals`, `retry_timeouts`, `filter`.

**Claude Code-specific options:** `opus_model`, `sonnet_model`, `haiku_model`, `subagent_model` (lets you control which model each tier maps to).
**Codex CLI-specific options:** `model_config` (defaults to `gpt-5-codex`), `home_dir`.
**Gemini CLI-specific options:** `gemini_model` (bypasses auto-router, defaults to `gemini-2.5-pro`).

All three also support **Centaur Mode** (human+AI collaboration) via `centaur=True`, which uses Inspect's `human_cli()` agent as the solver and makes the CLI agent available to the human user.

---

### 2. What is the `react()` solver -- does it only work with Inspect's own model calls, or can it wrap external agents?

**`react()` is an Inspect-native agent that works with Inspect's model calls. It does NOT wrap external CLI agents.** However, external agents use a different mechanism (`sandbox_agent_bridge()`) that serves the same purpose.

The `react()` function creates a general-purpose ReAct (Reasoning + Acting) agent:

```python
from inspect_ai.agent import react

@agent
def web_surfer() -> Agent:
    return react(
        name="web_surfer",
        description="Web research assistant",
        prompt="You are an expert at using a web browser to answer questions.",
        tools=[web_search()],
    )
```

Key parameters:
- `name`, `description` -- for multi-agent identification
- `prompt` -- str or `AgentPrompt` (instructions, handoff_prompt, assistant_prompt, submit_prompt)
- `tools` -- list of Inspect `Tool` objects
- `model` -- str, Model, or Agent (can delegate to another agent)
- `attempts` -- `AgentAttempts` for multi-attempt with scoring feedback
- `submit` -- `AgentSubmit` configuration (custom submit tool behavior)
- `on_continue` -- callback when model stops calling tools
- `retry_refusals` -- number of times to retry content filter refusals
- `compaction` -- context window overflow strategy
- `truncation` -- "auto", "disabled", or custom MessageFilter
- `approval` -- tool approval policies

Internally, `react()` runs a loop:
1. Prepend system message
2. Call `get_model().generate()` with tools
3. If tool calls present, execute via `execute_tools()`
4. Check for `submit()` tool call -- if found, optionally score and retry
5. If no tool calls, insert continue prompt
6. Loop until submit, limit hit, or no tool calls (when no submit tool)

The key distinction: `react()` orchestrates Inspect-native model calls and tools. For external agents, you use `sandbox_agent_bridge()` instead.

---

### 3. Does Inspect AI have subprocess management for running external agent commands?

**YES -- via the `SandboxEnvironment` API.**

The `sandbox()` function returns a `SandboxEnvironment` with these methods:

- **`exec(cmd, input, env, timeout, user, cwd)`** -- async command execution with:
  - 10MB output limit
  - Timeout with retry (up to 60s if `timeout_retry=True`)
  - Environment variable injection
  - User specification
  - Concurrency control

- **`exec_remote()`** -- streaming remote process execution (used for the model proxy in `sandbox_agent_bridge()`)

- **`write_file(path, contents)`** -- write files to sandbox, creates directories as needed

- **`read_file(path)`** -- read files from sandbox (text or binary, 100MB limit)

Example of running a CLI agent:
```python
from inspect_ai.util import sandbox

result = await sandbox().exec(
    cmd=["claude", "--print", "--model", "inspect", prompt],
    env={
        "ANTHROPIC_BASE_URL": f"http://localhost:{bridge.port}",
        "ANTHROPIC_API_KEY": "placeholder",
        "ANTHROPIC_MODEL": "inspect",
    },
)
if result.success:
    return result.stdout
```

Resource limits:
- `max_sandboxes` -- limits parallel sandboxes (Docker default: 2 * CPU count)
- `max_subprocesses` -- limits parallel subprocess calls (default: CPU count)
- `max_samples` -- limits concurrent samples (default: max_connections + 1)

---

### 4. Does Inspect AI provide workspace isolation for agent tasks?

**YES -- per-sample sandboxed environments with Docker, Kubernetes, and other backends.**

Each sample gets its own isolated sandbox instance. Configured at sample, task, or eval level:

```python
# Simple string config
sandbox="docker"

# With compose file
sandbox=("docker", "compose.yaml")

# Programmatic
from inspect_ai.util import SandboxEnvironmentSpec, ComposeConfig
sandbox=SandboxEnvironmentSpec(
    type="docker",
    config=ComposeConfig(services={
        "default": {"image": "python:3.12", "cpus": 1.0, "mem_limit": "0.5gb"}
    })
)
```

Per-sample setup:
```python
Sample(
    input="Explore this system",
    sandbox=("docker", "compose.yaml"),
    files={"task.py": "task.py", "data.json": "data.json"},  # copied into sandbox
    setup="pip install -r requirements.txt",  # bash script after file copy
)
```

Available sandbox backends:
| Backend | Type | Source |
|---------|------|--------|
| Docker | Built-in | Inspect core |
| Local | Built-in | Inspect core |
| Kubernetes | Extension | `inspect_k8s_sandbox` |
| EC2 | Extension | `inspect_ec2_sandbox` |
| Modal | Extension | `inspect_sandboxes` (Meridian) |
| Daytona | Extension | `inspect_sandboxes` (Meridian) |
| Proxmox | Extension | `inspect_proxmox_sandbox` |
| Podman | Extension | `inspect-podman` (Vector Institute) |
| Vagrant | Extension | `inspect_vagrant_sandbox` |

---

### 5. Does Inspect AI have built-in scoring for agent outputs (beyond text scoring)?

**Partially -- Inspect has a rich scorer ecosystem, but agent-specific scoring (trajectory, tool use efficiency) is not built-in as dedicated scorers.**

Built-in scorers:
- `includes()` -- substring match
- `match()` -- start/end match
- `pattern()` -- regex extraction
- `answer()` -- "ANSWER:" prefix extraction
- `exact()` -- exact text match
- `f1()` -- F1 score
- `model_graded_qa()` -- LLM-judged QA scoring
- `model_graded_fact()` -- LLM-judged fact verification
- `choice()` -- multiple choice
- `math()` -- LaTeX/SymPy math evaluation

**Agent-relevant scoring capabilities:**

Custom scorers can access the sandbox to verify outcomes:
```python
@scorer(metrics=[accuracy()])
def check_file_exists():
    async def score(state: TaskState, target: Target):
        try:
            _ = await sandbox().read_file(target.text)
            exists = True
        except FileNotFoundError:
            exists = False
        return Score(value=1 if exists else 0)
    return score
```

The `react()` agent has built-in `AgentAttempts` which scores intermediate submissions:
```python
react(
    attempts=AgentAttempts(
        attempts=3,
        incorrect_message="Your submission was incorrect. Try again.",
        score_value=value_to_float(),
    )
)
```

**What's NOT built-in as dedicated scorers:**
- No trajectory analysis scorer (number of tool calls, tool call efficiency)
- No tool use correctness scorer (did it use the right tools?)
- No efficiency scorer (time to completion, token usage as quality metric)
- No safety scorer (did the agent attempt dangerous actions?)

However, all of these CAN be built as custom scorers since `TaskState` contains the full message history including all tool calls and responses.

---

### 6. How does Inspect AI handle tool use evaluation and trajectory analysis?

**Tool use is fully captured in evaluation logs. Trajectory analysis is available via the log API and third-party tools, but not as built-in scoring.**

**What's captured per sample:**
- Full event transcript: model generations, tool calls, tool results, refusals
- Token usage stats (input/output per event)
- Model costs
- Score and scoring explanation
- Timestamps

**Log formats:**
- `.eval` -- binary, compressed (1/8 size of JSON), supports incremental access
- `.json` -- human-readable text format

**Log access:**
```python
from inspect_ai.log import list_eval_logs, read_eval_log
logs = list_eval_logs()
log = read_eval_log(logs[0])
# log.samples[0].events contains full trajectory
```

**CLI analysis:**
```bash
inspect log list          # enumerate logs
inspect log dump          # JSON output
inspect trace dump        # detailed trace
inspect trace anomalies   # find non-terminating/timed-out/errored commands
inspect trace dump --filter "Claude Code"  # filter by agent
```

**Third-party trajectory analysis tools:**
- **Inspect Scout** (Meridian) -- transcript analysis
- **Inspect Viz** (Meridian) -- interactive data visualization
- **Docent** (Transluce) -- summarize, cluster, search agent transcripts
- **Lunette** (Fulcrum Research) -- platform for understanding agents

**Tool approval system:**
Inspect has a tool approval mechanism that can intercept, approve, or reject tool calls. This is used for:
- Safety evaluation (did the agent try to do something dangerous?)
- Policy enforcement (restricting available tools)

---

### 7. Is there a `bridge` or `harness` pattern in Inspect AI for connecting to external agents?

**YES -- this is a core feature with two mechanisms: `agent_bridge()` (same-process) and `sandbox_agent_bridge()` (sandboxed).**

#### `agent_bridge(state)` -- Same-Process Python Agent Bridge

For Python-based agents (OpenAI Agents SDK, LangChain, Pydantic AI, etc.):

```python
from inspect_ai.agent import agent_bridge, Agent, AgentState, agent
from inspect_ai.model import messages_to_openai
from openai import AsyncOpenAI

@agent
def my_agent() -> Agent:
    async def execute(state: AgentState) -> AgentState:
        async with agent_bridge(state) as bridge:
            client = AsyncOpenAI()
            await client.chat.completions.create(
                model="inspect",
                messages=messages_to_openai(state.messages),
            )
        return bridge.state
    return execute
```

**How it works:** Monkey-patches the OpenAI, Anthropic, and Google client libraries. Any model named "inspect" (or "inspect/<provider>/<model>") gets redirected to Inspect's model provider. All model calls produce Inspect transcripts.

Supports:
- OpenAI Completions API and Responses API
- Anthropic Messages API
- Google Generative AI API
- Web search tool mapping
- Code execution tool mapping
- Compaction (context window management)
- Retry refusals

#### `sandbox_agent_bridge(state)` -- Sandbox Agent Bridge

For CLI agents and agents running in sandboxes:

```python
from inspect_ai.agent import sandbox_agent_bridge, Agent, AgentState, agent
from inspect_ai.util import sandbox
from inspect_ai.model import user_prompt

@agent
def my_agent() -> Agent:
    async def execute(state: AgentState) -> AgentState:
        async with sandbox_agent_bridge(state) as bridge:
            prompt = user_prompt(state.messages)
            result = await sandbox().exec(
                cmd=["/opt/my_agent", "--prompt", prompt.text],
                env={"OPENAI_BASE_URL": f"http://localhost:{bridge.port}/v1"},
            )
        return bridge.state
    return execute
```

**How it works:**
1. Starts a proxy server inside the sandbox container (port 13131)
2. The proxy intercepts OpenAI/Anthropic/Google API calls
3. Routes them back to Inspect's model provider on the host
4. All model calls produce Inspect transcripts with full observability

Parameters:
- `state` -- AgentState to track
- `model` -- fallback model (default: "inspect")
- `model_aliases` -- map of model name aliases
- `port` -- proxy port (default: 13131)
- `bridged_tools` -- host-side tools exposed via MCP
- `sandbox` -- which sandbox to use
- `compaction`, `filter`, `retry_refusals` -- same as agent_bridge

#### Bridged Tools (Host-to-Sandbox Tool Exposure)

Expose host-side Inspect tools to sandboxed agents via MCP protocol:

```python
from inspect_ai.agent import BridgedToolsSpec
from inspect_ai.tool import tool

@tool
def search_database():
    async def execute(query: str) -> str:
        return f"Results for: {query}"
    return execute

sandbox_agent_bridge(
    state,
    bridged_tools=[
        BridgedToolsSpec(name="host_tools", tools=[search_database()])
    ]
)
# bridge.mcp_server_configs contains MCPServerConfigStdio objects
```

---

### 8. Does Inspect AI's sandboxing (Docker/K8s) apply to agent eval or only model eval?

**Sandboxing applies equally to BOTH model eval and agent eval.** It is the same sandboxing infrastructure.

For model eval: tools like `bash()`, `python()`, `text_editor()` run inside sandboxes.
For agent eval: external CLI agents run inside sandboxes via `sandbox_agent_bridge()`.

The sandboxing is configured identically for both:
```python
# Model eval with sandbox
Task(solver=[use_tools(bash()), generate()], sandbox="docker")

# Agent eval with sandbox
Task(solver=claude_code(), sandbox="docker")

# Both support the same configuration options
Task(solver=..., sandbox=("docker", "compose.yaml"))
```

Key details:
- Per-sample isolation (no cross-contamination)
- Automatic cleanup after task completion
- Resource limits (CPU, memory) via compose.yaml
- Multiple named environments per sample (e.g., "victim" + "default")
- Sample metadata injection as `SAMPLE_METADATA_` env vars

---

## Source Code Analysis

Examined the Inspect AI repo at `/tmp/inspect_ai/` (cloned from GitHub):

**Agent module** (`src/inspect_ai/agent/`):
- `_agent.py` -- `Agent` protocol, `AgentState` class, `@agent` decorator
- `_react.py` -- Full `react()` implementation (338 lines)
- `_bridge/bridge.py` -- `agent_bridge()` with OpenAI/Anthropic/Google monkey-patching (479 lines)
- `_bridge/sandbox/bridge.py` -- `sandbox_agent_bridge()` with proxy server (235 lines)
- `_bridge/sandbox/types.py` -- `SandboxAgentBridge` class with port, MCP configs, bridged tools
- `_handoff.py` -- `handoff()` tool for multi-agent systems
- `_types.py` -- `AgentPrompt`, `AgentAttempts`, `AgentSubmit`, `AgentContinue`
- `_human/` -- `human_cli()` agent for human-in-the-loop baselining

**Example files** showing real usage:
- `examples/evals_in_eval/claude.py` -- Claude Code agent running inside Inspect
- `examples/http_proxy/claude.py` -- Claude Code with proxy configuration
- `examples/bridge/agentsdk/` -- OpenAI Agents SDK bridge
- `examples/bridge/langchain/` -- LangChain bridge
- `examples/bridge/pydantic-ai/` -- Pydantic AI bridge

---

## Key Takeaways for Bench

1. **Inspect AI already has everything Bench's PRD planned.** The `inspect-swe` package provides Claude Code, Codex CLI, and Gemini CLI as drop-in agents. The sandboxing, bridging, and scoring infrastructure is mature and production-grade.

2. **The Agent Bridge architecture is sophisticated.** It handles model call interception, state tracking, context compaction, refusal retrying, and tool bridging -- all automatically. Bench would not need to build any of this.

3. **What Inspect AI does NOT provide (gaps for Bench):**
   - No built-in efficiency scoring (time, tokens, tool calls as quality metrics)
   - No trajectory quality scoring (did the agent take the right path?)
   - No safety scoring (did the agent attempt dangerous actions?)
   - No statistical comparison framework (bootstrap CI, Cohen's d, etc.)
   - No "bench compare" or "bench history" CLI
   - No composite scoring (correctness * efficiency * safety)

4. **Bench's value-add should focus on:**
   - Task design (the evaluation tasks themselves)
   - Custom scorers (efficiency, safety, trajectory quality)
   - Statistical analysis layer on top of Inspect logs
   - Comparison/history CLI that reads Inspect log data
   - Bench-specific task categories and tiers

5. **The `inspect-swe` agents already handle:**
   - Automatic binary download and caching
   - Version pinning
   - Environment variable configuration
   - MCP server integration
   - Centaur mode (human+AI)
   - Debug/troubleshooting via `inspect trace dump`
