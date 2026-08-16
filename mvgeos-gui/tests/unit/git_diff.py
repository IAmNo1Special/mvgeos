"""Unit tests for git diff parsing and file change tracking."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from mvgeos_gui.git_diff import (
    get_changed_files,
    get_diff_for_file,
    parse_git_diff,
)

SAMPLE_DIFF = """\
diff --git a/src/main.py b/src/main.py
index abc1234..def5678 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,5 +1,6 @@
 # Module header
+import os

 def main():
-    print("hello")
+    print("hello world")
     return True

diff --git a/README.md b/README.md
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/README.md
@@ -0,0 +1,3 @@
+# Project
+
+This is a project.

"""


def test_parse_git_diff_returns_diff_views() -> None:
    """Verify parse_git_diff returns a DiffView per changed file."""
    views = parse_git_diff(SAMPLE_DIFF)
    assert len(views) == 2
    assert views[0].file_path == "src/main.py"
    assert views[0].status == "modified"
    assert views[1].file_path == "README.md"
    assert views[1].status == "added"


def test_parse_git_diff_calculates_additions_and_deletions() -> None:
    """Verify each hunk reports correct addition/deletion line counts."""
    views = parse_git_diff(SAMPLE_DIFF)
    main_view = views[0]
    assert main_view.additions == 2
    assert main_view.deletions == 1


def test_parse_git_diff_hunks_have_line_numbers() -> None:
    """Verify hunks preserve source and target line numbers."""
    views = parse_git_diff(SAMPLE_DIFF)
    main_view = views[0]
    assert len(main_view.hunks) == 1
    hunk = main_view.hunks[0]
    assert hunk.source_start == 1
    assert hunk.source_length == 5
    assert hunk.target_start == 1
    assert hunk.target_length == 6


def test_parse_git_diff_hunk_lines_classified() -> None:
    """Verify diff lines are classified as context/addition/deletion."""
    views = parse_git_diff(SAMPLE_DIFF)
    main_view = views[0]
    hunk = main_view.hunks[0]
    line_types = [line.line_type for line in hunk.lines]
    assert "context" in line_types
    assert "addition" in line_types
    assert "deletion" in line_types


def test_parse_git_diff_new_file_status() -> None:
    """Verify newly added files are marked with status 'added'."""
    views = parse_git_diff(SAMPLE_DIFF)
    readme_view = views[1]
    assert readme_view.status == "added"
    assert readme_view.additions == 3
    assert readme_view.deletions == 0


def test_parse_git_diff_empty_input_returns_empty_list() -> None:
    """Verify empty diff string returns empty list."""
    assert parse_git_diff("") == []


def test_parse_git_diff_no_diff_marker_returns_empty() -> None:
    """Verify input with no diff markers returns empty list."""
    assert parse_git_diff("no diff here") == []


EMPTY_DIFF = """diff --git a/src/main.py b/src/main.py
index abc1234..def5678 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,3 @@
 # header
 unchanged
 unchanged
"""


def test_parse_git_diff_zero_changes() -> None:
    """Verify hunk with only context lines has zero additions and deletions."""
    views = parse_git_diff(EMPTY_DIFF)
    assert len(views) == 1
    assert views[0].additions == 0
    assert views[0].deletions == 0


DELETED_DIFF = """diff --git a/old_file.py b/old_file.py
deleted file mode 100644
index abc1234..0000000
--- a/old_file.py
+++ /dev/null
@@ -1,2 +0,0 @@
-line1
-line2
"""


def test_parse_git_diff_deleted_file() -> None:
    """Verify deleted files are marked with status 'deleted'."""
    views = parse_git_diff(DELETED_DIFF)
    assert len(views) == 1
    assert views[0].status == "deleted"
    assert views[0].additions == 0
    assert views[0].deletions == 2


class TestGetChangedFiles:
    def test_returns_changed_files_list(self, tmp_path: Path) -> None:
        """Verify get_changed_files returns ChangedFile entries."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')\n")
        diff_output = "1\t0\tsrc/main.py\n"
        mock_result = MagicMock(stdout=diff_output, returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            files = get_changed_files(tmp_path)
        assert len(files) == 1
        assert files[0].path == "src/main.py"
        assert files[0].status == "added"
        assert files[0].additions == 1
        assert files[0].deletions == 0

    def test_empty_repo_returns_empty_list(self, tmp_path: Path) -> None:
        """Verify get_changed_files returns empty list when no changes."""
        mock_result = MagicMock(stdout="", returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            files = get_changed_files(tmp_path)
        assert files == []

    def test_subprocess_failure_returns_empty_list(self, tmp_path: Path) -> None:
        """Verify get_changed_files returns empty list on subprocess error."""
        import subprocess

        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            files = get_changed_files(tmp_path)
        assert files == []


class TestGetDiffForFile:
    def test_returns_diff_view(self, tmp_path: Path) -> None:
        """Verify get_diff_for_file returns a DiffView for the requested file."""
        diff_text = """diff --git a/src/main.py b/src/main.py
index abc1234..def5678 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,2 +1,3 @@
 # header
+import os
 print('hello')
"""
        mock_result = MagicMock(stdout=diff_text, returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            view = get_diff_for_file(tmp_path, "src/main.py")
        assert view is not None
        assert view.file_path == "src/main.py"
        assert view.status == "modified"
        assert view.additions == 1
        assert view.deletions == 0

    def test_returns_none_for_unchanged_file(self, tmp_path: Path) -> None:
        """Verify get_diff_for_file returns None when file has no diff."""
        mock_result = MagicMock(stdout="", returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            view = get_diff_for_file(tmp_path, "src/main.py")
        assert view is None

    def test_returns_none_on_subprocess_error(self, tmp_path: Path) -> None:
        """Verify get_diff_for_file returns None on subprocess error."""
        import subprocess

        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            view = get_diff_for_file(tmp_path, "src/main.py")
        assert view is None
