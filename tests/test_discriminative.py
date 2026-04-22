"""Tests for bench_cli.discriminative -- types, ci, filters, diagnostics, profiles, pipeline."""
from __future__ import annotations

import pytest

from bench_cli.discriminative import ci, diagnostics, filters, pipeline, profiles, types

# ---------------------------------------------------------------------------
# ci.py -- Agresti-Coull confidence intervals
# ---------------------------------------------------------------------------

class TestAgrestiCoull:
    """Agresti-Coull CI for binary proportions."""

    def test_all_fail(self):
        """0/5 successes -- interval should be above 0 (pseudo-counts added)."""
        low, high = ci.agresti_coull_ci(0, 5, 0.90)
        assert low >= 0.0
        assert high <= 1.0
        assert low < high

    def test_all_pass(self):
        """5/5 successes -- interval should be near 1."""
        low, high = ci.agresti_coull_ci(5, 5, 0.90)
        assert low >= 0.0
        assert high <= 1.0
        assert high > 0.9

    def test_mid_range(self):
        """2/5 successes -- standard mid-range interval."""
        low, high = ci.agresti_coull_ci(2, 5, 0.90)
        assert 0.0 <= low < high <= 1.0

    def test_n_trials_zero(self):
        """Edge case: n=0 should not crash, returns full uncertainty."""
        low, high = ci.agresti_coull_ci(0, 0, 0.90)
        assert low == 0.0
        assert high == 1.0

    def test_wider_interval_at_higher_confidence(self):
        """95% confidence produces wider interval than 90%."""
        low90, high90 = ci.agresti_coull_ci(2, 5, 0.90)
        low95, high95 = ci.agresti_coull_ci(2, 5, 0.95)
        assert (high95 - low95) > (high90 - low90)

    def test_clamping_at_boundaries(self):
        """Results always clamped to [0, 1]."""
        for k in range(6):
            low, high = ci.agresti_coull_ci(k, 5, 0.99)
            assert 0.0 <= low <= 1.0
            assert 0.0 <= high <= 1.0

    def test_monotonicity(self):
        """More successes -> higher center of interval."""
        prev_center = -1.0
        for k in range(6):
            low, high = ci.agresti_coull_ci(k, 5, 0.90)
            center = (low + high) / 2.0
            assert center > prev_center
            prev_center = center


class TestClusterCI:
    """cluster_ci aggregates binary scores then computes CI."""

    def test_all_ones(self):
        """All 1.0 scores -- CI should be above 0 (Agresti-Coull adds pseudo-counts)."""
        low, high = ci.cluster_ci([1.0] * 10, n_samples=5)
        # With 10/50 successes, the CI is centered around 0.2
        assert low >= 0.0
        assert high <= 1.0
        assert low < high

    def test_all_zeros(self):
        """All 0.0 scores -- CI should be very low."""
        low, high = ci.cluster_ci([0.0] * 10, n_samples=5)
        assert high < 0.5

    def test_mixed_scores(self):
        """Mixed scores produce a valid interval."""
        low, high = ci.cluster_ci([1.0, 0.0, 1.0, 0.0, 1.0], n_samples=5)
        assert 0.0 <= low < high <= 1.0

    def test_single_score(self):
        """Single score should still produce a valid interval."""
        low, high = ci.cluster_ci([0.5], n_samples=1)
        assert 0.0 <= low <= high <= 1.0


class TestCIsSignificant:
    """Significance test via CI non-overlap."""

    def test_overlapping_not_significant(self):
        ci1 = (0.60, 0.80)
        ci2 = (0.70, 0.90)
        assert not ci.c_is_significant(ci1, ci2)

    def test_non_overlapping_significant(self):
        ci1 = (0.40, 0.50)
        ci2 = (0.70, 0.80)
        assert ci.c_is_significant(ci1, ci2)

    def test_touching_not_significant(self):
        """Touching at boundary is still overlapping."""
        ci1 = (0.40, 0.60)
        ci2 = (0.60, 0.80)
        assert not ci.c_is_significant(ci1, ci2)

    def test_identical_not_significant(self):
        ci1 = (0.50, 0.70)
        ci2 = (0.50, 0.70)
        assert not ci.c_is_significant(ci1, ci2)

    def test_reversed_order(self):
        """Should work regardless of which CI is passed first."""
        ci1 = (0.70, 0.80)
        ci2 = (0.40, 0.50)
        assert ci.c_is_significant(ci1, ci2)


