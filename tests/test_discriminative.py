"""Tests for bench_cli.discriminative -- types, ci, filters, diagnostics, profiles, pipeline."""

from __future__ import annotations

import pytest

from bench_cli.discriminative import ci, diagnostics, filters, pipeline, profiles, types
from bench_cli.discriminative.types import ClusterScore, SubjectID, SubjectProfile

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
            model="openai/qwen-local",
            agent="claude",
            agent_mode="harness",
            harness_id="v2",
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
            name="competence",
            correct=0.83,
            token_ratio=1.1,
            time_ratio=0.9,
            cost_ratio=2.0,
            ci_low=0.71,
            ci_high=0.91,
            task_count=9,
        )
        assert cs.correct == 0.83
        assert cs.name == "competence"
        assert cs.alpha is None

    def test_with_alpha(self):
        cs = types.ClusterScore(
            name="exec",
            correct=0.5,
            token_ratio=1.0,
            time_ratio=1.0,
            cost_ratio=1.0,
            ci_low=0.3,
            ci_high=0.7,
            task_count=5,
            alpha=0.85,
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
        pillar_data = {"t1": {"token_ratio": [1.5], "time_ratio": [0.8], "cost_ratio": [2.0]}}
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
                    name="competence",
                    correct=0.83,
                    token_ratio=1.0,
                    time_ratio=1.0,
                    cost_ratio=1.0,
                    ci_low=0.71,
                    ci_high=0.91,
                    task_count=9,
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

    def _make_profile(
        self,
        model: str,
        correct: float,
        ci_low: float,
        ci_high: float,
        cost: float | None = None,
        latency: float | None = None,
    ):
        return types.SubjectProfile(
            subject_id=types.SubjectID(model=model),
            cluster_scores=[
                types.ClusterScore(
                    name="c",
                    correct=correct,
                    token_ratio=1.0,
                    time_ratio=1.0,
                    cost_ratio=1.0,
                    ci_low=ci_low,
                    ci_high=ci_high,
                    task_count=5,
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
                types.ClusterScore(
                    name="c1",
                    correct=0.7,
                    token_ratio=1.0,
                    time_ratio=1.0,
                    cost_ratio=1.0,
                    ci_low=0.6,
                    ci_high=0.8,
                    task_count=5,
                ),
                types.ClusterScore(
                    name="c2",
                    correct=0.5,
                    token_ratio=1.0,
                    time_ratio=1.0,
                    cost_ratio=1.0,
                    ci_low=0.4,
                    ci_high=0.6,
                    task_count=5,
                ),
            ],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=[],
            cost_per_sample=None,
            latency_avg=None,
            tool_calls_avg=None,
            verdict="",
        )
        pb = types.SubjectProfile(
            subject_id=types.SubjectID(model="b"),
            cluster_scores=[
                types.ClusterScore(
                    name="c1",
                    correct=0.8,
                    token_ratio=1.0,
                    time_ratio=1.0,
                    cost_ratio=1.0,
                    ci_low=0.7,
                    ci_high=0.9,
                    task_count=5,
                ),
                types.ClusterScore(
                    name="c2",
                    correct=0.6,
                    token_ratio=1.0,
                    time_ratio=1.0,
                    cost_ratio=1.0,
                    ci_low=0.5,
                    ci_high=0.7,
                    task_count=5,
                ),
            ],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=[],
            cost_per_sample=None,
            latency_avg=None,
            tool_calls_avg=None,
            verdict="",
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
                types.ClusterScore(
                    name="c1",
                    correct=0.7,
                    token_ratio=1.0,
                    time_ratio=1.0,
                    cost_ratio=1.0,
                    ci_low=0.6,
                    ci_high=0.8,
                    task_count=5,
                ),
            ],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=[],
            cost_per_sample=None,
            latency_avg=None,
            tool_calls_avg=None,
            verdict="",
        )
        pb = types.SubjectProfile(
            subject_id=types.SubjectID(model="b"),
            cluster_scores=[
                types.ClusterScore(
                    name="c2",
                    correct=0.7,
                    token_ratio=1.0,
                    time_ratio=1.0,
                    cost_ratio=1.0,
                    ci_low=0.6,
                    ci_high=0.8,
                    task_count=5,
                ),
            ],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=[],
            cost_per_sample=None,
            latency_avg=None,
            tool_calls_avg=None,
            verdict="",
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
        clusters, _warnings = pipeline.load_clusters_yaml(clusters_file)
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
        clusters, _warnings = pipeline.load_clusters_yaml(clusters_file)
        assert clusters["comp"] == ["t1", "t2"]
        assert clusters["exec"] == ["t3"]

    def test_empty_file(self, tmp_path):
        clusters_file = tmp_path / "clusters.yaml"
        clusters_file.write_text("{}")
        clusters, _warnings = pipeline.load_clusters_yaml(clusters_file)
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

        sample = FakeSample(
            {
                "token_ratio_scorer": FakeScore(1.5),
                "time_ratio_scorer": FakeScore(0.8),
                "price_ratio_scorer": FakeScore(2.0),
            }
        )
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


# ---------------------------------------------------------------------------
# gates.py -- non-compensatory safety gates
# ---------------------------------------------------------------------------


class TestCorrectnessGate:
    """correctness_gate: all clusters must exceed threshold."""

    def test_pass_when_all_above_threshold(self):
        from bench_cli.discriminative.gates import correctness_gate

        profile = _make_profile(correctness=[0.8, 0.7, 0.7, 0.7])
        result = correctness_gate(profile, threshold=0.60)
        assert result.passed is True
        assert result.score >= 0.60

    def test_fail_when_below_threshold(self):
        from bench_cli.discriminative.gates import correctness_gate

        profile = _make_profile(correctness=[0.8, 0.5, 0.5, 0.5])
        result = correctness_gate(profile, threshold=0.60)
        assert result.passed is False
        assert len(result.failed_tasks) > 0

    def test_strict_vs_warning_message(self):
        from bench_cli.discriminative.gates import correctness_gate

        profile = _make_profile(correctness=[0.8, 0.4, 0.4, 0.4])
        strict_result = correctness_gate(profile, threshold=0.60, strict=True)
        warn_result = correctness_gate(profile, threshold=0.60, strict=False)
        assert "FAILED" in strict_result.message or "FAIL" in strict_result.message
        assert "WARNING" in warn_result.message


class TestCoverageGate:
    """coverage_gate: all clusters must have data."""

    def test_pass_when_all_clusters_have_data(self):
        from bench_cli.discriminative.gates import coverage_gate

        profile = _make_profile(correctness=[0.8, 0.7, 0.7, 0.7])
        result = coverage_gate(profile, threshold=0.80)
        assert result.passed is True

    def test_fail_when_no_data(self):
        from bench_cli.discriminative.gates import coverage_gate
        from bench_cli.discriminative.types import ClusterScore, SubjectProfile

        profile = SubjectProfile(
            subject_id=types.SubjectID(model="test"),
            cluster_scores=[
                ClusterScore(
                    name="competence",
                    correct=0.0,
                    token_ratio=0.0,
                    time_ratio=0.0,
                    cost_ratio=0.0,
                    ci_low=0.0,
                    ci_high=0.0,
                    task_count=0,
                ),
                ClusterScore(
                    name="execution",
                    correct=0.0,
                    token_ratio=0.0,
                    time_ratio=0.0,
                    cost_ratio=0.0,
                    ci_low=0.0,
                    ci_high=0.0,
                    task_count=0,
                ),
                ClusterScore(
                    name="analysis",
                    correct=0.0,
                    token_ratio=0.0,
                    time_ratio=0.0,
                    cost_ratio=0.0,
                    ci_low=0.0,
                    ci_high=0.0,
                    task_count=0,
                ),
                ClusterScore(
                    name="universal",
                    correct=0.0,
                    token_ratio=0.0,
                    time_ratio=0.0,
                    cost_ratio=0.0,
                    ci_low=0.0,
                    ci_high=0.0,
                    task_count=0,
                ),
            ],
            strengths=[],
            weaknesses=[],
            non_discriminative_tasks=[],
            cost_per_sample=None,
            latency_avg=None,
            tool_calls_avg=None,
            verdict="",
            gate_results=[],
        )
        result = coverage_gate(profile, threshold=0.80)
        assert result.passed is False


class TestRunGates:
    """run_gates applies all gates to a profile."""

    def test_run_default_gates(self):
        from bench_cli.discriminative.gates import run_gates

        profile = _make_profile(correctness=[0.8, 0.7, 0.7, 0.7])
        results = run_gates(profile)
        assert len(results) == 2  # correctness_gate + coverage_gate
        names = {r.name for r in results}
        assert "correctness_gate" in names
        assert "coverage_gate" in names


class TestFormatGateResults:
    """format_gate_results renders gate results."""

    def test_pass_format(self):
        from bench_cli.discriminative.gates import format_gate_results
        from bench_cli.discriminative.types import GateResult

        results = [GateResult(name="correctness_gate", passed=True, threshold=0.60, score=0.75)]
        output = format_gate_results(results)
        assert "PASS" in output
        assert "correctness_gate" in output

    def test_fail_format(self):
        from bench_cli.discriminative.gates import format_gate_results
        from bench_cli.discriminative.types import GateResult

        results = [GateResult(name="correctness_gate", passed=False, threshold=0.60, score=0.40)]
        output = format_gate_results(results)
        assert "FAIL" in output


# ---------------------------------------------------------------------------
# pareto.py -- Pareto frontier computation
# ---------------------------------------------------------------------------


class TestComputeQuality:
    """compute_quality: geometric mean of cluster correctness scores."""

    def test_perfect_scores(self):
        from bench_cli.discriminative.pareto import compute_quality

        profile = _make_profile(correctness=[1.0, 1.0, 1.0, 1.0])
        assert abs(compute_quality(profile) - 1.0) < 1e-9

    def test_zero_cluster_drops_quality(self):
        from bench_cli.discriminative.pareto import compute_quality

        profile = _make_profile(correctness=[1.0, 0.0, 1.0, 1.0])
        # Geometric mean of [1, 0, 1, 1] = 0, product is 0
        assert compute_quality(profile) == 0.0

    def test_all_zero(self):
        from bench_cli.discriminative.pareto import compute_quality

        profile = _make_profile(correctness=[0.0, 0.0, 0.0, 0.0])
        assert compute_quality(profile) == 0.0

    def test_mixed_scores(self):
        from bench_cli.discriminative.pareto import compute_quality

        profile = _make_profile(correctness=[0.8, 0.6, 0.6, 0.6])
        q = compute_quality(profile)
        assert 0.0 < q < 1.0


class TestParetoFrontier:
    """compute_pareto_frontier marks undominated subjects."""

    def test_free_model_not_dominated_by_paid(self):
        from bench_cli.discriminative.pareto import compute_pareto_frontier

        free_profile = _make_profile(correctness=[0.8, 0.8, 0.8, 0.8], cost=0.0)
        paid_profile = _make_profile(correctness=[0.9, 0.9, 0.9, 0.9], cost=0.01)

        points = compute_pareto_frontier([free_profile, paid_profile])
        free_pt = next(p for p in points if p.is_free)
        paid_pt = next(p for p in points if not p.is_free)
        # Free is undominated in its free tier, paid is undominated in paid tier
        assert (
            free_pt.dominated is False
        )  # free models don't dominate each other if quality is lower
        assert paid_pt.dominated is False  # paid model is best on quality in paid tier

    def test_best_quality_is_undominated(self):
        from bench_cli.discriminative.pareto import compute_pareto_frontier

        low = _make_profile(correctness=[0.5, 0.5, 0.5, 0.5], cost=0.01)
        high = _make_profile(correctness=[0.9, 0.9, 0.9, 0.9], cost=0.01)

        points = compute_pareto_frontier([low, high])
        high_pt = next(p for p in points if p.quality > 0.8)
        assert high_pt.dominated is False

    def test_format_pareto(self):
        from bench_cli.discriminative.pareto import compute_pareto_frontier, format_pareto_frontier

        p1 = _make_profile(correctness=[0.9, 0.9, 0.9, 0.9], cost=0.01)
        p2 = _make_profile(correctness=[0.5, 0.5, 0.5, 0.5], cost=0.005)
        points = compute_pareto_frontier([p1, p2])
        output = format_pareto_frontier(points)
        assert "PARETO" in output
        assert "UNDOMINATED" in output or "undominated" in output.lower()


class TestCronbachAlpha:
    """cronbach_alpha: cluster coherence validation."""

    def test_good_alpha(self):
        # Items (tasks) with similar scores across subjects → high alpha
        # 3 tasks, 5 "subjects" (sample runs)
        from bench_cli.discriminative.profiles import cronbach_alpha

        item_scores = [
            [0.90, 0.95, 0.88, 0.92, 0.90],
            [0.79, 0.85, 0.78, 0.82, 0.80],
            [0.95, 0.99, 0.93, 0.97, 0.95],
        ]
        alpha = cronbach_alpha(item_scores)
        assert alpha is not None
        assert alpha > 0.5  # tasks cohere

    def test_low_alpha(self):
        # Items with very different patterns → low alpha
        from bench_cli.discriminative.profiles import cronbach_alpha

        item_scores = [
            [1.0, 0.0, 1.0, 0.0, 1.0],
            [0.0, 1.0, 0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0, 0.0, 1.0],
        ]
        alpha = cronbach_alpha(item_scores)
        assert alpha is not None
        assert alpha < 0.5

    def test_too_few_items(self):
        from bench_cli.discriminative.profiles import cronbach_alpha

        alpha = cronbach_alpha([[1.0, 0.0]])
        assert alpha is None  # need ≥2 items

    def test_too_few_subjects(self):
        from bench_cli.discriminative.profiles import cronbach_alpha

        item_scores = [[1.0], [0.0]]  # only 1 subject
        alpha = cronbach_alpha(item_scores)
        assert alpha is None


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_profile(correctness: list[float], cost: float | None = None) -> types.SubjectProfile:
    """Create a SubjectProfile with given per-cluster correctness scores."""
    from bench_cli.discriminative.types import ClusterScore, SubjectProfile

    cluster_names = ["competence", "execution", "analysis", "universal"]
    cluster_scores = []
    for i, name in enumerate(cluster_names):
        score = correctness[i] if i < len(correctness) else 0.8
        cluster_scores.append(
            ClusterScore(
                name=name,
                correct=score,
                token_ratio=1.0,
                time_ratio=1.0,
                cost_ratio=1.0,
                ci_low=0.0,
                ci_high=1.0,
                task_count=5,
            )
        )
    return SubjectProfile(
        subject_id=types.SubjectID(model="test-model"),
        cluster_scores=cluster_scores,
        strengths=[],
        weaknesses=[],
        non_discriminative_tasks=[],
        cost_per_sample=cost,
        latency_avg=10.0,
        tool_calls_avg=None,
        verdict="Test profile",
        gate_results=[],
    )


# ---------------------------------------------------------------------------
# Phase 3: matrix.py -- compare_matrix
# ---------------------------------------------------------------------------


class TestCompareMatrix:
    """compare_matrix builds comparison matrix from 2+ profiles."""

    def test_two_subjects_one_row_per_cluster(self):
        from bench_cli.discriminative.matrix import compare_matrix
        from bench_cli.discriminative.types import SubjectID

        sid_a = SubjectID(model="openai/model-a")
        sid_b = SubjectID(model="openai/model-b")

        profile_a = _make_profile_with_clusters(
            sid_a,
            {
                "competence": (0.80, 0.70, 0.90),
                "execution": (0.70, 0.60, 0.80),
            },
        )
        profile_b = _make_profile_with_clusters(
            sid_b,
            {
                "competence": (0.90, 0.82, 0.96),
                "execution": (0.60, 0.50, 0.70),
            },
        )

        matrix = compare_matrix([profile_a, profile_b])
        assert len(matrix.rows) == 2  # one row per cluster
        row_names = {r.cluster_name for r in matrix.rows}
        assert "competence" in row_names
        assert "execution" in row_names

    def test_three_subjects_scores_in_matrix(self):
        from bench_cli.discriminative.matrix import compare_matrix

        sid_a = SubjectID(model="openai/model-a")
        sid_b = SubjectID(model="openai/model-b")
        sid_c = SubjectID(model="openai/model-c")

        profile_a = _make_profile_with_clusters(sid_a, {"competence": (0.80, 0.7, 0.9)})
        profile_b = _make_profile_with_clusters(sid_b, {"competence": (0.90, 0.8, 1.0)})
        profile_c = _make_profile_with_clusters(sid_c, {"competence": (0.60, 0.5, 0.7)})

        matrix = compare_matrix([profile_a, profile_b, profile_c])
        assert len(matrix.subjects) == 3

        row = matrix.rows[0]
        assert row.scores["openai/model-a"] == 0.80
        assert row.scores["openai/model-b"] == 0.90
        assert row.scores["openai/model-c"] == 0.60

        # Deltas relative to reference (first subject)
        assert row.deltas["openai/model-a"] == 0.0
        assert row.deltas["openai/model-b"] == pytest.approx(0.10, abs=0.01)
        assert row.deltas["openai/model-c"] == pytest.approx(-0.20, abs=0.01)

    def test_empty_profiles_returns_empty_matrix(self):
        from bench_cli.discriminative.matrix import compare_matrix

        matrix = compare_matrix([])
        assert matrix.rows == []
        assert matrix.subjects == []


# ---------------------------------------------------------------------------
# Phase 3: pipeline -- load_clusters_yaml with custom merging
# ---------------------------------------------------------------------------


class TestLoadClustersYamlCustom:
    """load_clusters_yaml merges custom cluster definitions."""

    def test_custom_clusters_override_base(self, tmp_path):
        base_file = tmp_path / "clusters.yaml"
        base_file.write_text("""
competence:
  name: "Competence"
  task_ids:
    - task1
    - task2
""")
        custom_file = tmp_path / "custom.yaml"
        custom_file.write_text("""
competence:
  name: "Custom Competence"
  description: "My custom cluster"
  task_ids:
    - task3
    - task4
""")
        clusters, warnings = pipeline.load_clusters_yaml(base_file, custom_yaml=custom_file)
        assert "competence" in clusters
        # Custom overrides base
        assert clusters["competence"] == ["task3", "task4"]
        assert any("overrides" in w for w in warnings)

    def test_custom_clusters_add_new_cluster(self, tmp_path):
        base_file = tmp_path / "clusters.yaml"
        base_file.write_text("""
competence:
  name: "Competence"
  task_ids:
    - task1
""")
        custom_file = tmp_path / "custom.yaml"
        custom_file.write_text("""
my-custom:
  name: "My Custom"
  description: "A custom cluster"
  task_ids:
    - task2
    - task3
""")
        clusters, warnings = pipeline.load_clusters_yaml(base_file, custom_yaml=custom_file)
        assert "my-custom" in clusters
        assert clusters["my-custom"] == ["task2", "task3"]

    def test_unknown_task_ids_produce_warning(self, tmp_path):
        base_file = tmp_path / "clusters.yaml"
        base_file.write_text("competence:\n  name: 'C'\n  task_ids: ['task1']")
        custom_file = tmp_path / "custom.yaml"
        custom_file.write_text("""
my-cluster:
  name: "MC"
  task_ids:
    - unknown_task_xyz
""")
        known = {"task1"}
        clusters, warnings = pipeline.load_clusters_yaml(
            base_file, custom_yaml=custom_file, known_tasks=known
        )
        assert "my-cluster" in clusters
        assert any("unknown_task_xyz" in w for w in warnings)
        # Custom cluster still loads despite unknown task
        assert clusters["my-cluster"] == ["unknown_task_xyz"]


# ---------------------------------------------------------------------------
# Phase 3: correlation.py -- compute_task_correlation
# ---------------------------------------------------------------------------


class TestComputeTaskCorrelation:
    """compute_task_correlation finds task pairs with Pearson r >= 0.5."""

    def test_correlated_tasks_detected(self):
        from bench_cli.discriminative.correlation import compute_task_correlation

        # model-a and model-b both score high on task1, low on task2
        # -> task1 and task2 are negatively correlated
        all_scores = {
            "model-a": {"task1": 1.0, "task2": 0.0, "task3": 0.5},
            "model-b": {"task1": 1.0, "task2": 0.0, "task3": 0.5},
            "model-c": {"task1": 0.0, "task2": 1.0, "task3": 0.5},
            "model-d": {"task1": 0.0, "task2": 1.0, "task3": 0.5},
        }
        correlations = compute_task_correlation(all_scores)

        # task1 and task2 are perfectly negatively correlated
        task1_task2 = next(
            (c for c in correlations if {c.task_a, c.task_b} == {"task1", "task2"}),
            None,
        )
        assert task1_task2 is not None
        assert abs(task1_task2.pearson_r) == 1.0

    def test_uncorrelated_tasks_not_returned(self):
        from bench_cli.discriminative.correlation import compute_task_correlation

        all_scores = {
            "model-a": {"task1": 0.5, "task2": 0.5, "task3": 0.5},
            "model-b": {"task1": 0.5, "task2": 0.5, "task3": 0.5},
            "model-c": {"task1": 0.5, "task2": 0.5, "task3": 0.5},
        }
        correlations = compute_task_correlation(all_scores)
        assert len(correlations) == 0

    def test_less_than_3_tasks_returns_empty(self):
        from bench_cli.discriminative.correlation import compute_task_correlation

        all_scores = {
            "model-a": {"task1": 0.5, "task2": 0.5},
            "model-b": {"task1": 0.5, "task2": 0.5},
        }
        correlations = compute_task_correlation(all_scores)
        assert correlations == []

    def test_fewer_than_2_subjects_returns_empty(self):
        from bench_cli.discriminative.correlation import compute_task_correlation

        all_scores = {
            "model-a": {"task1": 1.0, "task2": 0.0},
        }
        correlations = compute_task_correlation(all_scores)
        assert correlations == []


# ---------------------------------------------------------------------------
# Phase 3: harness.py -- harness_change_report
# ---------------------------------------------------------------------------


class TestHarnessChangeReport:
    """harness_change_report builds delta report from before/after profiles."""

    def test_significant_improvement_detected(self):
        from bench_cli.discriminative.harness import harness_change_report

        sid = SubjectID(model="openai/qwen-local", agent="claude", agent_mode="harness")
        before = _make_profile_with_clusters(
            sid,
            {
                "competence": (0.60, 0.50, 0.70),
                "execution": (0.50, 0.40, 0.60),
            },
        )
        after = _make_profile_with_clusters(
            sid,
            {
                "competence": (0.90, 0.82, 0.96),
                "execution": (0.70, 0.60, 0.80),
            },
        )

        report = harness_change_report(before, after)
        assert report.subject_id == sid
        assert len(report.cluster_deltas) == 2

        # Competence delta should be +0.30 (significant)
        comp_delta = next(d for d in report.cluster_deltas if d.cluster_name == "competence")
        assert comp_delta.correctness_delta == pytest.approx(0.30, abs=0.01)
        assert comp_delta.correctness_significant is True

    def test_non_significant_delta_detected(self):
        from bench_cli.discriminative.harness import harness_change_report

        sid = SubjectID(model="openai/qwen-local")
        before = _make_profile_with_clusters(sid, {"competence": (0.80, 0.70, 0.90)})
        after = _make_profile_with_clusters(sid, {"competence": (0.82, 0.72, 0.92)})

        report = harness_change_report(before, after)
        comp_delta = next(d for d in report.cluster_deltas if d.cluster_name == "competence")
        assert comp_delta.correctness_significant is False

    def test_subject_id_mismatch_raises(self):
        from bench_cli.discriminative.harness import harness_change_report

        sid_a = SubjectID(model="openai/model-a")
        sid_b = SubjectID(model="openai/model-b")
        before = _make_profile_with_clusters(sid_a, {"competence": (0.80, 0.7, 0.9)})
        after = _make_profile_with_clusters(sid_b, {"competence": (0.90, 0.8, 1.0)})

        with pytest.raises(ValueError, match="SubjectID mismatch"):
            harness_change_report(before, after)

    def test_format_harness_report_includes_grid(self):
        from bench_cli.discriminative.harness import format_harness_report, harness_change_report

        sid = SubjectID(model="openai/qwen-local")
        before = _make_profile_with_clusters(sid, {"competence": (0.80, 0.7, 0.9)})
        after = _make_profile_with_clusters(sid, {"competence": (0.90, 0.8, 1.0)})

        report = harness_change_report(before, after)
        output = format_harness_report(report)

        assert "HARNESS CHANGE REPORT" in output
        assert "CLUSTER × PILLAR DELTAS" in output  # noqa: RUF001
        assert "(n.s.)" in output or "(*)" in output


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_profile_with_clusters(sid, cluster_data):
    """Create a SubjectProfile with specific per-cluster correctness."""
    cluster_scores = []
    for name, (correct, ci_low, ci_high) in cluster_data.items():
        cluster_scores.append(
            ClusterScore(
                name=name,
                correct=correct,
                token_ratio=1.0,
                time_ratio=1.0,
                cost_ratio=1.0,
                ci_low=ci_low,
                ci_high=ci_high,
                task_count=5,
            )
        )
    return SubjectProfile(
        subject_id=sid,
        cluster_scores=cluster_scores,
        strengths=[],
        weaknesses=[],
        non_discriminative_tasks=[],
        cost_per_sample=0.001,
        latency_avg=10.0,
        tool_calls_avg=None,
        verdict="Test",
        gate_results=[],
    )


# ---------------------------------------------------------------------------
# Phase 3: MultiSubjectReport -- type and pipeline
# ---------------------------------------------------------------------------


class TestMultiSubjectReport:
    """MultiSubjectReport type and run_multi_pipeline."""

    def test_multi_subject_report_type(self):
        from bench_cli.discriminative.phase3_types import MultiSubjectReport

        report = MultiSubjectReport(profiles=[], diagnostic_report=types.DiagnosticReport(tasks=[]))
        assert report.profiles == []
        assert len(report.diagnostic_report.tasks) == 0

    def test_run_multi_pipeline_accepts_list_of_subject_ids(self):
        # run_multi_pipeline exists and accepts list[SubjectID]
        import inspect

        from bench_cli.discriminative.pipeline import run_multi_pipeline

        sig = inspect.signature(run_multi_pipeline)
        params = list(sig.parameters.keys())
        assert "subject_ids" in params
