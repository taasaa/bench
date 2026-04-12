"""Tests for scorers/fixtures.py — fixture loading utilities."""

import importlib.util
import sys
from pathlib import Path

import pytest

# Load scorers.fixtures directly to avoid pulling in inspect_ai
# (not installed in this environment) via scorers/__init__.py.
_mod_path = Path(__file__).resolve().parent.parent / "scorers" / "fixtures.py"
_spec = importlib.util.spec_from_file_location("scorers.fixtures", _mod_path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["scorers.fixtures"] = _mod
_spec.loader.exec_module(_mod)

fixtures_dir = _mod.fixtures_dir
load_fixture = _mod.load_fixture
load_fixture_bytes = _mod.load_fixture_bytes


class TestFixturesDir:
    """Tests for fixtures_dir()."""

    def test_fixtures_dir_returns_correct_path(self, tmp_path):
        """Given a task.py path, returns the fixtures/ sibling directory."""
        task_dir = tmp_path / "my-task"
        task_dir.mkdir()
        (task_dir / "task.py").touch()
        (task_dir / "fixtures").mkdir()

        result = fixtures_dir(task_dir / "task.py")

        assert result == task_dir / "fixtures"

    def test_fixtures_dir_from_nested_path(self, tmp_path):
        """Verify it works with realistic path like tasks/code_gen/my-task/task.py."""
        nested = tmp_path / "tasks" / "code_gen" / "my-task"
        nested.mkdir(parents=True)
        (nested / "task.py").touch()
        (nested / "fixtures").mkdir()

        result = fixtures_dir(nested / "task.py")

        assert result == nested / "fixtures"
        assert result.is_dir()

    def test_fixtures_dir_raises_on_missing(self, tmp_path):
        """Raises FileNotFoundError with helpful message when fixtures dir missing."""
        task_dir = tmp_path / "lonely-task"
        task_dir.mkdir()
        (task_dir / "task.py").touch()
        # No fixtures/ directory created

        with pytest.raises(FileNotFoundError, match="Fixtures directory not found"):
            fixtures_dir(task_dir / "task.py")

    def test_fixtures_dir_accepts_string_path(self, tmp_path):
        """Accepts plain string in addition to Path."""
        task_dir = tmp_path / "str-task"
        task_dir.mkdir()
        (task_dir / "task.py").touch()
        (task_dir / "fixtures").mkdir()

        result = fixtures_dir(str(task_dir / "task.py"))

        assert result == task_dir / "fixtures"


class TestLoadFixture:
    """Tests for load_fixture()."""

    def test_load_fixture_reads_file_content(self, tmp_path):
        """Create a temp fixtures/ dir with a file, verify content loaded."""
        task_dir = tmp_path / "read-task"
        task_dir.mkdir()
        (task_dir / "task.py").touch()
        fix_dir = task_dir / "fixtures"
        fix_dir.mkdir()
        (fix_dir / "input.py").write_text("def hello():\n    return 42\n", encoding="utf-8")

        content = load_fixture(task_dir / "task.py", "input.py")

        assert content == "def hello():\n    return 42\n"

    def test_load_fixture_raises_on_missing(self, tmp_path):
        """Verify FileNotFoundError with helpful message for missing fixture."""
        task_dir = tmp_path / "missing-task"
        task_dir.mkdir()
        (task_dir / "task.py").touch()
        fix_dir = task_dir / "fixtures"
        fix_dir.mkdir()
        (fix_dir / "other.txt").write_text("exists", encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="Fixture file not found"):
            load_fixture(task_dir / "task.py", "nonexistent.py")

    def test_load_fixture_reads_nested_fixture(self, tmp_path):
        """Supports subdirectory references like data/config.json."""
        task_dir = tmp_path / "nested-task"
        task_dir.mkdir()
        (task_dir / "task.py").touch()
        fix_dir = task_dir / "fixtures"
        sub_dir = fix_dir / "data"
        sub_dir.mkdir(parents=True)
        (sub_dir / "config.json").write_text('{"key": "value"}', encoding="utf-8")

        content = load_fixture(task_dir / "task.py", "data/config.json")

        assert '"key"' in content

    def test_load_fixture_string_task_file(self, tmp_path):
        """Accepts string path for task_file."""
        task_dir = tmp_path / "str-task"
        task_dir.mkdir()
        (task_dir / "task.py").touch()
        fix_dir = task_dir / "fixtures"
        fix_dir.mkdir()
        (fix_dir / "hello.txt").write_text("world", encoding="utf-8")

        content = load_fixture(str(task_dir / "task.py"), "hello.txt")

        assert content == "world"


class TestLoadFixtureBytes:
    """Tests for load_fixture_bytes()."""

    def test_load_fixture_bytes_returns_bytes(self, tmp_path):
        """Verify binary loading works and returns bytes."""
        task_dir = tmp_path / "bin-task"
        task_dir.mkdir()
        (task_dir / "task.py").touch()
        fix_dir = task_dir / "fixtures"
        fix_dir.mkdir()
        raw = b"\x00\x01\x02\xff"
        (fix_dir / "data.bin").write_bytes(raw)

        result = load_fixture_bytes(task_dir / "task.py", "data.bin")

        assert isinstance(result, bytes)
        assert result == raw

    def test_load_fixture_bytes_raises_on_missing(self, tmp_path):
        """Raises FileNotFoundError for missing binary fixture."""
        task_dir = tmp_path / "bin-missing"
        task_dir.mkdir()
        (task_dir / "task.py").touch()
        (task_dir / "fixtures").mkdir()

        with pytest.raises(FileNotFoundError, match="Fixture file not found"):
            load_fixture_bytes(task_dir / "task.py", "missing.bin")

    def test_load_fixture_bytes_preserves_utf8(self, tmp_path):
        """Binary load of a text file preserves exact bytes including BOM."""
        task_dir = tmp_path / "utf8-task"
        task_dir.mkdir()
        (task_dir / "task.py").touch()
        fix_dir = task_dir / "fixtures"
        fix_dir.mkdir()
        # Write with BOM
        content = "\ufeffHello, world!"
        (fix_dir / "bom.txt").write_text(content, encoding="utf-8-sig")

        result = load_fixture_bytes(task_dir / "task.py", "bom.txt")

        assert result.startswith(b"\xef\xbb\xbf")