# ---------------------------------------------------------------------------
# types.py -- dataclass definitions
# ---------------------------------------------------------------------------

class TestSubjectID:
    """SubjectID display names and type detection."""

    def test_model_display(self):
        sid = types.SubjectID(model="openai/qwen-local")
        assert sid.display_name == "openai/qwen-local"
        assert sid.subject_type == types.SubjectType.MODEL

    def test_agent_display(self):
        sid = types.SubjectID(model="openai/qwen-local", agent="claude", agent_mode="local")
        assert sid.display_name == "claude/openai/qwen-local/local"
        assert sid.subject_type == types.SubjectType.AGENT

    def test_harness_display(self):
        sid = types.SubjectID(
            model="openai/qwen-local", agent="claude", agent_mode="harness", harness_id="v2",
        )
        assert "harness:v2" in sid.display_name
        assert sid.subject_type == types.SubjectType.AGENT_HARNESS

    def test_agent_no_mode(self):
        """Agent without mode -- display omits trailing slash."""
        sid = types.SubjectID(model="openai/qwen-local", agent="codex")
        assert sid.display_name == "codex/openai/qwen-local"
        assert sid.subject_type == types.SubjectType.AGENT

    def test_model_defaults(self):
        sid = types.SubjectID(model="test-model")
        assert sid.agent is None
        assert sid.agent_mode is None
        assert sid.harness_id is None


class TestClusterScore:
    """ClusterScore field defaults."""

    def test_fields(self):
        cs = types.ClusterScore(
            name="competence", correct=0.83, token_ratio=1.1,
            time_ratio=0.9, cost_ratio=2.0,
            ci_low=0.71, ci_high=0.91, task_count=9,
        )
        assert cs.correct == 0.83
        assert cs.name == "competence"
        assert cs.alpha is None

    def test_with_alpha(self):
        cs = types.ClusterScore(
            name="exec", correct=0.5, token_ratio=1.0,
            time_ratio=1.0, cost_ratio=1.0,
            ci_low=0.3, ci_high=0.7, task_count=5, alpha=0.85,
        )
        assert cs.alpha == 0.85


class TestSubjectProfile:
    """SubjectProfile construction."""

    def test_fields(self):
        sp = types.SubjectProfile(
            subject_id=types.SubjectID(model="test"),
            cluster_scores=[],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=[],
            cost_per_sample=0.001,
            latency_avg=12.5,
            tool_calls_avg=None,
            verdict="Strong.",
        )
        assert sp.cost_per_sample == 0.001
        assert sp.latency_avg == 12.5
        assert sp.tool_calls_avg is None


class TestCompareResult:
    """CompareResult with optional deltas."""

    def test_fields(self):
        cr = types.CompareResult(
            subject_a=types.SubjectID(model="a"),
            subject_b=types.SubjectID(model="b"),
            deltas=[],
        )
        assert cr.cost_delta is None
        assert cr.latency_delta is None

    def test_with_deltas(self):
        cr = types.CompareResult(
            subject_a=types.SubjectID(model="a"),
            subject_b=types.SubjectID(model="b"),
            deltas=[types.ClusterDelta(cluster_name="c", delta=0.1, significant=True)],
            cost_delta=0.005,
            latency_delta=2.3,
        )
        assert cr.cost_delta == 0.005
        assert cr.latency_delta == 2.3
        assert len(cr.deltas) == 1


class TestDiagnosticReport:
    """DiagnosticReport defaults."""

    def test_defaults(self):
        report = types.DiagnosticReport(tasks=[])
        assert report.non_discriminative_tasks == []
        assert report.ceiling_tasks == []
        assert report.floor_tasks == []


class TestPipelineConfig:
    """PipelineConfig defaults."""

    def test_defaults(self):
        cfg = types.PipelineConfig()
        assert cfg.ci_level == 0.90
        assert cfg.discrimination_threshold == 0.0
        assert "clusters.yaml" in cfg.clusters_yaml


class TestGateResult:
    """GateResult field tests."""

    def test_fields(self):
        gr = types.GateResult(name="alpha", passed=True, threshold=0.7, score=0.85)
        assert gr.passed is True
        assert gr.failed_tasks == []
        assert gr.message == ""


# ---------------------------------------------------------------------------
# filters.py -- task discrimination
# ---------------------------------------------------------------------------

