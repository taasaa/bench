"""Local agent solver: runs CLI agent as subprocess on the host machine.

Agent-agnostic — uses AgentConfig from bench_cli.agents to build the
correct command for claude, codex, gemini, or any future agent.

Modes:
  - local: Full harness (hooks, CLAUDE.md, skills — whatever the agent picks up)
  - bare:  No harness (--bare flag for agents that support it)

Output is captured and set as state.output.completion so all existing
scorers (verify_sh, llm_judge, token_ratio, time_ratio) work unchanged.
"""

from __future__ import annotations

import asyncio
import time

from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, Solver, TaskState, solver

from bench_cli.agents import get_agent_config

DEFAULT_TIMEOUT = 300  # 5 minutes per task


@solver
def local_agent(
    agent_name: str,
    bare: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    model: str | None = None,
) -> Solver:
    """Solver that runs a CLI agent as a local subprocess.

    Args:
        agent_name: Agent to use (claude, codex, gemini).
        bare: If True, run in bare mode (skip hooks, CLAUDE.md, etc.).
        timeout: Maximum seconds to wait for agent output.
        model: CCR-style model override for Claude Code (e.g. "litellm,thinking",
            "kilocode,opus"). Only supported for claude agent. Passed as
            --model flag to claude CLI. None means use CCR's default.
    """
    config = get_agent_config(agent_name)

    # Validate CLI is available at solver construction time
    if not config.cli_available():
        raise RuntimeError(
            f"Agent CLI {config.binary!r} not found in PATH. "
            f"Install {config.name} or check your PATH."
        )

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        prompt = state.input_text
        cmd = config.build_cmd(prompt, bare=bare, model=model)

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            state.output = ModelOutput.from_content(
                model=f"local-{agent_name}", content=""
            )
            if state.metadata is None:
                state.metadata = {}
            state.metadata["local_agent_error"] = f"Timeout after {timeout}s"
            state.metadata["local_agent_time"] = timeout
            state.metadata["agent_mode"] = "bare" if bare else "local"
            return state

        elapsed = time.monotonic() - start

        if state.metadata is None:
            state.metadata = {}

        state.metadata["local_agent_time"] = elapsed
        state.metadata["agent_mode"] = "bare" if bare else "local"

        if proc.returncode != 0:
            err_text = stderr.decode("utf-8", errors="replace")[:500] if stderr else ""
            state.output = ModelOutput.from_content(
                model=f"local-{agent_name}", content=""
            )
            state.metadata["local_agent_error"] = err_text
            state.metadata["local_agent_rc"] = proc.returncode
            return state

        # Parse output using agent-specific parser
        result_text = config.parse_output(stdout)

        state.output = ModelOutput.from_content(
            model=f"local-{agent_name}", content=result_text
        )
        return state

    return solve
