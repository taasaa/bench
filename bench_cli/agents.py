"""Agent config registry: per-agent CLI settings for local and Docker eval.

Each agent (claude, codex, gemini) has a config defining:
  - How to invoke it locally as a subprocess
  - How to parse its JSON/text output
  - Which inspect-swe solver to use for Docker mode
  - Whether it supports a "bare" (no-harness) flag

Add new agents by appending to AGENT_REGISTRY.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for a CLI agent."""

    name: str
    binary: str  # CLI binary name (looked up via shutil.which)
    local_cmd: list[str]  # base command for non-interactive local run
    bare_flag: list[str]  # flags to add for bare mode (empty = unsupported)
    prompt_separator: list[str]  # separator before prompt arg (e.g. ["--"] or [])
    docker_solver: str  # inspect-swe function name: "claude_code", "codex_cli", "gemini_cli"

    def cli_available(self) -> bool:
        """Check if the agent CLI is installed."""
        return shutil.which(self.binary) is not None

    def build_cmd(self, prompt: str, bare: bool = False, model: str | None = None) -> list[str]:
        """Build the full subprocess command.

        Args:
            prompt: The prompt to send to the agent.
            bare: If True, run in bare mode (skip hooks/CLAUDE.md).
            model: CCR-style model name to pass via --model flag.
                E.g. 'litellm,thinking', 'kilocode,opus'. Only used for claude agent.
        """
        cmd = self.local_cmd.copy()
        if bare and self.bare_flag:
            cmd.extend(self.bare_flag)
        if model and self.name == "claude":
            cmd.extend(["--model", model])
        cmd.extend(self.prompt_separator)
        cmd.append(prompt)
        return cmd

    def parse_output(self, stdout: bytes) -> str:
        """Parse agent stdout and return the text result."""
        text = stdout.decode("utf-8", errors="replace").strip()
        if not text:
            return ""

        # Try JSON parsing
        try:
            data = json.loads(text)
            return _extract_result(self.name, data)
        except (json.JSONDecodeError, ValueError):
            pass

        # Try JSONL (codex streams one JSON object per line)
        try:
            return _extract_jsonl_result(text)
        except (json.JSONDecodeError, ValueError):
            pass

        # Fall back to raw text
        return text


def _extract_result(agent_name: str, data: dict) -> str:
    """Extract the text result from a JSON response."""
    # claude: {"type": "result", "result": "..."}
    if "result" in data and isinstance(data["result"], str):
        return data["result"]

    # gemini: {"response": "..."}
    if "response" in data and isinstance(data["response"], str):
        return data["response"]

    # Fallback: look for common fields
    for key in ("result", "response", "text", "content", "output"):
        if key in data and isinstance(data[key], str):
            return data[key]

    return json.dumps(data)[:500]


def _extract_jsonl_result(text: str) -> str:
    """Extract result from JSONL stream (codex format).

    Codex outputs one JSON object per line. We look for the last
    item.completed event and extract its text.
    """
    last_text = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("type") == "item.completed":
            item = obj.get("item", {})
            if isinstance(item.get("text"), str):
                last_text = item["text"]
    if last_text:
        return last_text
    raise ValueError("No item.completed found in JSONL")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

AGENT_REGISTRY: dict[str, AgentConfig] = {
    "claude": AgentConfig(
        name="claude",
        binary="claude",
        local_cmd=["claude", "--print", "--output-format", "json"],
        bare_flag=["--bare"],
        prompt_separator=["--"],
        docker_solver="claude_code",
    ),
    "codex": AgentConfig(
        name="codex",
        binary="codex",
        local_cmd=["codex", "exec", "--json"],
        bare_flag=[],  # codex has no bare mode
        prompt_separator=[],
        docker_solver="codex_cli",
    ),
    "gemini": AgentConfig(
        name="gemini",
        binary="gemini",
        local_cmd=["gemini", "--output-format", "json"],
        bare_flag=[],  # gemini has no bare mode
        prompt_separator=["-p"],
        docker_solver="gemini_cli",
    ),
}


def get_agent_config(name: str) -> AgentConfig:
    """Look up agent config by name."""
    config = AGENT_REGISTRY.get(name)
    if config is None:
        raise ValueError(f"Unknown agent {name!r}. Available: {', '.join(AGENT_REGISTRY)}")
    return config


def available_agents() -> list[str]:
    """Return agent names whose CLIs are installed and in PATH."""
    return [name for name, config in AGENT_REGISTRY.items() if config.cli_available()]


AGENT_MODES = ("local", "bare", "docker", "harness")