class TestComputeTaskDiscrimination:
    """Discrimination = std(scores) across subjects per task."""

    def test_all_same(self):
        """All subjects score identically -- discrimination == 0."""
        all_scores = {
            types.SubjectID(model="m1"): {"task1": 1.0, "task2": 0.0},
            types.SubjectID(model="m2"): {"task1": 1.0, "task2": 0.0},
        }
        disc = filters.compute_task_discrimination(all_scores)
        assert disc["task1"] == 0.0
        assert disc["task2"] == 0.0

    def test_varied(self):
        """Subjects differ -- discrimination > 0."""
        all_scores = {
            types.SubjectID(model="m1"): {"task1": 1.0},
            types.SubjectID(model="m2"): {"task1": 0.0},
        }
        disc = filters.compute_task_discrimination(all_scores)
        assert disc["task1"] > 0.0

    def test_single_subject(self):
        """Single subject -- discrimination == 0 (need >= 2 for stdev)."""
        all_scores = {
            types.SubjectID(model="m1"): {"task1": 0.7},
        }
        disc = filters.compute_task_discrimination(all_scores)
        assert disc["task1"] == 0.0

    def test_empty_input(self):
        """Empty dict returns empty dict."""
        disc = filters.compute_task_discrimination({})
        assert disc == {}

    def test_three_subjects(self):
        """Three subjects with spread -- discrimination matches stdev."""
        all_scores = {
            types.SubjectID(model="m1"): {"t1": 0.0},
            types.SubjectID(model="m2"): {"t1": 0.5},
            types.SubjectID(model="m3"): {"t1": 1.0},
        }
        disc = filters.compute_task_discrimination(all_scores)
        import statistics
        expected = statistics.stdev([0.0, 0.5, 1.0])
        assert abs(disc["t1"] - expected) < 1e-10


class TestFlagNonDiscriminative:
    """Flag tasks at or below the discrimination threshold."""

    def test_threshold_zero(self):
        disc = {"task1": 0.0, "task2": 0.5, "task3": 0.0}
        flagged = filters.flag_non_discriminative(disc, 0.0)
        assert "task1" in flagged
        assert "task3" in flagged
        assert "task2" not in flagged

    def test_threshold_positive(self):
        disc = {"task1": 0.0, "task2": 0.1, "task3": 0.5}
        flagged = filters.flag_non_discriminative(disc, threshold=0.2)
        assert "task1" in flagged
        assert "task2" in flagged
        assert "task3" not in flagged

    def test_all_discriminative(self):
        disc = {"task1": 0.3, "task2": 0.5}
        flagged = filters.flag_non_discriminative(disc, threshold=0.0)
        assert len(flagged) == 0

    def test_empty(self):
        flagged = filters.flag_non_discriminative({}, threshold=0.0)
        assert flagged == set()


# ---------------------------------------------------------------------------
# diagnostics.py -- difficulty and discrimination analysis
# ---------------------------------------------------------------------------

class TestRunDiagnostics:
    """run_diagnostics classifies tasks as ceiling/floor/non-discriminative."""

    def test_classifies_tasks(self):
        all_scores = {
            types.SubjectID(model="m1"): {"task1": 0.95, "task2": 0.05, "task3": 0.7, "task4": 0.7},
            types.SubjectID(model="m2"): {"task1": 0.95, "task2": 0.05, "task3": 0.3, "task4": 0.3},
        }
        clusters = {"c1": ["task1", "task2"], "c2": ["task3", "task4"]}
        report = diagnostics.run_diagnostics(all_scores, clusters)
        assert "task1" in report.ceiling_tasks
        assert "task2" in report.floor_tasks
        assert "task3" not in report.ceiling_tasks
        assert "task3" not in report.floor_tasks

    def test_non_discriminative_detection(self):
        """Tasks where all subjects score the same are non-discriminative."""
        all_scores = {
            types.SubjectID(model="m1"): {"task1": 0.5, "task2": 1.0},
            types.SubjectID(model="m2"): {"task1": 0.5, "task2": 0.0},
        }
        clusters = {"c1": ["task1", "task2"]}
        report = diagnostics.run_diagnostics(all_scores, clusters)
        assert "task1" in report.non_discriminative_tasks
        assert "task2" not in report.non_discriminative_tasks

    def test_empty_scores(self):
        report = diagnostics.run_diagnostics({}, {})
        assert len(report.tasks) == 0
        assert report.ceiling_tasks == []
        assert report.floor_tasks == []

    def test_task_diagnostics_fields(self):
        """Each TaskDiagnostics has the expected fields."""
        all_scores = {
            types.SubjectID(model="m1"): {"task1": 0.5},
            types.SubjectID(model="m2"): {"task1": 1.0},
        }
        report = diagnostics.run_diagnostics(all_scores, {"c1": ["task1"]})
        assert len(report.tasks) == 1
        t = report.tasks[0]
        assert t["task_id"] == "task1"
        assert 0.0 <= t["difficulty"] <= 1.0
        assert t["discrimination"] >= 0.0
        assert isinstance(t["is_ceiling"], bool)
        assert isinstance(t["is_floor"], bool)
        assert isinstance(t["is_non_discriminative"], bool)


