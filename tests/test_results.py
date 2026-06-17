"""Tests for bench_cli.results: model card generation."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from bench_cli.results import (
    _compute_pillar_scores,
    _extract_task_scores,
    _format_ratio,
    _generate_summary,
    _rating,
    _real_model_name,
    _slug_from_alias,
    generate_card,
    generate_card_for_model,
    results,
)

# ---------------------------------------------------------------------------
# _rating
# ---------------------------------------------------------------------------


class TestRating:
    def test_boundaries(self):
        assert _rating(0.90) == "excellent"
        assert _rating(0.89) == "good"
        assert _rating(0.75) == "good"
        assert _rating(0.74) == "fair"
        assert _rating(0.60) == "fair"
        assert _rating(0.59) == "weak"
        assert _rating(0.0) == "weak"

    def test_high_ratio(self):
        assert _rating(2.5) == "excellent"


# ---------------------------------------------------------------------------
# _format_ratio
# ---------------------------------------------------------------------------


class TestFormatRatio:
    def test_special_values(self):
        assert _format_ratio(None) == "--"
        assert _format_ratio(float("nan")) == "--"
        assert _format_ratio(float("inf")) == "FREE"

    def test_numeric(self):
        assert _format_ratio(1.234) == "1.234"
        assert _format_ratio(0.0) == "0.000"


# ---------------------------------------------------------------------------
# _compute_pillar_scores
# ---------------------------------------------------------------------------


class TestComputePillarScores:
    def test_empty_tasks(self):
        result = _compute_pillar_scores({})
        assert result["correctness"] == 0
        assert result["token_ratio"] == 0
        assert result["time_ratio"] == 0
        assert result["price_ratio"] == 0

    def test_verify_sh_tasks(self):
        tasks = {
            "task-a": {
                "scores": {
                    "verify_sh": 1.0,
                    "token_ratio_scorer": 1.5,
                    "time_ratio_scorer": 2.0,
                    "price_ratio_scorer": 1.2,
                }
            },
            "task-b": {
                "scores": {
                    "verify_sh": 0.5,
                    "token_ratio_scorer": 0.5,
                    "time_ratio_scorer": 1.0,
                    "price_ratio_scorer": 0.8,
                }
            },
        }
        result = _compute_pillar_scores(tasks)
        assert result["correctness"] == 0.75
        assert result["token_ratio"] == 1.0
        assert result["time_ratio"] == 1.5
        assert result["price_ratio"] == 1.0

    def test_llm_judge_tasks(self):
        tasks = {
            "task-a": {"scores": {"llm_judge": 0.8, "token_ratio_scorer": 0.4}},
        }
        result = _compute_pillar_scores(tasks)
        assert result["correctness"] == 0.8
        assert result["token_ratio"] == 0.4

    def test_nan_scorers_excluded(self):
        tasks = {
            "task-a": {
                "scores": {
                    "verify_sh": 1.0,
                    "time_ratio_scorer": float("nan"),
                    "price_ratio_scorer": float("inf"),
                }
            },
        }
        result = _compute_pillar_scores(tasks)
        assert result["correctness"] == 1.0
        assert result["time_ratio"] == 0
        assert result["price_ratio"] == 0

    def test_mixed_scorer_types(self):
        tasks = {
            "task-a": {"scores": {"verify_sh": 1.0, "token_ratio_scorer": 1.0}},
            "task-b": {"scores": {"llm_judge": 0.5, "token_ratio_scorer": 0.5}},
        }
        result = _compute_pillar_scores(tasks)
        assert result["correctness"] == 0.75
        assert result["token_ratio"] == 0.75


# ---------------------------------------------------------------------------
# _slug_from_alias
# ---------------------------------------------------------------------------


class TestSlugFromAlias:
    def test_produces_slug_without_slash(self):
        slug = _slug_from_alias("openai/gemma-4-26-local")
        assert "gemma" in slug
        assert "/" not in slug

    def test_unknown_model_falls_back(self):
        slug = _slug_from_alias("openai/some-unknown-model")
        assert "some-unknown-model" in slug


# ---------------------------------------------------------------------------
# _slug_from_alias / _real_model_name determinism (W2a)
# ---------------------------------------------------------------------------


class TestDeterministicCardIdentity:
    """W2a: card slug/name are deterministic from the static alias map, never volatile."""

    def test_slug_known_alias_matches_orid(self):
        # Recorded OR id -> slug (full name with '/' -> '-').
        assert _slug_from_alias("nvidia/nemotron-3-nano-30b-a3b") == "nvidia-nemotron-3-nano-30b-a3b"
        assert "/" not in _slug_from_alias("nvidia/nemotron-3-nano-30b-a3b")

    def test_slug_unknown_alias_bare(self):
        # An arbitrary recorded OR id still slugs predictably with '/' -> '-'.
        slug = _slug_from_alias("some-brand/new-model")
        assert slug == "some-brand-new-model"

    def test_slug_invariant_to_cache_drift(self, monkeypatch):
        # Even if resolve_openrouter_id flips/returns None, the slug must NOT change.
        monkeypatch.setattr(
            "bench_cli.results.core.resolve_openrouter_id", lambda a: None
        )
        assert _slug_from_alias("nvidia/nemotron-3-nano-30b-a3b") == "nvidia-nemotron-3-nano-30b-a3b"

    def test_real_name_matches_orid(self):
        assert _real_model_name("nvidia/nemotron-3-nano-30b-a3b") == "nvidia/nemotron-3-nano-30b-a3b"

    def test_two_distinct_models_never_collide(self, tmp_path, monkeypatch):
        """Guards the deleted glm-5.1 == m2.7 byte-identical card bug.

        Two distinct bench aliases that map to distinct or_ids MUST produce
        distinct slug + name AND distinct generated card filenames + title lines --
        never identical card data. (Compares actual generated card content, not just
        the slug derivation, so it directly guards the historical byte-identical card.)
        """
        monkeypatch.setattr("bench_cli.results.core._RESULTS_DIR", tmp_path)
        a = "openai/nvidia-nemotron-30b"        # -> nvidia/nemotron-3-nano-30b-a3b
        b = "openai/fabric"                      # -> nvidia/nemotron-3-super-120b-a12b
        # 1. derivation-level distinctness
        assert _slug_from_alias(a) != _slug_from_alias(b)
        assert _real_model_name(a) != _real_model_name(b)
        # 2. file-level distinctness (the user-visible collision)
        data = {
            "tasks": {"add-tests": {"date": "2026-04-20", "samples": 1, "input_tokens": 1,
                                   "output_tokens": 1, "scores": {"verify_sh": 1.0}}},
            "dates": ["2026-04-20"], "total_input": 1, "total_output": 1,
        }
        pa = generate_card(a, dict(data), tmp_path)
        pb = generate_card(b, dict(data), tmp_path)
        assert pa is not None and pb is not None
        assert pa.name != pb.name                       # distinct filenames
        assert pa.read_text().splitlines()[0] != pb.read_text().splitlines()[0]  # distinct title lines


# ---------------------------------------------------------------------------
# _extract_task_scores
# ---------------------------------------------------------------------------


class TestExtractTaskScores:
    def test_extracts_correctness(self):
        tasks = {
            "add-tests": {"scores": {"verify_sh": 1.0}},
            "f1-multi-file-verify": {"scores": {"llm_judge": 0.85}},
        }
        scores = _extract_task_scores(tasks)
        assert len(scores) == 2
        names = [s[0] for s in scores]
        assert "add-tests" in names
        assert "f1-multi-file-verify" in names

    def test_no_scorer(self):
        tasks = {"no-scores": {"scores": {}}}
        scores = _extract_task_scores(tasks)
        assert len(scores) == 0

    def test_pillar_mapped(self):
        tasks = {"add-tests": {"scores": {"verify_sh": 1.0}}}
        scores = _extract_task_scores(tasks)
        assert scores[0][2] == "competence"


# ---------------------------------------------------------------------------
# _generate_summary
# ---------------------------------------------------------------------------


class TestGenerateSummary:
    def test_high_correctness(self):
        pillars = {"correctness": 0.90, "token_ratio": 1.5, "time_ratio": 2.0, "price_ratio": 1.5}
        task_scores = [("task-a", 0.95, "competence"), ("task-b", 0.85, "execution")]
        summary = _generate_summary("test/model", pillars, task_scores, "openai/nvidia-devstral")
        assert "strong reliability" in summary
        assert "Recommended for:" in summary

    def test_mid_correctness(self):
        pillars = {"correctness": 0.78, "token_ratio": 0.8, "time_ratio": 0.5, "price_ratio": 0.9}
        task_scores = [("task-a", 0.9, "competence"), ("task-b", 0.6, "execution")]
        summary = _generate_summary("test/model", pillars, task_scores, "openai/nvidia-devstral")
        assert "solid" in summary
        assert "below benchmark" in summary

    def test_free_model(self):
        pillars = {"correctness": 0.72, "token_ratio": 0.8, "time_ratio": 0.5, "price_ratio": 0.0}
        task_scores = [("task-a", 0.8, "competence")]
        summary = _generate_summary("test/model", pillars, task_scores, "openai/qwen-local")
        assert "free model" in summary

    def test_weak_model(self):
        pillars = {"correctness": 0.50, "token_ratio": 0.5, "time_ratio": 0.3, "price_ratio": 0.2}
        task_scores = [("task-a", 0.5, "competence")]
        summary = _generate_summary("test/model", pillars, task_scores, "openai/nvidia-devstral")
        assert "struggles" in summary

    def test_strengths_and_weaknesses(self):
        pillars = {"correctness": 0.80, "token_ratio": 1.0, "time_ratio": 1.0, "price_ratio": 1.0}
        task_scores = [
            ("good-task", 0.95, "competence"),
            ("bad-task", 0.40, "execution"),
        ]
        summary = _generate_summary("test/model", pillars, task_scores, "openai/nvidia-devstral")
        assert "Strengths:" in summary
        assert "Weaknesses:" in summary


# ---------------------------------------------------------------------------
# generate_card
# ---------------------------------------------------------------------------


class TestGenerateCard:
    def test_returns_none_for_empty_tasks(self, tmp_path):
        result = generate_card("openai/test", {"tasks": {}}, tmp_path)
        assert result is None

    def test_generates_card_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bench_cli.results.core._RESULTS_DIR", tmp_path)

        model_data = {
            "tasks": {
                "add-tests": {
                    "date": "2026-04-20",
                    "samples": 4,
                    "input_tokens": 500,
                    "output_tokens": 3000,
                    "scores": {
                        "verify_sh": 1.0,
                        "token_ratio_scorer": 1.5,
                        "time_ratio_scorer": 2.0,
                        "price_ratio_scorer": 1.2,
                    },
                },
            },
            "dates": ["2026-04-20"],
            "total_input": 500,
            "total_output": 3000,
        }
        path = generate_card("openai/qwen-local", model_data, tmp_path)
        assert path is not None
        assert path.exists()
        content = path.read_text()
        assert "## Overview" in content
        assert "## Overall Scores" in content
        assert "## Per-Task Results" in content
        assert "## Strengths & Weaknesses" in content
        assert "## Token Usage" in content
        assert "## Summary" in content
        assert "add-tests" in content
        assert "FREE" in content

    def test_smoke_tasks_filtered(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bench_cli.results.core._RESULTS_DIR", tmp_path)

        model_data = {
            "tasks": {
                "smoke": {
                    "date": "2026-04-20",
                    "samples": 1,
                    "input_tokens": 50,
                    "output_tokens": 50,
                    "scores": {},
                },
                "agent-smoke": {
                    "date": "2026-04-20",
                    "samples": 1,
                    "input_tokens": 50,
                    "output_tokens": 50,
                    "scores": {},
                },
                "add-tests": {
                    "date": "2026-04-20",
                    "samples": 4,
                    "input_tokens": 500,
                    "output_tokens": 3000,
                    "scores": {"verify_sh": 1.0},
                },
            },
            "dates": ["2026-04-20"],
            "total_input": 600,
            "total_output": 3100,
        }
        path = generate_card("openai/qwen-local", model_data, tmp_path)
        content = path.read_text()
        assert "smoke" not in content.split("## Per-Task Results")[1].split("## Strengths")[0]
        assert "add-tests" in content

    def test_card_contains_all_sections(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bench_cli.results.core._RESULTS_DIR", tmp_path)

        model_data = {
            "tasks": {
                "f1-multi-file-verify": {
                    "date": "2026-04-20",
                    "samples": 4,
                    "input_tokens": 12000,
                    "output_tokens": 11000,
                    "scores": {
                        "llm_judge": 0.85,
                        "token_ratio_scorer": 0.46,
                        "time_ratio_scorer": 0.76,
                    },
                },
            },
            "dates": ["2026-04-20"],
            "total_input": 12000,
            "total_output": 11000,
        }
        path = generate_card("openai/nvidia-devstral", model_data, tmp_path)
        content = path.read_text()
        assert "0.850" in content
        assert "0.460" in content
        assert "llm_judge" in content

    def test_overwrite_on_rerun(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bench_cli.results.core._RESULTS_DIR", tmp_path)

        model_data_v1 = {
            "tasks": {
                "add-tests": {
                    "date": "2026-04-19",
                    "samples": 4,
                    "input_tokens": 500,
                    "output_tokens": 3000,
                    "scores": {"verify_sh": 0.5},
                }
            },
            "dates": ["2026-04-19"],
            "total_input": 500,
            "total_output": 3000,
        }
        model_data_v2 = {
            "tasks": {
                "add-tests": {
                    "date": "2026-04-20",
                    "samples": 4,
                    "input_tokens": 500,
                    "output_tokens": 3000,
                    "scores": {"verify_sh": 1.0},
                }
            },
            "dates": ["2026-04-20"],
            "total_input": 500,
            "total_output": 3000,
        }
        path1 = generate_card("openai/qwen-local", model_data_v1, tmp_path)
        content1 = path1.read_text()
        path2 = generate_card("openai/qwen-local", model_data_v2, tmp_path)
        content2 = path2.read_text()
        assert path1 == path2
        assert "0.500" in content1
        assert "1.000" in content2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestResultsCLI:
    def test_results_help(self):
        runner = CliRunner()
        result = runner.invoke(results, ["--help"])
        assert result.exit_code == 0
        assert "Generate and manage" in result.output

    def test_generate_help(self):
        runner = CliRunner()
        result = runner.invoke(results, ["generate", "--help"])
        assert result.exit_code == 0
        assert "--log-dir" in result.output

    def test_generate_missing_dir(self):
        runner = CliRunner()
        result = runner.invoke(results, ["generate", "--log-dir", "/nonexistent"])
        assert result.exit_code == 1
        assert "not a directory" in result.output

    def test_subcommand_registered(self):
        from bench_cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["results", "--help"])
        assert result.exit_code == 0
        assert "generate" in result.output

    def test_generate_agent_flags_in_help(self):
        runner = CliRunner()
        result = runner.invoke(results, ["generate", "--help"])
        assert result.exit_code == 0
        assert "--agent" in result.output
        assert "--agent-mode" in result.output
        assert "--model" in result.output


# ---------------------------------------------------------------------------
# Agent card naming
# ---------------------------------------------------------------------------


class TestAgentCardNaming:
    def _make_model_data(self, **overrides):
        data = {
            "tasks": {
                "add-tests": {
                    "date": "2026-04-22",
                    "samples": 4,
                    "input_tokens": 500,
                    "output_tokens": 3000,
                    "scores": {
                        "verify_sh": 1.0,
                        "token_ratio_scorer": 1.5,
                        "time_ratio_scorer": 2.0,
                        "price_ratio_scorer": 1.2,
                    },
                },
            },
            "dates": ["2026-04-22"],
            "total_input": 500,
            "total_output": 3000,
            "agent": None,
            "agent_mode": None,
        }
        data.update(overrides)
        return data

    def test_model_only_card_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bench_cli.results.core._RESULTS_DIR", tmp_path)

        data = self._make_model_data()
        path = generate_card("openai/qwen-local", data, tmp_path)
        assert path is not None
        assert "__" not in path.name
        assert path.name.endswith(".md")

    def test_agent_card_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bench_cli.results.core._RESULTS_DIR", tmp_path)

        data = self._make_model_data(agent="claude", agent_mode="docker")
        path = generate_card("nvidia/nemotron-3-nano-30b-a3b", data, tmp_path)
        assert path is not None
        assert path.name == "nvidia-nemotron-3-nano-30b-a3b__claude__docker.md"

    def test_agent_card_title(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bench_cli.results.core._RESULTS_DIR", tmp_path)

        data = self._make_model_data(agent="codex", agent_mode="local")
        path = generate_card("openai/nvidia-nemotron-30b", data, tmp_path)
        content = path.read_text()
        assert "codex (local)" in content
        assert "agent: codex/local" in content

    def test_model_only_no_agent_in_title(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bench_cli.results.core._RESULTS_DIR", tmp_path)

        data = self._make_model_data()
        path = generate_card("openai/qwen-local", data, tmp_path)
        content = path.read_text()
        assert "agent:" not in content


# ---------------------------------------------------------------------------
# generate_card_for_model with agent params
# ---------------------------------------------------------------------------


class TestGenerateCardForModel:
    def test_agent_card_with_params(self, tmp_path, monkeypatch):
        """generate_card_for_model uses composite key when agent params provided."""
        monkeypatch.setattr("bench_cli.results.core._RESULTS_DIR", tmp_path)

        path = generate_card_for_model(
            "openai/qwen-local",
            tmp_path,
            agent="claude",
            agent_mode="docker",
        )
        assert path is None


# ---------------------------------------------------------------------------
# W2b: router-tier meta-monikers must never emit cards
# ---------------------------------------------------------------------------


class TestMonikerSkip:
    """W2b: results generate emits no cards for router-tier meta-monikers."""

    @pytest.mark.parametrize("moniker", ["default", "thinking", "heavy", "background", "smart-router"])
    def test_is_moniker_alias(self, moniker):
        from bench_cli.results.core import is_moniker_alias
        assert is_moniker_alias(f"openai/{moniker}") is True
        assert is_moniker_alias("openai/nvidia-nemotron-30b") is False
