"""Unit tests for verify_sh scorer."""

import os
import stat

import pytest

# Helpers imported from conftest.py
from conftest import make_task_state, run_async

from scorers.verify_sh import verify_sh


def _make_script(content: str, tmpdir: str, name: str = "verify.sh") -> str:
    """Create an executable verify.sh script in tmpdir."""
    path = os.path.join(tmpdir, name)
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVerifyShPass:
    def test_pass_full(self, tmp_path):
        """PASS 3/3 → score 1.0"""
        _make_script(
            '#!/bin/bash\necho "PASS 3/3"',
            str(tmp_path),
        )
        s = verify_sh()
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            state = make_task_state("model response", bench_task_dir=str(tmp_path))
            result = run_async(s(state, state.target))
        finally:
            os.chdir(orig)
        assert result.value == 1.0
        assert "PASS 3/3" in result.explanation
        assert "correctness=1.00" in result.explanation

    def test_pass_partial(self, tmp_path):
        """PASS 2/3 → score ≈ 0.667"""
        _make_script(
            '#!/bin/bash\necho "PASS 2/3"',
            str(tmp_path),
        )
        s = verify_sh()
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            state = make_task_state("model response", bench_task_dir=str(tmp_path))
            result = run_async(s(state, state.target))
        finally:
            os.chdir(orig)
        assert result.value == pytest.approx(2 / 3)


class TestVerifyShFail:
    def test_fail_output(self, tmp_path):
        """FAIL → score 0.0"""
        _make_script(
            '#!/bin/bash\necho "FAIL"\necho "something wrong" >&2',
            str(tmp_path),
        )
        s = verify_sh()
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            state = make_task_state("model response", bench_task_dir=str(tmp_path))
            result = run_async(s(state, state.target))
        finally:
            os.chdir(orig)
        assert result.value == 0.0
        assert "FAIL" in result.explanation


class TestVerifyShTimeout:
    def test_timeout(self, tmp_path):
        """Script timeout → score 0.0 with error explanation"""
        _make_script(
            '#!/bin/bash\nsleep 10\necho "PASS 1/1"',
            str(tmp_path),
        )
        s = verify_sh(timeout=1)
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            state = make_task_state("model response", bench_task_dir=str(tmp_path))
            result = run_async(s(state, state.target))
        finally:
            os.chdir(orig)
        assert result.value == 0.0
        assert "timeout" in result.explanation.lower()


class TestVerifyShScriptNotFound:
    def test_missing_script(self, tmp_path):
        """Missing verify.sh → score 0.0 with script-not-found explanation"""
        s = verify_sh()
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            state = make_task_state("model response", bench_task_dir=str(tmp_path))
            result = run_async(s(state, state.target))
        finally:
            os.chdir(orig)
        assert result.value == 0.0
        assert "no such file" in result.explanation.lower()


class TestVerifyShEdgeCases:
    def test_empty_output(self):
        """Empty model output → score 0.0"""
        s = verify_sh()
        state = make_task_state("")
        result = run_async(s(state, state.target))
        assert result.value == 0.0
        assert "empty" in result.explanation.lower()

    def test_bare_pass(self, tmp_path):
        """Bare PASS (no fraction) → score 1.0"""
        _make_script(
            '#!/bin/bash\necho "PASS"',
            str(tmp_path),
        )
        s = verify_sh()
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            state = make_task_state("model response", bench_task_dir=str(tmp_path))
            result = run_async(s(state, state.target))
        finally:
            os.chdir(orig)
        assert result.value == 1.0

    def test_pass_with_stderr(self, tmp_path):
        """PASS with stderr diagnostics → score value correct, stderr in explanation"""
        _make_script(
            '#!/bin/bash\necho "some diagnostic" >&2\necho "PASS 1/1"',
            str(tmp_path),
        )
        s = verify_sh()
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            state = make_task_state("model response", bench_task_dir=str(tmp_path))
            result = run_async(s(state, state.target))
        finally:
            os.chdir(orig)
        assert result.value == 1.0
        assert "some diagnostic" in result.explanation

    def test_pass_in_middle_of_output(self, tmp_path):
        """PASS line in middle of multi-line output → correctly parsed"""
        _make_script(
            '#!/bin/bash\necho "Checking..."\necho "PASS 4/5"\necho "done"',
            str(tmp_path),
        )
        s = verify_sh()
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            state = make_task_state("model response", bench_task_dir=str(tmp_path))
            result = run_async(s(state, state.target))
        finally:
            os.chdir(orig)
        assert result.value == pytest.approx(0.8)