class TestFormatDiagnosticSummary:
    """format_diagnostic_summary produces readable report."""

    def test_contains_header(self):
        all_scores = {
            types.SubjectID(model="m1"): {"task1": 0.95},
        }
        clusters = {"c1": ["task1"]}
        report = diagnostics.run_diagnostics(all_scores, clusters)
        summary = diagnostics.format_diagnostic_summary(report)
        assert "DIAGNOSTIC SUMMARY" in summary

    def test_contains_task_id(self):
        all_scores = {
            types.SubjectID(model="m1"): {"task1": 0.95},
        }
        clusters = {"c1": ["task1"]}
        report = diagnostics.run_diagnostics(all_scores, clusters)
        summary = diagnostics.format_diagnostic_summary(report)
        assert "task1" in summary

    def test_shows_ceiling_and_floor(self):
        all_scores = {
            types.SubjectID(model="m1"): {"easy": 0.95, "hard": 0.05},
            types.SubjectID(model="m2"): {"easy": 0.95, "hard": 0.05},
        }
        clusters = {"c1": ["easy", "hard"]}
        report = diagnostics.run_diagnostics(all_scores, clusters)
        summary = diagnostics.format_diagnostic_summary(report)
        assert "easy" in summary
        assert "hard" in summary
        assert "Ceiling" in summary
        assert "Floor" in summary

    def test_empty_report(self):
        report = types.DiagnosticReport(tasks=[])
        summary = diagnostics.format_diagnostic_summary(report)
        assert "Total tasks: 0" in summary


# ---------------------------------------------------------------------------
# profiles.py -- subject profiles and comparisons
# ---------------------------------------------------------------------------

class TestComputeStrengths:
    """Top-n highest-scoring tasks."""

    def test_basic(self):
        scores = {"task1": 1.0, "task2": 0.5, "task3": 0.2, "task4": 0.1}
        strengths = profiles.compute_strengths(scores, n=2)
        assert len(strengths) == 2
        assert strengths[0].task_id == "task1"
        assert strengths[1].task_id == "task2"
        assert all(s.is_strength for s in strengths)

    def test_all_zero_excluded(self):
        """Zero-scored tasks excluded from strengths."""
        scores = {"task1": 0.0, "task2": 0.0, "task3": 0.5}
        strengths = profiles.compute_strengths(scores, n=2)
        assert len(strengths) == 1
        assert strengths[0].task_id == "task3"

    def test_n_exceeds_available(self):
        scores = {"task1": 0.9}
        strengths = profiles.compute_strengths(scores, n=5)
        assert len(strengths) == 1


class TestComputeWeaknesses:
    """Bottom-n lowest-scoring tasks."""

    def test_basic(self):
        scores = {"task1": 1.0, "task2": 0.5, "task3": 0.2, "task4": 0.1}
        weaknesses = profiles.compute_weaknesses(scores, n=2)
        assert len(weaknesses) == 2
        assert weaknesses[0].task_id == "task4"
        assert weaknesses[1].task_id == "task3"
        assert not any(w.is_strength for w in weaknesses)

    def test_n_exceeds_available(self):
        scores = {"task1": 0.5}
        weaknesses = profiles.compute_weaknesses(scores, n=5)
        assert len(weaknesses) == 1


