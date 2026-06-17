"""bench inspect must find rewritten logs by routing alias OR recorded name."""
import shutil
from pathlib import Path

from click.testing import CliRunner

from bench_cli.inspect.cli import inspect
from bench_cli.inspect.core import _resolve_query_name
from bench_cli.run.core import resolve_recorded_name, rewrite_log_model_name


_FIXTURE = Path(__file__).parent / "fixtures" / "eval-logs" / "sample_success.eval"


def _copy_rewritten_log(dest_dir: Path, recorded_name: str) -> Path:
    dest = dest_dir / _FIXTURE.name
    shutil.copy2(_FIXTURE, dest)
    assert rewrite_log_model_name(dest, recorded_name) is True
    return dest


def test_stats_cli_finds_recorded_or_id_query_after_alias_normalization(tmp_path):
    _copy_rewritten_log(tmp_path, "minimaxai/minimax-m3")

    result = CliRunner().invoke(
        inspect,
        ["stats", "--model", "minimaxai/minimax-m3", "--log-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "f18_direct_answer_first" in result.output


def test_stats_cli_finds_recorded_name_from_routing_alias(tmp_path):
    # Round-trip invariant: querying by routing alias `openai/thinking` finds
    # logs recorded with that alias's live-resolved backing model. The expected
    # recorded name is whatever the proxy currently resolves — the test follows
    # the proxy by design, so a proxy rebind does not break it.
    recorded = resolve_recorded_name("openai/thinking", None)
    assert recorded != "openai/thinking", (
        "test premise broken: openai/thinking must resolve to a backing model "
        "(not the routing alias itself) for the round-trip to be meaningful"
    )
    _copy_rewritten_log(tmp_path, recorded)

    result = CliRunner().invoke(
        inspect,
        ["stats", "--model", "openai/thinking", "--log-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "f18_direct_answer_first" in result.output


def test_stats_cli_finds_custom_as_label_after_alias_normalization(tmp_path):
    _copy_rewritten_log(tmp_path, "my-custom-label")

    result = CliRunner().invoke(
        inspect,
        ["stats", "--model", "my-custom-label", "--log-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "f18_direct_answer_first" in result.output


def test_stats_cli_finds_recorded_or_id_from_recognizable_bare_alias(tmp_path):
    _copy_rewritten_log(tmp_path, "nvidia/nemotron-3-ultra-550b-a55b")

    result = CliRunner().invoke(
        inspect,
        ["stats", "--model", "nemotron-ultra-550b", "--log-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "f18_direct_answer_first" in result.output


def test_resolve_query_name_passes_recorded_through():
    # Invariant: query-side resolution mirrors record-side resolution. The two
    # functions must agree so a user querying by routing alias finds logs
    # recorded by routing alias. Tested live (whatever the proxy resolves) so
    # the invariant holds across proxy rebinds.
    alias = "openai/thinking"
    assert _resolve_query_name(alias) == resolve_recorded_name(alias, None)


def test_resolve_query_name_passes_or_id_through():
    # If user queries with an OR id, it's already recorded form -> unchanged
    assert _resolve_query_name("minimaxai/minimax-m3") == "minimaxai/minimax-m3"


def test_resolve_query_name_managed_passthrough():
    assert _resolve_query_name("openai/qwen-local") == "openai/qwen-local"


def test_resolve_query_name_custom_as_is_opaque():
    # R5: a custom --as value with no LiteLLM backing resolves to itself.
    # Users query such logs by the literal --as value (matched via raw input).
    # NOTE: use a genuinely opaque name — 'nemotron-ultra-550b' is NOT opaque
    # (it resolves via LiteLLM to nvidia/nemotron-3-ultra-550b-a55b).
    assert _resolve_query_name("my-custom-label") == "my-custom-label"
