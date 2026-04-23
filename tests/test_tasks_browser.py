"""Tests for bench tasks browser."""

import pytest
from click.testing import CliRunner

from bench_cli.tasks_browser import tasks_cmd


@pytest.fixture
def runner():
    return CliRunner()


class TestTasksBrowser:
    def test_lists_all_pillars(self, runner):
        result = runner.invoke(tasks_cmd)
        assert result.exit_code == 0
        assert "COMPETENCE" in result.output
        assert "EXECUTION" in result.output

    def test_lists_tasks_with_names(self, runner):
        result = runner.invoke(tasks_cmd)
        assert "q1-verification-gate" in result.output

    def test_filter_by_pillar(self, runner):
        result = runner.invoke(tasks_cmd, ["competence"])
        assert result.exit_code == 0
        assert "COMPETENCE" in result.output
        assert "EXECUTION" not in result.output

    def test_filter_by_prefix(self, runner):
        result = runner.invoke(tasks_cmd, ["comp"])
        assert result.exit_code == 0
        assert "COMPETENCE" in result.output

    def test_unknown_pillar(self, runner):
        result = runner.invoke(tasks_cmd, ["nonexistent"])
        assert result.exit_code == 0
        assert "Unknown pillar" in result.output

    def test_scores_flag(self, runner):
        result = runner.invoke(tasks_cmd, ["--scores"])
        # May or may not have score data, but should not crash
        assert result.exit_code == 0
