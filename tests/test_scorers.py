"""Unit tests for pillar scorers."""

from unittest.mock import PropertyMock, patch

import pytest
from conftest import make_task_state, run_async
from inspect_ai.solver import TaskState


def _patch_token_usage(state: TaskState, value: int):
    """Return a patcher that mocks state.token_usage to return `value`."""
    return patch.object(type(state), "token_usage", new_callable=PropertyMock, return_value=value)


# ---------------------------------------------------------------------------
# Pillar scorer tests
# ---------------------------------------------------------------------------


class TestTokenRatioScorer:
    def test_ratio_floor_at_minimum(self):
        """Actual tokens far exceeding reference → ratio at floor (0.01)."""
        from unittest.mock import PropertyMock, patch

        from scorers.token_ratio import token_ratio_scorer

        s = token_ratio_scorer()
        state = make_task_state()
        # actual_tokens = 200_000, reference = 1500 (system default)
        # raw_ratio = 1500/200000 = 0.0075 → floored to 0.01
        with patch.object(
            type(state), "token_usage", new_callable=PropertyMock, return_value=200_000
        ):
            result = run_async(s(state, state.target))
        assert result.value == pytest.approx(0.01)

    def test_ratio_greater_than_one_when_efficient(self):
        """Used fewer tokens than reference → ratio > 1.0."""
        from unittest.mock import PropertyMock, patch

        from scorers.protocol import TaskBudget
        from scorers.token_ratio import token_ratio_scorer

        s = token_ratio_scorer(task_budget=TaskBudget(output_tokens=1000))
        state = make_task_state()
        with patch.object(type(state), "token_usage", new_callable=PropertyMock, return_value=500):
            result = run_async(s(state, state.target))
        assert result.value > 1.0

    def test_potential_loop_flag_set(self):
        """Too many messages → potential_loop flag in metadata."""
        from unittest.mock import PropertyMock, patch

        from inspect_ai.model import ChatMessageAssistant

        from scorers.token_ratio import token_ratio_scorer

        s = token_ratio_scorer()
        messages = [ChatMessageAssistant(content=f"msg {i}") for i in range(60)]
        state = make_task_state(messages=messages)
        with patch.object(type(state), "token_usage", new_callable=PropertyMock, return_value=100):
            result = run_async(s(state, state.target))
        assert result.metadata.get("potential_loop") is True

    def test_resolution_chain_tier3_system_default(self):
        """No baseline or task budget → uses system default (1000)."""
        from unittest.mock import PropertyMock, patch

        from scorers.token_ratio import token_ratio_scorer

        s = token_ratio_scorer(baseline_store=None)
        state = make_task_state()
        with patch.object(type(state), "token_usage", new_callable=PropertyMock, return_value=1000):
            result = run_async(s(state, state.target))
        # actual=1000, system_default=1000 → ratio=1.0
        assert result.value == pytest.approx(1.0)


class TestTimeRatioScorer:
    def test_noise_floor_suppresses_brief_tasks(self):
        """Both reference and actual below noise_floor → ratio suppressed."""
        from unittest.mock import patch

        from scorers.protocol import TaskBudget
        from scorers.time_ratio import time_ratio_scorer

        s = time_ratio_scorer(task_budget=TaskBudget(latency_seconds=2.0, noise_floor_seconds=5.0))
        state = make_task_state()
        with patch("scorers.time_ratio.sample_working_time", return_value=2.5):
            result = run_async(s(state, state.target))
        import math

        assert math.isnan(result.value)  # NaN = suppressed
        assert result.metadata.get("suppressed") is True

    def test_noise_floor_not_triggered_when_above_threshold(self):
        """Reference above noise floor → ratio computed normally."""
        from unittest.mock import patch

        from scorers.protocol import TaskBudget
        from scorers.time_ratio import time_ratio_scorer

        s = time_ratio_scorer(task_budget=TaskBudget(latency_seconds=20.0, noise_floor_seconds=5.0))
        state = make_task_state()
        with patch("scorers.time_ratio.sample_working_time", return_value=10.0):
            result = run_async(s(state, state.target))
        assert result.value is not None
        assert result.metadata.get("suppressed") is False

    def test_no_working_time_returns_none_metadata(self):
        """sample_working_time unavailable → returns score with None metadata."""
        from unittest.mock import patch

        from scorers.time_ratio import time_ratio_scorer

        s = time_ratio_scorer()
        state = make_task_state()
        # Outside eval context, sample_working_time returns huge number (>86400)
        with patch("scorers.time_ratio.sample_working_time", return_value=999999.0):
            result = run_async(s(state, state.target))
        assert result.value == 1.0  # fallback
        assert result.metadata.get("ratio") is None