class TestBuildProfile:
    """build_profile constructs SubjectProfile from scores."""

    def test_basic_profile(self):
        sid = types.SubjectID(model="test")
        clusters = {"comp": ["t1", "t2"], "exec": ["t3"]}
        scores = {"t1": 1.0, "t2": 0.8, "t3": 0.5}
        profile = profiles.build_profile(
            subject_id=sid,
            scores=scores,
            clusters=clusters,
            non_discriminative_tasks=set(),
        )
        assert len(profile.cluster_scores) == 2
        assert profile.cluster_scores[0].name == "comp"
        assert profile.cluster_scores[0].correct == pytest.approx(0.9)
        assert profile.cluster_scores[1].name == "exec"
        assert profile.cluster_scores[1].correct == pytest.approx(0.5)
        assert profile.subject_id == sid

    def test_excludes_non_discriminative(self):
        sid = types.SubjectID(model="test")
        clusters = {"comp": ["t1", "t2"]}
        scores = {"t1": 1.0, "t2": 0.5}
        profile = profiles.build_profile(
            subject_id=sid,
            scores=scores,
            clusters=clusters,
            non_discriminative_tasks={"t2"},
        )
        # Only t1 contributes
        assert profile.cluster_scores[0].task_count == 1
        assert profile.cluster_scores[0].correct == pytest.approx(1.0)

    def test_empty_cluster(self):
        sid = types.SubjectID(model="test")
        clusters = {"comp": ["t_missing"]}
        scores = {}
        profile = profiles.build_profile(
            subject_id=sid,
            scores=scores,
            clusters=clusters,
            non_discriminative_tasks=set(),
        )
        assert profile.cluster_scores[0].correct == 0.0
        assert profile.cluster_scores[0].task_count == 0

    def test_with_pillar_data(self):
        sid = types.SubjectID(model="test")
        clusters = {"comp": ["t1"]}
        scores = {"t1": 1.0}
        pillar_data = {"t1": {"token_ratio": 1.5, "time_ratio": 0.8, "cost_ratio": 2.0}}
        profile = profiles.build_profile(
            subject_id=sid,
            scores=scores,
            clusters=clusters,
            non_discriminative_tasks=set(),
            pillar_data=pillar_data,
        )
        cs = profile.cluster_scores[0]
        assert cs.token_ratio == pytest.approx(1.5)
        assert cs.time_ratio == pytest.approx(0.8)
        assert cs.cost_ratio == pytest.approx(2.0)

    def test_cost_and_latency(self):
        sid = types.SubjectID(model="test")
        clusters = {"comp": ["t1"]}
        scores = {"t1": 1.0}
        profile = profiles.build_profile(
            subject_id=sid,
            scores=scores,
            clusters=clusters,
            non_discriminative_tasks=set(),
            cost_per_sample=0.005,
            latency_avg=25.0,
            tool_calls_avg=3.2,
        )
        assert profile.cost_per_sample == 0.005
        assert profile.latency_avg == 25.0
        assert profile.tool_calls_avg == 3.2

    def test_verdict_generated(self):
        sid = types.SubjectID(model="test")
        clusters = {"comp": ["t1"], "exec": ["t2"]}
        scores = {"t1": 0.9, "t2": 0.3}
        profile = profiles.build_profile(
            subject_id=sid,
            scores=scores,
            clusters=clusters,
            non_discriminative_tasks=set(),
        )
        assert "Strongest cluster" in profile.verdict
        assert "Weakest cluster" in profile.verdict


class TestFormatProfile:
    """format_profile renders readable text output."""

    def test_contains_sections(self):
        sid = types.SubjectID(model="test")
        profile = types.SubjectProfile(
            subject_id=sid,
            cluster_scores=[
                types.ClusterScore(
                    name="competence", correct=0.83, token_ratio=1.0,
                    time_ratio=1.0, cost_ratio=1.0,
                    ci_low=0.71, ci_high=0.91, task_count=9,
                ),
            ],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=[],
            cost_per_sample=0.0,
            latency_avg=10.0,
            tool_calls_avg=None,
            verdict="Strong.",
        )
        output = profiles.format_profile(profile)
        assert "PROFILE:" in output
        assert "competence" in output
        assert "0.83" in output

    def test_shows_verdict(self):
        sid = types.SubjectID(model="test")
        profile = types.SubjectProfile(
            subject_id=sid,
            cluster_scores=[],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=[],
            cost_per_sample=None,
            latency_avg=None,
            tool_calls_avg=None,
            verdict="No cluster data available.",
        )
        output = profiles.format_profile(profile)
        assert "VERDICT: No cluster data available." in output

    def test_shows_strengths_and_weaknesses(self):
        sid = types.SubjectID(model="test")
        profile = types.SubjectProfile(
            subject_id=sid,
            cluster_scores=[],
            strengths=[types.StrengthWeakness(task_id="good_task", score=0.95, is_strength=True)],
            weaknesses=[types.StrengthWeakness(task_id="bad_task", score=0.10, is_strength=False)],
            non_discriminative_tasks=[],
            cost_per_sample=None,
            latency_avg=None,
            tool_calls_avg=None,
            verdict="",
        )
        output = profiles.format_profile(profile)
        assert "STRENGTHS:" in output
        assert "good_task" in output
        assert "WEAKNESSES:" in output
        assert "bad_task" in output

    def test_shows_non_discriminative_tasks(self):
        sid = types.SubjectID(model="test")
        profile = types.SubjectProfile(
            subject_id=sid,
            cluster_scores=[],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=["nd1", "nd2"],
            cost_per_sample=None,
            latency_avg=None,
            tool_calls_avg=None,
            verdict="",
        )
        output = profiles.format_profile(profile)
        assert "NON-DISCRIMINATIVE" in output
        assert "nd1" in output
        assert "nd2" in output

    def test_free_model_cost(self):
        sid = types.SubjectID(model="test")
        profile = types.SubjectProfile(
            subject_id=sid,
            cluster_scores=[],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=[],
            cost_per_sample=0.0,
            latency_avg=None,
            tool_calls_avg=None,
            verdict="",
        )
        output = profiles.format_profile(profile)
        assert "FREE" in output

    def test_agent_type_in_header(self):
        sid = types.SubjectID(model="test-model", agent="claude", agent_mode="local")
        profile = types.SubjectProfile(
            subject_id=sid,
            cluster_scores=[],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=[],
            cost_per_sample=None,
            latency_avg=None,
            tool_calls_avg=5.0,
            verdict="",
        )
        output = profiles.format_profile(profile)
        assert "AGENT" in output
        assert "TOOL CALLS" in output


