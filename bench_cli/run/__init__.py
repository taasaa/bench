"""bench run -- discover tasks and execute them via Inspect AI."""

from bench_cli.run.cli import run
from bench_cli.run.core import _discover_tasks, _resolve_agent_solver, _resolve_task

__all__ = ["run", "_discover_tasks", "_resolve_agent_solver", "_resolve_task"]
