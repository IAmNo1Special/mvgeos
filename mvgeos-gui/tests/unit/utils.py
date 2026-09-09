"""Unit tests for mvgeos-gui shared utilities."""

from __future__ import annotations

from unittest.mock import patch

from mvgeos_gui.utils import (
    _sanitize_filename,
    copy_to_clipboard,
    data_uri_escape,
    download_artifact,
    js_escape,
)


def test_sanitize_filename_replaces_invalid_characters() -> None:
    """Invalid characters for file systems should be replaced by underscores."""
    raw = 'file<>:"/\\|?*\x00name.txt'
    sanitized = _sanitize_filename(raw)
    for bad_char in '<>:"/\\|?*\x00':
        assert bad_char not in sanitized
    assert sanitized == "file_name.txt"


def test_sanitize_filename_collapses_consecutive_underscores() -> None:
    """Multiple consecutive underscores should be collapsed into a single underscore."""
    assert _sanitize_filename("foo___bar///baz") == "foo_bar_baz"


def test_sanitize_filename_strips_leading_trailing_dots_and_spaces() -> None:
    """Leading and trailing dots and whitespace should be stripped."""
    assert _sanitize_filename(" .my_file.md. ") == "my_file.md"


def test_sanitize_filename_avoids_windows_reserved_names() -> None:
    """Windows reserved device names should be prefixed with an underscore."""
    assert _sanitize_filename("con") == "_con"
    assert _sanitize_filename("NUL") == "_NUL"
    assert _sanitize_filename("aux") == "_aux"
    assert _sanitize_filename("prn") == "_prn"
    assert _sanitize_filename("COM1") == "_COM1"
    assert _sanitize_filename("lpt9") == "_lpt9"


def test_sanitize_filename_limits_length_to_255() -> None:
    """Filenames longer than 255 characters should be truncated."""
    long_name = "a" * 300
    sanitized = _sanitize_filename(long_name)
    assert len(sanitized) == 255
    assert sanitized == "a" * 255


def test_sanitize_filename_fallback_when_empty() -> None:
    """Empty or whitespace-only names should fall back to 'artifact'."""
    assert _sanitize_filename("") == "artifact"
    assert _sanitize_filename("   ...  ") == "artifact"


def test_js_escape_escapes_special_characters() -> None:
    """Special JavaScript literal characters must be properly escaped."""
    raw = "slash\\backtick`dollar$newline\ncr\rtab\tsingle'tag</script>"
    escaped = js_escape(raw)
    assert "\\\\" in escaped
    assert "\\`" in escaped
    assert "\\$" in escaped
    assert "\\n" in escaped
    assert "\\r" in escaped
    assert "\\t" in escaped
    assert "\\'" in escaped
    assert "<\\/script>" in escaped


def test_data_uri_escape() -> None:
    """Data URI escape should safely encode characters."""
    raw = "hello world & <foo> ?"
    escaped = data_uri_escape(raw)
    assert " " not in escaped
    assert "%20" in escaped
    assert "%26" in escaped


def test_copy_to_clipboard() -> None:
    """copy_to_clipboard should run JS clipboard write and notify user."""
    with (
        patch("mvgeos_gui.utils.ui.run_javascript") as mock_js,
        patch("mvgeos_gui.utils.ui.notify") as mock_notify,
    ):
        copy_to_clipboard("test `code` with $var\n")
        assert mock_js.called
        js_arg = mock_js.call_args[0][0]
        assert "navigator.clipboard.writeText" in js_arg
        assert "\\`code\\`" in js_arg
        assert "\\$var" in js_arg
        mock_notify.assert_called_once_with(
            "Copied to clipboard", type="positive", position="bottom"
        )


def test_download_artifact() -> None:
    """download_artifact should trigger browser download with sanitized name."""
    with (
        patch("mvgeos_gui.utils.ui.run_javascript") as mock_js,
        patch("mvgeos_gui.utils.ui.notify") as mock_notify,
    ):
        download_artifact("my:title", "artifact content\nwith markdown")
        assert mock_js.called
        js_arg = mock_js.call_args[0][0]
        assert "document.createElement('a')" in js_arg
        assert "my_title.md" in js_arg
        assert "artifact%20content" in js_arg
        mock_notify.assert_called_once_with(
            "Downloading my_title.md", type="positive", position="bottom"
        )