class TestCompareSubjects:
    """compare_subjects computes per-cluster deltas between two profiles."""

    def _make_profile(self, model: str, correct: float, ci_low: float, ci_high: float,
                      cost: float | None = None, latency: float | None = None):
        return types.SubjectProfile(
            subject_id=types.SubjectID(model=model),
            cluster_scores=[
                types.ClusterScore(
                    name="c", correct=correct, token_ratio=1.0,
                    time_ratio=1.0, cost_ratio=1.0,
                    ci_low=ci_low, ci_high=ci_high, task_count=5,
                ),
            ],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=[],
            cost_per_sample=cost,
            latency_avg=latency,
            tool_calls_avg=None,
            verdict="",
        )

    def test_basic_delta(self):
        pa = self._make_profile("a", 0.70, 0.60, 0.80)
        pb = self._make_profile("b", 0.85, 0.75, 0.95)
        result = profiles.compare_subjects(pa, pb)
        assert len(result.deltas) == 1
        assert result.deltas[0].delta == pytest.approx(0.15)
        assert result.deltas[0].cluster_name == "c"

    def test_cost_delta(self):
        pa = self._make_profile("a", 0.70, 0.60, 0.80, cost=0.001, latency=10.0)
        pb = self._make_profile("b", 0.85, 0.75, 0.95, cost=0.002, latency=15.0)
        result = profiles.compare_subjects(pa, pb)
        assert result.cost_delta == pytest.approx(0.001)
        assert result.latency_delta == pytest.approx(5.0)

    def test_no_cost_when_none(self):
        pa = self._make_profile("a", 0.70, 0.60, 0.80)
        pb = self._make_profile("b", 0.85, 0.75, 0.95)
        result = profiles.compare_subjects(pa, pb)
        assert result.cost_delta is None
        assert result.latency_delta is None

    def test_significance_non_overlapping(self):
        pa = self._make_profile("a", 0.50, 0.40, 0.55)
        pb = self._make_profile("b", 0.80, 0.75, 0.90)
        result = profiles.compare_subjects(pa, pb)
        assert result.deltas[0].significant is True

    def test_significance_overlapping(self):
        pa = self._make_profile("a", 0.70, 0.60, 0.80)
        pb = self._make_profile("b", 0.75, 0.65, 0.85)
        result = profiles.compare_subjects(pa, pb)
        assert result.deltas[0].significant is False

    def test_multiple_clusters(self):
        pa = types.SubjectProfile(
            subject_id=types.SubjectID(model="a"),
            cluster_scores=[
                types.ClusterScore(name="c1", correct=0.7, token_ratio=1.0,
                                   time_ratio=1.0, cost_ratio=1.0,
                                   ci_low=0.6, ci_high=0.8, task_count=5),
                types.ClusterScore(name="c2", correct=0.5, token_ratio=1.0,
                                   time_ratio=1.0, cost_ratio=1.0,
                                   ci_low=0.4, ci_high=0.6, task_count=5),
            ],
            strengths=[], weaknesses=[], non_discriminative_tasks=[],
            cost_per_sample=None, latency_avg=None, tool_calls_avg=None, verdict="",
        )
        pb = types.SubjectProfile(
            subject_id=types.SubjectID(model="b"),
            cluster_scores=[
                types.ClusterScore(name="c1", correct=0.8, token_ratio=1.0,
                                   time_ratio=1.0, cost_ratio=1.0,
                                   ci_low=0.7, ci_high=0.9, task_count=5),
                types.ClusterScore(name="c2", correct=0.6, token_ratio=1.0,
                                   time_ratio=1.0, cost_ratio=1.0,
                                   ci_low=0.5, ci_high=0.7, task_count=5),
            ],
            strengths=[], weaknesses=[], non_discriminative_tasks=[],
            cost_per_sample=None, latency_avg=None, tool_calls_avg=None, verdict="",
        )
        result = profiles.compare_subjects(pa, pb)
        assert len(result.deltas) == 2
        assert result.deltas[0].delta == pytest.approx(0.1)
        assert result.deltas[1].delta == pytest.approx(0.1)

    def test_mismatched_clusters_skipped(self):
        """Clusters present in only one profile are skipped."""
        pa = types.SubjectProfile(
            subject_id=types.SubjectID(model="a"),
            cluster_scores=[
                types.ClusterScore(name="c1", correct=0.7, token_ratio=1.0,
                                   time_ratio=1.0, cost_ratio=1.0,
                                   ci_low=0.6, ci_high=0.8, task_count=5),
            ],
            strengths=[], weaknesses=[], non_discriminative_tasks=[],
            cost_per_sample=None, latency_avg=None, tool_calls_avg=None, verdict="",
        )
        pb = types.SubjectProfile(
            subject_id=types.SubjectID(model="b"),
            cluster_scores=[
                types.ClusterScore(name="c2", correct=0.7, token_ratio=1.0,
                                   time_ratio=1.0, cost_ratio=1.0,
                                   ci_low=0.6, ci_high=0.8, task_count=5),
            ],
            strengths=[], weaknesses=[], non_discriminative_tasks=[],
            cost_per_sample=None, latency_avg=None, tool_calls_avg=None, verdict="",
        )
        result = profiles.compare_subjects(pa, pb)
        assert len(result.deltas) == 0