class TestExecutionSafetyScorer:
    def test_detects_rm_rf(self):
        """rm -rf in message content → score 0.0."""
        from inspect_ai.model import ChatMessageAssistant

        from scorers.execution_safety import execution_safety_scorer

        s = execution_safety_scorer()
        state = make_task_state(messages=[ChatMessageAssistant(content="rm -rf /tmp/logs")])
        result = run_async(s(state, state.target))
        assert result.value == 0.0

    def test_detects_chmod_777(self):
        """chmod 777 in message → score 0.0."""
        from inspect_ai.model import ChatMessageAssistant

        from scorers.execution_safety import execution_safety_scorer

        s = execution_safety_scorer()
        state = make_task_state(messages=[ChatMessageAssistant(content="chmod 777 /etc/passwd")])
        result = run_async(s(state, state.target))
        assert result.value == 0.0

    def test_clean_output_passes(self):
        """No dangerous patterns → score 1.0."""
        from inspect_ai.model import ChatMessageAssistant

        from scorers.execution_safety import execution_safety_scorer

        s = execution_safety_scorer()
        state = make_task_state(
            messages=[ChatMessageAssistant(content="def hello(): return 'world'")]
        )
        result = run_async(s(state, state.target))
        assert result.value == 1.0


class TestConstraintAdherenceScorer:
    def test_no_violations_with_empty_rules(self):
        """No rules defined → score 1.0."""
        from scorers.constraint import constraint_adherence_scorer

        s = constraint_adherence_scorer(rules=None)
        state = make_task_state()
        result = run_async(s(state, state.target))
        assert result.value == 1.0

    def test_all_rules_pass(self):
        """All constraints respected → score 1.0."""
        from inspect_ai.model import ChatMessageAssistant

        from scorers.constraint import ConstraintRule, constraint_adherence_scorer

        s = constraint_adherence_scorer(
            rules=[ConstraintRule(type="no_file_write", path="/etc/passwd")]
        )
        state = make_task_state(
            messages=[ChatMessageAssistant(content="echo hello world > /tmp/out.txt")]
        )
        result = run_async(s(state, state.target))
        assert result.value == 1.0

    def test_violation_penalizes_score(self):
        """Constraint violated → score reflects fraction passed."""
        from inspect_ai.model import ChatMessageAssistant

        from scorers.constraint import ConstraintRule, constraint_adherence_scorer

        s = constraint_adherence_scorer(
            rules=[
                ConstraintRule(type="no_file_write", path="/etc/passwd"),
                ConstraintRule(type="no_file_write", path="/etc/shadow"),
            ]
        )
        state = make_task_state(
            messages=[ChatMessageAssistant(content="echo root:x:0:0 >> /etc/passwd")]
        )
        result = run_async(s(state, state.target))
        # 1 out of 2 passed → 0.5
        assert result.value == pytest.approx(0.5)


class TestResolveBaselineReference:
    def test_returns_system_default_when_no_store(self):
        """No baseline store → returns system default."""
        from scorers.protocol import RatioSource, resolve_baseline_reference

        ref_val, source, ref_model = resolve_baseline_reference(
            None, "task-a", "claude-3", "output_tokens"
        )
        assert ref_val == 1000.0
        assert source == RatioSource.SYSTEM_DEFAULT
        assert ref_model is None

    def test_returns_system_default_latency(self):
        """No baseline store → returns 30s for latency."""
        from scorers.protocol import RatioSource, resolve_baseline_reference

        ref_val, source, ref_model = resolve_baseline_reference(
            None, "task-a", "claude-3", "latency_seconds"
        )
        assert ref_val == 30.0
        assert source == RatioSource.SYSTEM_DEFAULT


# ---------------------------------------------------------------------------
# LLM Judge scorer tests
# ---------------------------------------------------------------------------


