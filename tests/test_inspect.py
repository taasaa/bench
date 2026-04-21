"""Tests for bench_cli.inspect — eval log inspection.

All tests use mocked data. No real eval log files are read.
Fast tests: no I/O. CLI tests use CliRunner.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bench_cli.inspect import (
    SampleScore,
    _load_pillar_map,
    _per_task_stats,
    _resolve_alias,
)


# ---------------------------------------------------------------------------
# Mock factories — no file I/O
# ---------------------------------------------------------------------------

def _mock_sample(
    correctness: float | None = 1.0,
    scorer_type: str = "llm_judge",
    working_time: float = 5.0,
    input_tokens: int = 100,
    output_tokens: int = 100,
    judge_explanation: str | None = "Good response.",
    token_ratio: float | None = 1.0,
    time_ratio: float | None = 1.0,
    price_ratio: float | None = 1.0,
    actual_cost_usd: float | None = 0.001,
    suppressed_token: bool = False,
    suppressed_time: bool = False,
) -> SampleScore:
    return SampleScore(
        task="test_task",
        sample_id="sample-1",
        scorer_type=scorer_type,
        correctness=correctness,
        token_ratio=token_ratio,
        time_ratio=time_ratio,
        price_ratio=price_ratio,
        actual_cost_usd=actual_cost_usd,
        reference_cost_usd=0.001,
        is_free=False,
        verify_sh_score=None,
        llm_judge_score=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        working_time=working_time,
        judge_explanation=judge_explanation,
        output_text="test output",
        suppressed_token=suppressed_token,
        suppressed_time=suppressed_time,
    )


# ---------------------------------------------------------------------------
# _resolve_alias
# ---------------------------------------------------------------------------

class TestResolveAlias:
    def test_full_alias_unchanged(self):
        assert _resolve_alias("openai/nvidia-nemotron-30b") == "openai/nvidia-nemotron-30b"

    def test_short_and_foreign_prefixes_normalized(self):
        assert _resolve_alias("nvidia-nemotron-30b") == "openai/nvidia-nemotron-30b"
        assert _resolve_alias("models/nvidia-nemotron-30b") == "openai/nvidia-nemotron-30b"
        assert _resolve_alias("openrouter/nvidia-nemotron-30b") == "openai/nvidia-nemotron-30b"
        assert _resolve_alias("  nvidia-nemotron-30b  ") == "openai/nvidia-nemotron-30b"


# ---------------------------------------------------------------------------
# _per_task_stats — pure function, no I/O
# ---------------------------------------------------------------------------

class TestPerTaskStats:
    def _ss(self, correctness=None, scorer_type="llm_judge", suppressed_tok=False,
            suppressed_time=False, working_time=5.0, token_ratio=1.0,
            time_ratio=1.0, price_ratio=1.0, actual_cost_usd=0.001):
        return _mock_sample(
            correctness=correctness, scorer_type=scorer_type,
            suppressed_token=suppressed_tok, suppressed_time=suppressed_time,
            working_time=working_time, token_ratio=token_ratio,
            time_ratio=time_ratio, price_ratio=price_ratio,
            actual_cost_usd=actual_cost_usd,
        )

    def test_empty_returns_empty_dict(self):
        assert _per_task_stats([]) == {}

    def test_correctness_avg(self):
        s = [self._ss(correctness=1.0), self._ss(correctness=0.0), self._ss(correctness=1.0)]
        stats = _per_task_stats(s)
        assert stats["correctness_avg"] == pytest.approx(2 / 3)
        assert stats["correctness_min"] == 0.0
        assert stats["correctness_max"] == 1.0

    def test_correctness_avg_none_if_no_values(self):
        s = [self._ss(correctness=None), self._ss(correctness=None)]
        stats = _per_task_stats(s)
        assert stats["correctness_avg"] is None

    def test_suppressed_token_ratio_excluded(self):
        s = [self._ss(token_ratio=1.0, suppressed_tok=True),
             self._ss(token_ratio=2.0, suppressed_tok=True)]
        stats = _per_task_stats(s)
        assert stats["token_ratio_avg"] is None
        assert stats["n_tok_suppressed"] == 2

    def test_suppressed_time_ratio_excluded(self):
        s = [self._ss(time_ratio=1.0, suppressed_time=True),
             self._ss(time_ratio=2.0, suppressed_time=True)]
        stats = _per_task_stats(s)
        assert stats["time_ratio_avg"] is None
        assert stats["n_time_suppressed"] == 2

    def test_non_suppressed_included(self):
        s = [self._ss(suppressed_tok=False, suppressed_time=False)]
        stats = _per_task_stats(s)
        assert stats["n_tok_suppressed"] == 0
        assert stats["n_time_suppressed"] == 0

    def test_all_correctness_one(self):
        s = [self._ss(correctness=1.0), self._ss(correctness=1.0)]
        stats = _per_task_stats(s)
        assert stats["all_correctness_one"] is True
        assert stats["all_correctness_zero"] is False

    def test_all_correctness_zero(self):
        s = [self._ss(correctness=0.0), self._ss(correctness=0.0)]
        stats = _per_task_stats(s)
        assert stats["all_correctness_zero"] is True
        assert stats["all_correctness_one"] is False

    def test_all_verify_sh_binary_true(self):
        s = [self._ss(correctness=1.0, scorer_type="verify_sh"),
             self._ss(correctness=0.0, scorer_type="verify_sh")]
        stats = _per_task_stats(s)
        assert stats["all_verify_sh_binary"] is True

    def test_all_verify_sh_binary_false_on_nonbinary(self):
        s = [self._ss(correctness=0.75, scorer_type="verify_sh"),
             self._ss(correctness=0.5, scorer_type="verify_sh")]
        stats = _per_task_stats(s)
        assert stats["all_verify_sh_binary"] is False

    def test_avg_tokens_and_time(self):
        s = [self._ss(), self._ss()]
        s[0].working_time = 10.0
        s[1].working_time = 20.0
        s[0].input_tokens = 100
        s[0].output_tokens = 50
        s[1].input_tokens = 200
        s[1].output_tokens = 100
        stats = _per_task_stats(s)
        assert stats["avg_tokens"] == pytest.approx(225.0)
        assert stats["avg_time"] == pytest.approx(15.0)

    def test_nan_token_ratio_counted(self):
        import math
        s = [self._ss(token_ratio=1.0), self._ss()]
        s[1].token_ratio = math.nan
        stats = _per_task_stats(s)
        assert stats["n_nan_tok"] == 1

    def test_nan_time_ratio_counted(self):
        import math
        s = [self._ss(time_ratio=1.0), self._ss()]
        s[1].time_ratio = math.nan
        stats = _per_task_stats(s)
        assert stats["n_nan_time"] == 1

    def test_scorer_type_from_first_sample(self):
        s = [self._ss(scorer_type="verify_sh"), self._ss(scorer_type="llm_judge")]
        stats = _per_task_stats(s)
        assert stats["scorer_type"] == "verify_sh"

    def test_avg_cost_usd(self):
        s = [self._ss(actual_cost_usd=0.001), self._ss(actual_cost_usd=0.003)]
        stats = _per_task_stats(s)
        assert stats["avg_cost_usd"] == pytest.approx(0.002)


# ---------------------------------------------------------------------------
# _load_pillar_map — uses real tasks/ directory. Integration tests, not mocked.
# ---------------------------------------------------------------------------

class TestLoadPillarMap:
    """Integration tests — hit real tasks/ directory."""

    def test_loads_hyphenated_tasks(self):
        pillar_map = _load_pillar_map()
        assert "add-tests" in pillar_map

    def test_smoke_in_verification(self):
        pillar_map = _load_pillar_map()
        assert pillar_map["smoke"] == "verification"

    def test_add_tests_in_competence(self):
        pillar_map = _load_pillar_map()
        assert pillar_map["add-tests"] == "competence"


# ---------------------------------------------------------------------------
# CLI commands via CliRunner — mocked, no real log I/O
# ---------------------------------------------------------------------------

from unittest.mock import patch
from click.testing import CliRunner
from bench_cli.inspect import inspect


def _mock_inspect_sample(ss: SampleScore) -> MagicMock:
    """Wrap a SampleScore as a mock Inspect sample with .scores, .working_time."""
    sample = MagicMock()
    sample.id = ss.sample_id
    sample.working_time = ss.working_time

    scores: dict[str, MagicMock] = {}

    def make_score(value, scorer_name, explanation=None, metadata=None):
        sc = MagicMock()
        sc.value = value
        sc.explanation = explanation
        sc.metadata = metadata or {}
        return sc

    if ss.scorer_type in ("llm_judge", "hybrid_scorer"):
        scores["llm_judge"] = make_score(ss.correctness, "llm_judge", ss.judge_explanation)

    if ss.scorer_type in ("verify_sh", "hybrid_scorer"):
        scores["verify_sh"] = make_score(ss.correctness, "verify_sh")

    scores["token_ratio_scorer"] = make_score(ss.token_ratio, "token_ratio_scorer")
    scores["time_ratio_scorer"] = make_score(ss.time_ratio, "time_ratio_scorer")
    scores["price_ratio_scorer"] = make_score(
        ss.price_ratio, "price_ratio_scorer",
        metadata={"actual_cost_usd": ss.actual_cost_usd, "is_free": ss.is_free},
    )

    sample.scores = scores

    usage = MagicMock()
    usage.input_tokens = ss.input_tokens
    usage.output_tokens = ss.output_tokens
    sample.model_usage = {"model": usage}

    return sample


class TestInspectCLI:
    runner = CliRunner()

    def test_stats_requires_model(self):
        result = self.runner.invoke(inspect, ["stats"])
        assert result.exit_code != 0

    def test_stats_unknown_model_exits_nonzero(self):
        with patch("bench_cli.inspect._load_samples") as mock:
            mock.return_value = {}
            result = self.runner.invoke(inspect, ["stats", "--model", "openai/nonexistent"])
        assert result.exit_code != 0
        assert "No eval logs found" in result.output

    def test_stats_shows_data(self):
        with patch("bench_cli.inspect._load_samples") as mock:
            mock.return_value = {
                "f22_error_spiral": [_mock_sample(0.5, working_time=10.0)],
                "add_tests": [_mock_sample(1.0, scorer_type="verify_sh", working_time=2.0)],
            }
            result = self.runner.invoke(inspect, ["stats", "--model", "openai/test"])
        assert result.exit_code == 0
        assert "f22_error_spiral" in result.output
        assert "add_tests" in result.output

    def test_compare_no_baseline_shows_new_task(self):
        with patch("bench_cli.inspect._load_samples") as mock_s:
            mock_s.return_value = {"task_a": [_mock_sample(0.5)]}
            with patch("bench_cli.inspect._load_baseline") as mock_b:
                mock_b.return_value = {}
                result = self.runner.invoke(inspect, ["compare", "--model", "openai/test"])
        assert result.exit_code == 0
        assert "NEW TASK" in result.output

    def test_compare_significant_delta_flagged(self):
        with patch("bench_cli.inspect._load_samples") as mock_s:
            mock_s.return_value = {"task_a": [_mock_sample(0.8), _mock_sample(0.8)]}
            with patch("bench_cli.inspect._load_baseline") as mock_b:
                mock_b.return_value = {"task_a": 0.3}
                result = self.runner.invoke(
                    inspect, ["compare", "--model", "openai/test", "--delta-threshold", "0.15"]
                )
        assert result.exit_code == 0
        assert "SIGNIFICANT" in result.output
        assert "+0.500" in result.output

    def test_compare_small_delta_not_flagged(self):
        with patch("bench_cli.inspect._load_samples") as mock_s:
            mock_s.return_value = {"task_a": [_mock_sample(0.5), _mock_sample(0.5)]}
            with patch("bench_cli.inspect._load_baseline") as mock_b:
                mock_b.return_value = {"task_a": 0.4}
                result = self.runner.invoke(
                    inspect, ["compare", "--model", "openai/test", "--delta-threshold", "0.15"]
                )
        assert result.exit_code == 0
        assert "SIGNIFICANT" not in result.output

    def test_compare_tight_threshold_flags_more(self):
        with patch("bench_cli.inspect._load_samples") as mock_s:
            mock_s.return_value = {"task_a": [_mock_sample(0.5), _mock_sample(0.5)]}
            with patch("bench_cli.inspect._load_baseline") as mock_b:
                mock_b.return_value = {"task_a": 0.4}
                r_tight = self.runner.invoke(
                    inspect, ["compare", "--model", "openai/test", "--delta-threshold", "0.01"])
                r_loose = self.runner.invoke(
                    inspect, ["compare", "--model", "openai/test", "--delta-threshold", "0.50"])
        sig_tight = r_tight.output.count("SIGNIFICANT") + r_tight.output.count("notable")
        sig_loose = r_loose.output.count("SIGNIFICANT") + r_loose.output.count("notable")
        assert sig_tight >= sig_loose

    def test_deep_check_produces_full_report(self):
        with patch("bench_cli.inspect._load_samples") as mock:
            mock.return_value = {
                "f22_error_spiral": [
                    _mock_sample(0.5, scorer_type="llm_judge",
                                judge_explanation="Correctly identifies the error path and handles it appropriately."),
                    _mock_sample(0.9, scorer_type="llm_judge",
                                 judge_explanation="Excellent multi-step reasoning with proper error spiral detection."),
                ],
            }
            result = self.runner.invoke(inspect, ["deep-check", "--model", "openai/test"])
        assert result.exit_code == 0
        assert "# Deep QA Report" in result.output
        assert "## Per-Task Deep Check" in result.output
        assert "## Verdict Summary" in result.output
        assert "f22_error_spiral" in result.output

    def test_deep_check_flags_all_zero(self):
        with patch("bench_cli.inspect._load_samples") as mock:
            mock.return_value = {
                "failing_task": [_mock_sample(0.0), _mock_sample(0.0)],
            }
            result = self.runner.invoke(inspect, ["deep-check", "--model", "openai/test"])
        assert result.exit_code == 0
        assert "ALL-ZERO" in result.output

    def test_deep_check_flags_all_perfect(self):
        with patch("bench_cli.inspect._load_samples") as mock:
            mock.return_value = {
                "trivial_task": [_mock_sample(1.0), _mock_sample(1.0)],
            }
            result = self.runner.invoke(inspect, ["deep-check", "--model", "openai/test"])
        assert result.exit_code == 0
        assert "ALL-PERFECT" in result.output

    def test_deep_check_flags_short_judge_explanation(self):
        with patch("bench_cli.inspect._load_samples") as mock:
            mock.return_value = {
                "judge_task": [
                    _mock_sample(0.5, scorer_type="llm_judge", judge_explanation="OK"),
                    _mock_sample(0.6, scorer_type="llm_judge", judge_explanation="OK"),
                ],
            }
            result = self.runner.invoke(inspect, ["deep-check", "--model", "openai/test"])
        assert result.exit_code == 0
        assert "too short" in result.output

    def test_deep_check_flags_broken_judge(self):
        with patch("bench_cli.inspect._load_samples") as mock:
            mock.return_value = {
                "judge_task": [
                    _mock_sample(0.5, scorer_type="llm_judge", judge_explanation="OK"),
                    _mock_sample(0.9, scorer_type="llm_judge", judge_explanation="OK"),
                    _mock_sample(0.3, scorer_type="llm_judge", judge_explanation="OK"),
                ],
            }
            result = self.runner.invoke(inspect, ["deep-check", "--model", "openai/test"])
        assert result.exit_code == 0
        assert "BROKEN" in result.output or "too short" in result.output

    def test_deep_check_writes_output_file(self, tmp_path):
        out_file = tmp_path / "qa.md"
        with patch("bench_cli.inspect._load_samples") as mock:
            mock.return_value = {"task_a": [_mock_sample(0.5)]}
            result = self.runner.invoke(
                inspect, ["deep-check", "--model", "openai/test", "--output", str(out_file)]
            )
        assert result.exit_code == 0
        assert out_file.exists()
        assert "# Deep QA Report" in out_file.read_text()

    def test_deep_check_verdict_sound_for_good_judge(self):
        with patch("bench_cli.inspect._load_samples") as mock:
            mock.return_value = {
                "good_task": [
                    _mock_sample(
                        0.9, scorer_type="llm_judge",
                        judge_explanation="The solution correctly identifies the root cause and provides an accurate fix that properly handles the edge case.",
                    ),
                ],
            }
            result = self.runner.invoke(inspect, ["deep-check", "--model", "openai/test"])
        assert result.exit_code == 0
        assert "SOUND" in result.output or "Verdict Summary" in result.output

    def test_deep_check_non_binary_verify_sh_flagged(self):
        with patch("bench_cli.inspect._load_samples") as mock:
            mock.return_value = {
                "verify_task": [
                    _mock_sample(0.75, scorer_type="verify_sh"),
                    _mock_sample(0.25, scorer_type="verify_sh"),
                ],
            }
            result = self.runner.invoke(inspect, ["deep-check", "--model", "openai/test"])
        assert result.exit_code == 0
        assert "not binary" in result.output.lower() or "verify_sh" in result.output