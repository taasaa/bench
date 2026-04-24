"""Tests for agent config registry and solver construction."""

import json
from unittest.mock import patch

import pytest

from bench_cli.agents import (
    AGENT_REGISTRY,
    _extract_jsonl_result,
    _extract_result,
    available_agents,
    get_agent_config,
)


class TestAgentConfig:
    """AgentConfig dataclass and registry lookups."""

    def test_all_agents_registered(self):
        assert set(AGENT_REGISTRY.keys()) == {"claude", "codex", "gemini"}

    def test_get_known_agent(self):
        cfg = get_agent_config("claude")
        assert cfg.name == "claude"
        assert cfg.binary == "claude"

    def test_get_unknown_agent_raises(self):
        with pytest.raises(ValueError, match="Unknown agent"):
            get_agent_config("nonexistent")

    def test_claude_config(self):
        cfg = get_agent_config("claude")
        assert cfg.local_cmd == ["claude", "--print", "--output-format", "json"]
        assert cfg.bare_flag == ["--bare"]
        assert cfg.prompt_separator == ["--"]
        assert cfg.docker_solver == "claude_code"

    def test_codex_config(self):
        cfg = get_agent_config("codex")
        assert cfg.local_cmd == ["codex", "exec", "--json"]
        assert cfg.bare_flag == []
        assert cfg.docker_solver == "codex_cli"

    def test_gemini_config(self):
        cfg = get_agent_config("gemini")
        assert cfg.local_cmd == ["gemini", "--output-format", "json"]
        assert cfg.bare_flag == []
        assert cfg.prompt_separator == ["-p"]
        assert cfg.docker_solver == "gemini_cli"


class TestBuildCmd:
    """AgentConfig.build_cmd() with various mode combinations."""

    def test_claude_local(self):
        cfg = get_agent_config("claude")
        cmd = cfg.build_cmd("fix the bug")
        assert cmd == ["claude", "--print", "--output-format", "json", "--", "fix the bug"]

    def test_claude_bare(self):
        cfg = get_agent_config("claude")
        cmd = cfg.build_cmd("fix the bug", bare=True)
        assert cmd == [
            "claude", "--print", "--output-format", "json",
            "--bare", "--", "fix the bug",
        ]

    def test_codex_local(self):
        cfg = get_agent_config("codex")
        cmd = cfg.build_cmd("fix the bug")
        assert cmd == ["codex", "exec", "--json", "fix the bug"]

    def test_codex_bare_ignored(self):
        """Codex has no bare mode — bare flag is empty list."""
        cfg = get_agent_config("codex")
        cmd_bare = cfg.build_cmd("fix the bug", bare=True)
        cmd_normal = cfg.build_cmd("fix the bug")
        assert cmd_bare == cmd_normal

    def test_gemini_local(self):
        cfg = get_agent_config("gemini")
        cmd = cfg.build_cmd("fix the bug")
        assert cmd == ["gemini", "--output-format", "json", "-p", "fix the bug"]


class TestParseOutput:
    """AgentConfig.parse_output() — JSON, JSONL, and raw text."""

    def test_claude_json_result(self):
        cfg = get_agent_config("claude")
        data = {"type": "result", "result": "The answer is 42"}
        out = cfg.parse_output(json.dumps(data).encode())
        assert out == "The answer is 42"

    def test_gemini_json_response(self):
        cfg = get_agent_config("gemini")
        data = {"response": "Created hello.py"}
        out = cfg.parse_output(json.dumps(data).encode())
        assert out == "Created hello.py"

    def test_codex_jsonl(self):
        cfg = get_agent_config("codex")
        lines = [
            '{"type":"item.started","item":{"id":"1"}}',
            '{"type":"item.completed","item":{"text":"Fixed the bug"}}',
        ]
        out = cfg.parse_output("\n".join(lines).encode())
        assert out == "Fixed the bug"

    def test_empty_stdout(self):
        cfg = get_agent_config("claude")
        out = cfg.parse_output(b"")
        assert out == ""

    def test_raw_text_fallback(self):
        cfg = get_agent_config("claude")
        out = cfg.parse_output(b"Just some plain text output")
        assert out == "Just some plain text output"


class TestExtractResult:
    """Unit tests for _extract_result helper."""

    def test_result_field(self):
        assert _extract_result("claude", {"result": "hello"}) == "hello"

    def test_response_field(self):
        assert _extract_result("gemini", {"response": "world"}) == "world"

    def test_fallback_content(self):
        assert _extract_result("x", {"content": "stuff"}) == "stuff"

    def test_fallback_json(self):
        data = {"unknown_key": [1, 2, 3]}
        result = _extract_result("x", data)
        assert "unknown_key" in result


class TestExtractJsonlResult:
    """Unit tests for _extract_jsonl_result helper."""

    def test_single_completed(self):
        text = '{"type":"item.completed","item":{"text":"done"}}'
        assert _extract_jsonl_result(text) == "done"

    def test_last_completed_wins(self):
        text = (
            '{"type":"item.completed","item":{"text":"first"}}\n'
            '{"type":"item.completed","item":{"text":"second"}}'
        )
        assert _extract_jsonl_result(text) == "second"

    def test_no_completed_raises(self):
        with pytest.raises(ValueError, match=r"No item\.completed"):
            _extract_jsonl_result('{"type":"other"}')


class TestAvailableAgents:
    """available_agents() checks PATH."""

    def test_returns_subset(self):
        agents = available_agents()
        assert set(agents).issubset({"claude", "codex", "gemini"})

    @patch("bench_cli.agents.shutil.which", return_value="/usr/local/bin/claude")
    def test_detects_installed(self, mock_which):
        agents = available_agents()
        assert "claude" in agents

    @patch("bench_cli.agents.shutil.which", return_value=None)
    def test_excludes_missing(self, mock_which):
        agents = available_agents()
        assert "claude" not in agents


class TestResolveAgentSolver:
    """_resolve_agent_solver routes to correct solver based on mode."""

    def test_local_mode_routes_to_local_agent(self):
        from bench_cli.run import _resolve_agent_solver

        with patch("bench_cli.solvers.local_agent.local_agent") as mock:
            mock.return_value = "local_solver"
            result = _resolve_agent_solver("claude", "local")
            mock.assert_called_once_with("claude", bare=False, model=None)
            assert result == "local_solver"

    def test_bare_mode_routes_to_local_agent_bare(self):
        from bench_cli.run import _resolve_agent_solver

        with patch("bench_cli.solvers.local_agent.local_agent") as mock:
            mock.return_value = "bare_solver"
            _resolve_agent_solver("claude", "bare")
            mock.assert_called_once_with("claude", bare=True, model=None)

    def test_docker_mode_routes_to_docker_agent(self):
        from bench_cli.run import _resolve_agent_solver

        with patch("bench_cli.solvers.docker_agent.docker_agent") as mock:
            mock.return_value = "docker_solver"
            _resolve_agent_solver("claude", "docker")
            mock.assert_called_once_with("claude", harness=False)

    def test_harness_mode_routes_to_docker_agent_harness(self):
        from bench_cli.run import _resolve_agent_solver

        with patch("bench_cli.solvers.docker_agent.docker_agent") as mock:
            mock.return_value = "harness_solver"
            _resolve_agent_solver("claude", "harness")
            mock.assert_called_once_with("claude", harness=True)
