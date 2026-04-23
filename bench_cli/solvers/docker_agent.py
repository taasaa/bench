"""Docker agent solver: wraps inspect-swe solvers with optional harness injection.

Modes:
  - docker:  Pristine agent in Docker — no hooks, no CLAUDE.md, no config
  - harness: Docker agent with harness components injected via system_prompt
"""

from __future__ import annotations

from pathlib import Path

from bench_cli.agents import get_agent_config


def _load_project_instructions() -> str:
    """Load project CLAUDE.md and global steering rules for harness injection."""
    parts: list[str] = []

    # Global user instructions
    global_claude_md = Path.home() / ".claude" / "CLAUDE.md"
    if global_claude_md.is_file():
        parts.append(global_claude_md.read_text())

    # Project-level instructions
    project_claude_md = Path("CLAUDE.md")
    if project_claude_md.is_file():
        parts.append(project_claude_md.read_text())

    return "\n\n".join(parts)


def docker_agent(agent_name: str, harness: bool = False) -> object:
    """Create an inspect-swe Docker agent solver.

    The agent's cwd is set to "workspace" so it starts inside the fixture
    directory when fixture files are mounted via sample.files.  The workspace
    directory is created by Inspect's sandbox init when sample.files contains
    a "workspace" key.

    Args:
        agent_name: Agent to use (claude, codex, gemini).
        harness: If True, inject project CLAUDE.md and global instructions
            as system_prompt into the Docker agent.

    Returns:
        Inspect solver (from inspect-swe).
    """
    try:
        from inspect_swe import claude_code, codex_cli, gemini_cli  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "Docker agent eval requires the 'inspect-swe' package. "
            "Install with: pip install 'bench[agent]'"
        ) from exc

    config = get_agent_config(agent_name)

    solvers = {
        "claude": claude_code,
        "codex": codex_cli,
        "gemini": gemini_cli,
    }
    factory = solvers.get(config.name)
    if factory is None:
        raise ValueError(f"No Docker solver for agent {agent_name!r}")

    kwargs: dict = {"cwd": "workspace"}
    if harness:
        instructions = _load_project_instructions()
        if instructions:
            kwargs["system_prompt"] = instructions

    return factory(**kwargs)