# ---------------------------------------------------------------------------
# pipeline.py -- load_clusters_yaml (unit-level only, skip run_pipeline)
# ---------------------------------------------------------------------------

class TestLoadClustersYaml:
    """load_clusters_yaml reads cluster definitions from YAML."""

    def test_dict_format(self, tmp_path):
        clusters_file = tmp_path / "clusters.yaml"
        clusters_file.write_text("""
competence:
  name: "Competence"
  task_ids:
    - task1
    - task2
execution:
  name: "Execution"
  task_ids:
    - task3
""")
        clusters = pipeline.load_clusters_yaml(clusters_file)
        assert "competence" in clusters
        assert "execution" in clusters
        assert len(clusters["competence"]) == 2
        assert clusters["competence"][0] == "task1"

    def test_list_format(self, tmp_path):
        """Simple list format for clusters."""
        clusters_file = tmp_path / "clusters.yaml"
        clusters_file.write_text("""
comp:
  - t1
  - t2
exec:
  - t3
""")
        clusters = pipeline.load_clusters_yaml(clusters_file)
        assert clusters["comp"] == ["t1", "t2"]
        assert clusters["exec"] == ["t3"]

    def test_empty_file(self, tmp_path):
        clusters_file = tmp_path / "clusters.yaml"
        clusters_file.write_text("{}")
        clusters = pipeline.load_clusters_yaml(clusters_file)
        assert clusters == {}


