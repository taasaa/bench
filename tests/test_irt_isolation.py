"""SC13: Core bench commands work without PyMC installed."""

from __future__ import annotations

from click.testing import CliRunner


def test_compare_works_without_pymc(monkeypatch, tmp_path):
    """bench compare runs fine even if pymc is not importable."""
    import builtins
    real_import = builtins.__import__

    def _block_pymc(name, *args, **kwargs):
        if name == "pymc" or name.startswith("pymc."):
            raise ImportError("no pymc in this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_pymc)

    from bench_cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["compare", "--log-dir", str(tmp_path)])
    assert result.exit_code == 0
