from __future__ import annotations

from pathlib import Path

from coding_mvge.spells._ignore import (
    default_is_excluded,
    is_ignored_dir_name,
    is_ignored_path,
)


class TestIgnorePredicates:
    def test_ignored_dir_names(self) -> None:
        assert is_ignored_dir_name(".venv") is True
        assert is_ignored_dir_name(".git") is True
        assert is_ignored_dir_name("src") is False

    def test_ignored_path(self) -> None:
        assert is_ignored_path(Path("a") / ".venv" / "x.py") is True
        assert is_ignored_path(Path("a") / "src" / "x.py") is False

    def test_default_is_excluded_dirs_only(self) -> None:
        assert default_is_excluded(Path(".venv"), True) is True
        assert default_is_excluded(Path(".venv"), False) is False
        assert default_is_excluded(Path("src"), True) is False