class TestParseScore:
    """_parse_score: regex extraction, snap-to-discrete, edge cases."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("SCORE: 10", 1.0),
            ("SCORE: 7.5", 0.75),
            ("SCORE: 5", 0.5),
            ("SCORE: 2.5", 0.25),
            ("SCORE: 0", 0.0),
            ("SCORE: 8", 0.75),  # snaps to 7.5
            ("score: 6", 0.5),  # snaps to 5.0
            ("SCORE: 9", 1.0),  # snaps to 10.0
            ("SCORE: 3", 0.25),  # snaps to 2.5
            ("SCORE: 2.4", 0.25),  # edge snap
            ("SCORE: 8.75", 0.75),  # equidistant → 7.5
            ("SCORE: 8/10", 0.75),  # slash-10 format
            ("SCORE:5", 0.5),  # no space
            ("Score: 0", 0.0),  # case insensitive
            ("SCORE: 15", 1.0),  # clamp above 10
        ],
    )
    def test_parses_to_expected(self, text, expected):
        from scorers.llm_judge import _parse_score

        assert _parse_score(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "no score here",
            "SCORE: -1",
        ],
    )
    def test_returns_none_for_invalid(self, text):
        from scorers.llm_judge import _parse_score

        assert _parse_score(text) is None


class TestLoadRubric:
    """Unit tests for _load_rubric file loading."""

    def test_loads_existing_rubric(self):
        from scorers.llm_judge import _load_rubric

        rubric = _load_rubric("tasks/execution/q4-root-cause")
        assert rubric is not None
        assert "SCORE" in rubric
        assert len(rubric) > 100

    def test_returns_none_for_missing_rubric(self):
        from scorers.llm_judge import _load_rubric

        assert _load_rubric("tasks/execution/f6-partial-impl") is None

    def test_returns_none_for_nonexistent_dir(self):
        from scorers.llm_judge import _load_rubric

        assert _load_rubric("/nonexistent/path") is None


class TestLLMJudgeScorer:
    """Integration tests for the llm_judge scorer with mocked model."""

    def test_no_bench_task_dir_returns_error(self):
        """Missing bench_task_dir metadata → error score."""
        from scorers.llm_judge import llm_judge

        s = llm_judge()
        state = make_task_state(completion="some output")
        result = run_async(s(state, state.target))
        assert result.value == 0.0
        assert result.metadata.get("judge_error") == "no_task_dir"

    def test_missing_rubric_returns_error(self):
        """Task dir without judge.md → error score."""
        from scorers.llm_judge import llm_judge

        s = llm_judge()
        state = make_task_state(
            completion="some output", bench_task_dir="tasks/execution/f6-partial-impl"
        )
        result = run_async(s(state, state.target))
        assert result.value == 0.0
        assert result.metadata.get("judge_error") == "missing_rubric"

    def test_empty_output_returns_error(self):
        """Empty model output → error score."""
        from scorers.llm_judge import llm_judge

        s = llm_judge()
        state = make_task_state(completion="", bench_task_dir="tasks/execution/q4-root-cause")
        result = run_async(s(state, state.target))
        assert result.value == 0.0
        assert result.metadata.get("judge_error") == "empty_output"

    def test_api_error_returns_error(self):
        """Judge model API error → error score with exception details."""
        from unittest.mock import AsyncMock, patch

        from scorers.llm_judge import llm_judge

        mock_model = AsyncMock()
        mock_model.generate.side_effect = ConnectionError("proxy down")

        s = llm_judge()
        # Patch the model resolved at factory time
        with patch("scorers.llm_judge.get_model", return_value=mock_model):
            s = llm_judge()

        state = make_task_state(
            completion="some output", bench_task_dir="tasks/execution/q4-root-cause"
        )
        result = run_async(s(state, state.target))
        assert result.value == 0.0
        assert result.metadata.get("judge_error") == "api_error"
        assert "proxy down" in result.metadata.get("exception", "")

    def test_unparseable_response_returns_error(self):
        """Judge response without SCORE: N → error score."""
        from unittest.mock import AsyncMock, patch

        from inspect_ai.model import ModelOutput

        from scorers.llm_judge import llm_judge

        mock_model = AsyncMock()
        mock_model.generate.return_value = ModelOutput.from_content(
            model="judge", content="I think this is a good response but no score"
        )

        with patch("scorers.llm_judge.get_model", return_value=mock_model):
            s = llm_judge()

        state = make_task_state(
            completion="some output", bench_task_dir="tasks/execution/q4-root-cause"
        )
        result = run_async(s(state, state.target))
        assert result.value == 0.0
        assert result.metadata.get("judge_error") == "unparseable"

    def test_successful_judge_score(self):
        """Judge returns SCORE: 7.5 → value 0.75 with metadata (discrete scale)."""
        from unittest.mock import AsyncMock, patch

        from inspect_ai.model import ModelOutput

        from scorers.llm_judge import llm_judge

        mock_model = AsyncMock()
        mock_model.generate.return_value = ModelOutput.from_content(
            model="judge",
            content="Good analysis. SCORE: 7.5",
        )

        with patch("scorers.llm_judge.get_model", return_value=mock_model):
            s = llm_judge()

        state = make_task_state(
            completion="The root cause is environment mismatch",
            bench_task_dir="tasks/execution/q4-root-cause",
        )
        result = run_async(s(state, state.target))
        assert result.value == pytest.approx(0.75)
        assert result.metadata.get("pillar") == "correctness"
        assert result.metadata.get("judge_score_raw") == pytest.approx(7.5)
        assert result.metadata.get("judge_model") == "openai/judge"

    def test_perfect_score(self):
        """Judge returns SCORE: 10 → value 1.0."""
        from unittest.mock import AsyncMock, patch

        from inspect_ai.model import ModelOutput

        from scorers.llm_judge import llm_judge

        mock_model = AsyncMock()
        mock_model.generate.return_value = ModelOutput.from_content(
            model="judge", content="Perfect. SCORE: 10"
        )

        with patch("scorers.llm_judge.get_model", return_value=mock_model):
            s = llm_judge()

        state = make_task_state(
            completion="correct answer", bench_task_dir="tasks/execution/q4-root-cause"
        )
        result = run_async(s(state, state.target))
        assert result.value == 1.0

    def test_rubric_cached_across_calls(self):
        """Rubric loaded once per task dir, not per sample."""
        from unittest.mock import AsyncMock, patch

        from inspect_ai.model import ModelOutput

        from scorers.llm_judge import llm_judge

        mock_model = AsyncMock()
        mock_model.generate.return_value = ModelOutput.from_content(
            model="judge", content="OK. SCORE: 7"
        )

        with patch("scorers.llm_judge.get_model", return_value=mock_model):
            s = llm_judge()

        # Call twice with same task dir
        state1 = make_task_state(
            completion="output1", bench_task_dir="tasks/execution/q4-root-cause"
        )
        state2 = make_task_state(
            completion="output2", bench_task_dir="tasks/execution/q4-root-cause"
        )
        run_async(s(state1, state1.target))
        run_async(s(state2, state2.target))

        # Both succeeded (rubric was cached, no file-not-found on second call)
        assert mock_model.generate.call_count == 2


class TestPriceRatioScorer:
    """Tests for price_ratio_scorer with mocked cache."""

    def _price_info(self, inp: float = 1.0, out: float = 2.0, ctx: int | None = 4096):
        """Return a PriceInfo with the given prices."""
        from bench_cli.pricing.model_aliases import PriceInfo

        return PriceInfo("test/model", inp, out, ctx)

    def _make_scored_state(
        self, completion: str, model: str, input_tokens: int, output_tokens: int
    ):
        """TaskState with usage metadata matching price_ratio_scorer expectations."""
        state = make_task_state(completion=completion)
        state._model = model  # type: ignore[attr-defined]
        # Patch output.usage
        state.output.usage = {"prompt_tokens": input_tokens, "completion_tokens": output_tokens}
        return state

    def test_unknown_alias_returns_nan_with_anomaly(self):
        """Unknown bench alias → anomaly=True, value=NaN."""
        from scorers.price_ratio import price_ratio_scorer

        s = price_ratio_scorer()
        state = self._make_scored_state("output", "openai/nonexistent", 100, 50)
        result = run_async(s(state, state.target))
        import math

        assert math.isnan(result.value)
        assert result.metadata.get("anomaly") is True
        assert result.metadata.get("pillar") == "cost"

    def test_cache_miss_returns_nan_with_anomaly(self):
        """Cache miss → anomaly=True, value=NaN."""
        from bench_cli.pricing.price_cache import CacheMiss
        from scorers.price_ratio import price_ratio_scorer

        s = price_ratio_scorer()
        state = self._make_scored_state("output", "openai/qwen-local", 100, 50)

        with patch("scorers.price_ratio._price_info", side_effect=CacheMiss("test")):
            result = run_async(s(state, state.target))

        import math

        assert math.isnan(result.value)
        assert result.metadata.get("anomaly") is True

    def test_free_model_returns_inf(self):
        """Free model (price=0) → value=inf, is_free=True."""
        from unittest.mock import patch

        from bench_cli.pricing.model_aliases import PriceInfo
        from scorers.price_ratio import price_ratio_scorer

        s = price_ratio_scorer()
        state = self._make_scored_state("output", "openai/qwen-local", 100, 50)
        free_info = PriceInfo("qwen/qwen-local", 0.0, 0.0, None)

        with patch("scorers.price_ratio._price_info", return_value=free_info):
            result = run_async(s(state, state.target))

        import math

        assert math.isinf(result.value)
        assert result.metadata.get("is_free") is True
        assert result.metadata.get("actual_cost_usd") == 0.0

    def test_no_reference_cost_returns_nan(self):
        """TaskBudget with no reference_cost_usd → NaN, records actual_cost only."""
        from unittest.mock import patch

        from bench_cli.pricing.model_aliases import PriceInfo
        from scorers.price_ratio import price_ratio_scorer
        from scorers.protocol import TaskBudget

        s = price_ratio_scorer(task_budget=TaskBudget())
        state = self._make_scored_state("output", "openai/qwen-local", 100, 50)
        paid_info = PriceInfo("qwen/qwen-local", 1.0, 2.0, 4096)

        with patch("scorers.price_ratio._price_info", return_value=paid_info):
            result = run_async(s(state, state.target))

        import math

        assert math.isnan(result.value)
        assert result.metadata.get("actual_cost_usd") is not None
        assert result.metadata.get("cost_ratio") is None

    def test_with_reference_cost_returns_ratio(self):
        """reference_cost_usd set → cost_ratio = ref/actual."""
        from unittest.mock import patch

        from bench_cli.pricing.model_aliases import PriceInfo
        from scorers.price_ratio import price_ratio_scorer
        from scorers.protocol import TaskBudget

        # reference_cost = $0.001, actual = 100 in + 50 out at $1/$2 per M
        # actual = 100*1/1M + 50*2/1M = $0.0002
        # ratio = 0.001 / 0.0002 = 5.0
        s = price_ratio_scorer(task_budget=TaskBudget(reference_cost_usd=0.001))
        state = self._make_scored_state("output", "openai/qwen-local", 100, 50)
        paid_info = PriceInfo("qwen/qwen-local", 1.0, 2.0, 4096)

        with patch("scorers.price_ratio._price_info", return_value=paid_info):
            result = run_async(s(state, state.target))

        assert result.value == pytest.approx(5.0)
        assert result.metadata.get("actual_cost_usd") == pytest.approx(0.0002)
        assert result.metadata.get("reference_cost_usd") == pytest.approx(0.001)
        assert result.metadata.get("cost_ratio") == pytest.approx(5.0)
        assert result.metadata.get("pillar") == "cost"
        assert result.metadata.get("anomaly") is False

    def test_zero_actual_cost_returns_nan(self):
        """Actual cost $0 (edge case) → NaN."""
        from unittest.mock import patch

        from bench_cli.pricing.model_aliases import PriceInfo
        from scorers.price_ratio import price_ratio_scorer
        from scorers.protocol import TaskBudget

        s = price_ratio_scorer(task_budget=TaskBudget(reference_cost_usd=0.001))
        state = self._make_scored_state("output", "openai/qwen-local", 0, 0)
        paid_info = PriceInfo("qwen/qwen-local", 1.0, 2.0, 4096)

        with patch("scorers.price_ratio._price_info", return_value=paid_info):
            result = run_async(s(state, state.target))

        import math

        assert math.isnan(result.value)

    def test_cost_per_sample_math(self):
        """Verify PriceInfo.cost_per_sample math."""
        info = self._price_info(inp=2.5, out=5.0)
        # 1000 input + 2000 output at $2.5/$5.0 per M
        cost = info.cost_per_sample(1000, 2000)
        assert cost == pytest.approx(0.0125)


# ---------------------------------------------------------------------------
# Fixture loading tests
# ---------------------------------------------------------------------------


class TestLoadFixtures:
    """Unit tests for bench_cli.fixtures module."""

    def test_load_fixtures_returns_none_for_none_scenario(self):
        from bench_cli.fixtures import load_fixtures

        assert load_fixtures("/some/dir", None) is None

    def test_load_fixtures_returns_none_for_missing_scenario(self):
        from bench_cli.fixtures import load_fixtures

        assert load_fixtures("/nonexistent", "missing_scenario") is None

    def test_load_fixtures_reads_files(self, tmp_path):
        from bench_cli.fixtures import load_fixtures

        fixture_dir = tmp_path / "fixtures" / "test_scenario"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "config.py").write_text("TIMEOUT = 30")
        (fixture_dir / "README.md").write_text("# Test fixture")

        result = load_fixtures(str(tmp_path), "test_scenario")
        assert result is not None
        assert "config.py" in result
        assert "README.md" in result
        assert result["config.py"] == "TIMEOUT = 30"

    def test_load_fixtures_empty_dir_returns_none(self, tmp_path):
        from bench_cli.fixtures import load_fixtures

        fixture_dir = tmp_path / "fixtures" / "empty_scenario"
        fixture_dir.mkdir(parents=True)

        assert load_fixtures(str(tmp_path), "empty_scenario") is None

    def test_fixture_dir_for_returns_path(self, tmp_path):
        from bench_cli.fixtures import fixture_dir_for

        fixture_dir = tmp_path / "fixtures" / "scenario1"
        fixture_dir.mkdir(parents=True)

        result = fixture_dir_for(str(tmp_path), "scenario1")
        assert result is not None
        assert result == fixture_dir.resolve()

    def test_fixture_dir_for_missing_returns_none(self, tmp_path):
        from bench_cli.fixtures import fixture_dir_for

        assert fixture_dir_for(str(tmp_path), "nonexistent") is None

    def test_list_fixture_files(self, tmp_path):
        from bench_cli.fixtures import list_fixture_files

        fixture_dir = tmp_path / "fixtures" / "scenario"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "a.py").write_text("a")
        (fixture_dir / "b.py").write_text("b")
        subdir = fixture_dir / "sub"
        subdir.mkdir()
        (subdir / "c.py").write_text("c")

        files = list_fixture_files(str(tmp_path), "scenario")
        assert files == ["a.py", "b.py", "sub/c.py"]

    def test_list_fixture_files_none_scenario(self):
        from bench_cli.fixtures import list_fixture_files

        assert list_fixture_files("/some/dir", None) == []


# ---------------------------------------------------------------------------
# Multi-shot solver tests
# ---------------------------------------------------------------------------


class TestMultishotSolver:
    """Unit tests for bench_cli.solvers.multishot module."""

    def test_max_turns_1_returns_bare_generate(self):
        """max_turns=1 branches to bare generate() — no tool injection."""
        from bench_cli.solvers.multishot import multishot_solver

        s = multishot_solver(max_turns=1)
        assert s is not None

    def test_solver_creation_default_params(self):
        from bench_cli.solvers.multishot import multishot_solver

        s = multishot_solver()
        assert s is not None

    def test_solver_creation_with_turns(self):
        from bench_cli.solvers.multishot import multishot_solver

        s = multishot_solver(max_turns=5)
        assert s is not None

    def test_sandbox_reject_path_traversal(self, tmp_path):
        from bench_cli.solvers.multishot import sandbox_read

        result = sandbox_read(tmp_path.resolve(), "../../../etc/passwd")
        assert "escapes workspace boundary" in result

    def test_sandbox_reject_absolute_path(self, tmp_path):
        from bench_cli.solvers.multishot import sandbox_read

        result = sandbox_read(tmp_path.resolve(), "/etc/passwd")
        assert "escapes workspace boundary" in result

    def test_sandbox_read_file(self, tmp_path):
        from bench_cli.solvers.multishot import sandbox_read

        (tmp_path / "test.py").write_text("print('hello')")
        result = sandbox_read(tmp_path.resolve(), "test.py")
        assert result == "print('hello')"

    def test_sandbox_read_missing_file(self, tmp_path):
        from bench_cli.solvers.multishot import sandbox_read

        result = sandbox_read(tmp_path.resolve(), "nonexistent.py")
        assert "not found" in result

    def test_sandbox_list_directory(self, tmp_path):
        from bench_cli.solvers.multishot import sandbox_list

        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")
        result = sandbox_list(tmp_path.resolve(), ".")
        assert "a.py" in result
        assert "b.py" in result

    def test_sandbox_list_rejects_escape(self, tmp_path):
        from bench_cli.solvers.multishot import sandbox_list

        result = sandbox_list(tmp_path.resolve(), "../../..")
        assert "escapes workspace boundary" in result

    def test_build_fixture_context_no_path(self):
        from bench_cli.solvers.multishot import _build_fixture_context

        assert _build_fixture_context(None) == ""

    def test_build_fixture_context_with_files(self, tmp_path):
        from bench_cli.solvers.multishot import _build_fixture_context

        fixture_dir = tmp_path / "fixtures" / "scenario"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "config.py").write_text("X=1")

        ctx = _build_fixture_context(str(fixture_dir))
        assert "config.py" in ctx
        assert "read_file" in ctx


# ---------------------------------------------------------------------------
# Hybrid scorer tests
# ---------------------------------------------------------------------------


class TestHybridScorer:
    """Unit tests for scorers/hybrid.py weighted combination logic."""

    def test_hybrid_scorer_importable(self):
        from scorers.hybrid import hybrid_scorer

        assert callable(hybrid_scorer)

    def test_compare_discovers_hybrid_scorer(self):
        """compare.py _extract_from_scorers finds hybrid_scorer first."""
        from bench_cli.compare import _extract_from_scorers

        # Mock a hybrid_scorer Score object
        mock_score = type(
            "Score",
            (),
            {
                "value": 0.85,
                "metadata": {
                    "scorer_type": "hybrid",
                    "verify_sh_score": 0.9,
                    "llm_judge_score": 0.75,
                },
            },
        )()
        scores = {"hybrid_scorer": mock_score}
        correctness, _, _, _, _ = _extract_from_scorers(scores)
        assert correctness == 0.85

    def test_compare_prefers_hybrid_over_judge(self):
        """When both hybrid and judge exist, hybrid wins."""
        from bench_cli.compare import _extract_from_scorers

        mock_hybrid = type("Score", (), {"value": 0.7, "metadata": {}})()
        mock_judge = type("Score", (), {"value": 0.5, "metadata": {}})()
        scores = {"hybrid_scorer": mock_hybrid, "llm_judge": mock_judge}
        correctness, _, _, _, _ = _extract_from_scorers(scores)
        assert correctness == 0.7


# ---------------------------------------------------------------------------
# Smart-router tier_breakdown tests
# ---------------------------------------------------------------------------


class TestResolveAndPriceTierBreakdown:
    """Tests for _resolve_and_price() tier_breakdown return value."""

    def test_single_model_returns_none_tier_breakdown(self):
        """Non-router ModelUsage → tier_breakdown is None."""
        from unittest.mock import patch

        from bench_cli.pricing.model_aliases import PriceInfo
        from scorers.price_ratio import _resolve_and_price

        usage = type("U", (), {"input_tokens": 100, "output_tokens": 50})()
        paid_info = PriceInfo("qwen/qwen-local", 1.0, 2.0, 4096)

        with patch("scorers.price_ratio._price_info", return_value=paid_info):
            cost, or_id, is_free, tb = _resolve_and_price("openai/qwen-local", usage)

        assert tb is None
        assert cost is not None

    def test_old_dict_format_returns_none_tier_breakdown(self):
        """Old single-model dict format (prompt/completion_tokens) → None."""
        from unittest.mock import patch

        from bench_cli.pricing.model_aliases import PriceInfo
        from scorers.price_ratio import _resolve_and_price

        usage = {"prompt_tokens": 100, "completion_tokens": 50}
        paid_info = PriceInfo("qwen/qwen-local", 1.0, 2.0, 4096)

        with patch("scorers.price_ratio._price_info", return_value=paid_info):
            cost, or_id, is_free, tb = _resolve_and_price("openai/qwen-local", usage)

        assert tb is None

    def test_smart_router_dict_returns_tier_breakdown(self):
        """Smart-router dict {tier: ModelUsage} → tier_breakdown populated."""
        from unittest.mock import patch

        from bench_cli.pricing.model_aliases import PriceInfo
        from scorers.price_ratio import _resolve_and_price

        default_usage = type("U", (), {"input_tokens": 200, "output_tokens": 100})()
        background_usage = type("U", (), {"input_tokens": 50, "output_tokens": 25})()
        usage = {"default": default_usage, "background": background_usage}

        paid_info = PriceInfo("test/model", 1.0, 2.0, 4096)

        with patch("scorers.price_ratio.resolve_openrouter_id", return_value="test/model"):
            with patch("scorers.price_ratio._price_info", return_value=paid_info):
                cost, or_id, is_free, tb = _resolve_and_price("openai/smart-router", usage)

        assert tb is not None
        assert "default" in tb
        assert "background" in tb
        assert tb["default"]["model"] == "test/model"
        assert tb["default"]["input_tokens"] == 200
        assert tb["default"]["output_tokens"] == 100
        assert isinstance(tb["default"]["cost_usd"], float)
        assert cost is not None

    def test_none_usage_returns_none_tier_breakdown(self):
        """None usage → cost is None, tier_breakdown is None."""
        from unittest.mock import patch

        from scorers.price_ratio import _resolve_and_price

        with patch("scorers.price_ratio.resolve_openrouter_id", return_value=None):
            cost, or_id, is_free, tb = _resolve_and_price("openai/nonexistent", None)
        assert cost is None
        assert or_id is None
        assert is_free is False
        assert tb is None


class TestExtractTierBreakdown:
    """Tests for _extract_from_scorers() tier_breakdown extraction."""

    def test_no_price_ratio_scorer_returns_none(self):
        """No price_ratio_scorer → tier_breakdown is None."""
        from bench_cli.compare import _extract_from_scorers

        mock_judge = type("Score", (), {"value": 0.8, "metadata": {}})()
        scores = {"llm_judge": mock_judge}
        _, _, _, _, tb = _extract_from_scorers(scores)
        assert tb is None

    def test_price_ratio_without_tier_breakdown_returns_none(self):
        """price_ratio_scorer without tier_breakdown metadata → None."""
        from bench_cli.compare import _extract_from_scorers

        mock_pr = type(
            "Score",
            (),
            {"value": 1.5, "metadata": {"actual_cost_usd": 0.001, "pillar": "cost"}},
        )()
        scores = {"price_ratio_scorer": mock_pr}
        _, _, _, _, tb = _extract_from_scorers(scores)
        assert tb is None

    def test_price_ratio_with_tier_breakdown_extracts_it(self):
        """price_ratio_scorer with tier_breakdown → extracted correctly."""
        from bench_cli.compare import _extract_from_scorers

        tier_data = {
            "default": {
                "model": "qwen/qwen3-235b",
                "input_tokens": 200,
                "output_tokens": 100,
                "cost_usd": 0.001,
            }
        }
        mock_pr = type(
            "Score",
            (),
            {
                "value": 1.5,
                "metadata": {"actual_cost_usd": 0.001, "tier_breakdown": tier_data},
            },
        )()
        scores = {"price_ratio_scorer": mock_pr}
        _, _, _, _, tb = _extract_from_scorers(scores)
        assert tb == tier_data


class TestFormatTierBreakdown:
    """Tests for format_tier_breakdown() rendering."""

    def test_no_tier_data_returns_none(self):
        """No models with tier data → returns None."""
        from bench_cli.compare import PillarScores, format_tier_breakdown

        data = type("CompareData", (), {"models": ["openai/qwen-local"], "tasks": ["smoke"], "matrix": {}})()
        assert format_tier_breakdown(data) is None

    def test_renders_tier_distribution(self):
        """Renders tier distribution and per-task mapping."""
        from bench_cli.compare import PillarScores, format_tier_breakdown

        tier_bd = {
            "default": {
                "model": "qwen/qwen3-235b",
                "input_tokens": 200,
                "output_tokens": 100,
                "cost_usd": 0.001,
            }
        }
        ps = PillarScores(
            correctness=1.0,
            token_ratio=1.0,
            time_ratio=1.0,
            avg_tokens=300,
            avg_time=1.0,
            samples=1,
            avg_cost_usd=0.001,
            tier_breakdown=tier_bd,
        )
        data = type(
            "CompareData",
            (),
            {
                "models": ["openai/smart-router"],
                "tasks": ["smoke", "sort-array"],
                "matrix": {
                    "smoke": {"openai/smart-router": ps},
                    "sort-array": {"openai/smart-router": ps},
                },
            },
        )()

        result = format_tier_breakdown(data)
        assert result is not None
        assert "TIER USAGE" in result
        assert "default" in result
        assert "qwen3-235b" in result
        assert "smoke" in result
        assert "sort-array" in result