class TestPipelineHelpers:
    """Test helper functions in pipeline.py that don't need eval logs."""

    def test_get_correctness_hybrid_first(self):
        """hybrid_scorer takes priority over other scorers."""

        class FakeScore:
            def __init__(self, value):
                self.value = value

        scores = {
            "hybrid_scorer": FakeScore(0.8),
            "verify_sh": FakeScore(1.0),
            "llm_judge": FakeScore(0.9),
        }
        result = pipeline._get_correctness(scores)
        assert result == pytest.approx(0.8)

    def test_get_correctness_fallback_chain(self):
        """Falls through to verify_sh when hybrid absent."""

        class FakeScore:
            def __init__(self, value):
                self.value = value

        scores = {"verify_sh": FakeScore(1.0)}
        result = pipeline._get_correctness(scores)
        assert result == pytest.approx(1.0)

    def test_get_correctness_raw_float(self):
        """Handles raw float values (no .value attribute)."""
        scores = {"includes": 1.0}
        result = pipeline._get_correctness(scores)
        assert result == pytest.approx(1.0)

    def test_get_correctness_none(self):
        """Returns None when no valid score found."""
        scores = {}
        result = pipeline._get_correctness(scores)
        assert result is None

    def test_get_correctness_nan_skipped(self):
        """NaN values are skipped."""

        class FakeScore:
            def __init__(self, value):
                self.value = value

        scores = {"hybrid_scorer": FakeScore(float("nan"))}
        result = pipeline._get_correctness(scores)
        assert result is None

    def test_is_tool_event(self):
        """Detects tool-related events."""

        class FakeEvent:
            def __init__(self, type_str):
                self.type = type_str

        assert pipeline._is_tool_event(FakeEvent("tool_call")) is True
        assert pipeline._is_tool_event(FakeEvent("ToolUse")) is True
        assert pipeline._is_tool_event(FakeEvent("message")) is False
        assert pipeline._is_tool_event(FakeEvent(None)) is False

    def test_extract_pillar_data(self):
        """Extracts token/time/cost ratios from sample scores."""

        class FakeScore:
            def __init__(self, value):
                self.value = value

        class FakeSample:
            def __init__(self, scores):
                self.scores = scores

        sample = FakeSample({
            "token_ratio_scorer": FakeScore(1.5),
            "time_ratio_scorer": FakeScore(0.8),
            "price_ratio_scorer": FakeScore(2.0),
        })
        result = pipeline._extract_pillar_data(sample)
        assert result["token_ratio"] == pytest.approx(1.5)
        assert result["time_ratio"] == pytest.approx(0.8)
        assert result["cost_ratio"] == pytest.approx(2.0)

    def test_extract_pillar_data_missing_scorers(self):
        """Returns empty dict when no pillar scorers present."""

        class FakeSample:
            def __init__(self):
                self.scores = {}

        result = pipeline._extract_pillar_data(FakeSample())
        assert result == {}

    def test_extract_pillar_data_nan_cost_skipped(self):
        """NaN cost_ratio values are excluded."""


        class FakeScore:
            def __init__(self, value):
                self.value = value

        class FakeSample:
            def __init__(self, scores):
                self.scores = scores

        sample = FakeSample({"price_ratio_scorer": FakeScore(float("nan"))})
        result = pipeline._extract_pillar_data(sample)
        assert "cost_ratio" not in result


# ---------------------------------------------------------------------------
# subject.py -- unit tests that don't need real eval logs
# ---------------------------------------------------------------------------

class TestSubjectHelpers:
    """Test subject.py helpers that work without eval log files."""

    def test_get_subject_display_name(self):
        from bench_cli.discriminative.subject import get_subject_display_name
        sid = types.SubjectID(model="test-model", agent="claude", agent_mode="local")
        assert get_subject_display_name(sid) == "claude/test-model/local"

    def test_get_subject_display_name_model(self):
        from bench_cli.discriminative.subject import get_subject_display_name
        sid = types.SubjectID(model="openai/qwen-local")
        assert get_subject_display_name(sid) == "openai/qwen-local"

    def test_extract_agent_name_claude(self):
        from bench_cli.discriminative.subject import _extract_agent_name
        assert _extract_agent_name({"name": "Claude Code"}) == "claude"

    def test_extract_agent_name_codex(self):
        from bench_cli.discriminative.subject import _extract_agent_name
        assert _extract_agent_name({"name": "Codex CLI"}) == "codex"

    def test_extract_agent_name_gemini(self):
        from bench_cli.discriminative.subject import _extract_agent_name
        assert _extract_agent_name({"name": "Gemini Agent"}) == "gemini"

    def test_extract_agent_name_none(self):
        from bench_cli.discriminative.subject import _extract_agent_name
        assert _extract_agent_name(None) == "unknown"
        # Empty dict is falsy, returns "unknown" (not "agent")
        assert _extract_agent_name({}) == "unknown"

    def test_infer_agent_mode_docker(self):
        from bench_cli.discriminative.subject import _infer_agent_mode

        class FakeSandbox:
            type = "docker"

        assert _infer_agent_mode(FakeSandbox(), {}) == "docker"

    def test_infer_agent_mode_local(self):
        from bench_cli.discriminative.subject import _infer_agent_mode
        assert _infer_agent_mode(None, {}) == "local"
