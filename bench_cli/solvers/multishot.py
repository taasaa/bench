"""Multi-shot solver with read-only tool access to fixture directories.

Provides `read_file` and `list_directory` tools that are sandboxed to the
fixture directory. The solver chains `use_tools()` + `generate()` using
Inspect's native tool-use loop.

When `max_turns <= 1`, branches to bare `generate()` with no tool injection
to avoid changing model behavior (tool schemas affect output even at 1 turn).
"""

from __future__ import annotations

from pathlib import Path

from inspect_ai.model import ModelOutput
from inspect_ai.solver import Generate, Solver, generate, solver, use_tools
from inspect_ai.solver._task_state import TaskState
from inspect_ai.tool import Tool, tool


def sandbox_read(fixture_dir: Path, path: str) -> str:
    """Read a file sandboxed to fixture_dir. Returns content or error string."""
    resolved = (fixture_dir / path).resolve()
    if not resolved.is_relative_to(fixture_dir):
        return f"Error: path '{path}' escapes workspace boundary"
    if not resolved.is_file():
        return f"Error: file '{path}' not found"
    try:
        return resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading '{path}': {exc}"


def sandbox_list(fixture_dir: Path, path: str = ".") -> str:
    """List directory contents sandboxed to fixture_dir. Returns listing or error."""
    resolved = (fixture_dir / path).resolve()
    if not resolved.is_relative_to(fixture_dir):
        return f"Error: path '{path}' escapes workspace boundary"
    if not resolved.is_dir():
        return f"Error: directory '{path}' not found"
    entries = sorted((f"{'DIR' if p.is_dir() else 'FILE':4s} {p.name}") for p in resolved.iterdir())
    return "\n".join(entries) if entries else "(empty directory)"


def _make_sandboxed_tools(fixture_dir: Path) -> list[Tool]:
    """Create read_file and list_directory tools sandboxed to fixture_dir.

    Uses inspect-ai's factory pattern: @tool decorates an outer function
    that returns an inner async execute function.
    """

    @tool(name="read_file")
    def read_file():
        async def execute(path: str) -> str:
            """Read the contents of a file in the project workspace.

            Args:
                path: Relative path to the file (e.g. "src/main.py").
            """
            return sandbox_read(fixture_dir, path)

        return execute

    @tool(name="list_directory")
    def list_directory():
        async def execute(path: str = ".") -> str:
            """List files and directories in the given path.

            Args:
                path: Relative directory path (default: workspace root).
            """
            return sandbox_list(fixture_dir, path)

        return execute

    return [read_file(), list_directory()]


def _build_fixture_context(fixture_path: str | None) -> str:
    """Build initial context message listing available fixture files."""
    if fixture_path is None:
        return ""

    from bench_cli.fixtures import list_fixture_files

    p = Path(fixture_path)
    task_dir = str(p.parent.parent)
    scenario_id = p.name
    files = list_fixture_files(task_dir, scenario_id)

    if not files:
        return ""

    file_list = "\n".join(f"  - {f}" for f in files)
    return (
        f"You have access to the following files in the project workspace:\n"
        f"{file_list}\n"
        f"Use read_file(path) to read any file and list_directory(path) to explore directories."
    )


@solver
def multishot_solver(
    max_turns: int = 1,
    tools: list[Tool] | None = None,
) -> Solver:
    """Multi-shot solver with read-only tool access to fixture directories.

    Args:
        max_turns: Maximum tool-use turns. When <= 1, falls back to bare
            generate() with no tool injection.
        tools: Custom tool list. If None and max_turns > 1, uses default
            read_file/list_directory sandboxed to fixture directory.
    """
    if max_turns <= 1:
        # Bare generate — no tool injection. Tool schemas change model
        # behavior even at 1 turn, so we branch at code level.
        return generate()

    async def solve(state: TaskState, generate_fn: Generate) -> TaskState:
        fixture_path = state.metadata.get("fixture_path") if state.metadata else None

        # Resolve tools: custom or sandboxed defaults
        if tools is not None:
            active_tools = tools
        elif fixture_path:
            active_tools = _make_sandboxed_tools(Path(fixture_path))
        else:
            # No fixture dir — no tools needed, just generate
            return await generate_fn(state)

        # Inject fixture context as initial system hint
        context_msg = _build_fixture_context(fixture_path)
        if context_msg and state.messages:
            from inspect_ai.model import ChatMessageSystem

            state.messages.insert(0, ChatMessageSystem(content=context_msg))

        # Chain: register tools → generate with tool loop
        tool_solver = use_tools(*active_tools)
        state = await tool_solver(state, generate_fn)
        state = await generate_fn(state)

        # Fix state.output — Inspect's tool loop doesn't update it
        last_text = ""
        for msg in reversed(state.messages):
            text = getattr(msg, "text", None)
            if text:
                last_text = text
                break

        state.output = ModelOutput(
            model=str(state.model),
            completion=last_text,
        )
        return state

    return solve
