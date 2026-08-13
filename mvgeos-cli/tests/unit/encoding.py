from __future__ import annotations

import io
import sys
from unittest.mock import patch

from mvgeos_agent.snapshot import RuntimeSnapshot, SnapshotSpell, SpellSource
from typer.testing import CliRunner

from mvgeos_cli.commands.info import _render_snapshot, info
from mvgeos_cli.console import configure_streams, get_console, is_utf8_stream
from mvgeos_cli.main import app

runner = CliRunner()


def _make_simple_snapshot() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        agent_name="encoding-agent",
        model="nvidia/nemotron-3-ultra-550b-a55b:free",
        spells=[
            SnapshotSpell(
                name="bash",
                description="Run shell command",
                source=SpellSource.BUILTIN,
                parameters={},
            ),
        ],
    )


def test_is_utf8_stream_with_utf8() -> None:
    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding="utf-8")
    assert is_utf8_stream(stream) is True


def test_is_utf8_stream_with_cp1252() -> None:
    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding="cp1252")
    assert is_utf8_stream(stream) is False


def test_render_snapshot_ascii_only() -> None:
    snap = _make_simple_snapshot()
    output = _render_snapshot(snap, ascii_only=True)
    assert "+---" in output or "+=" in output or "|" in output
    assert "encoding-agent" in output
    # Ensure no non-ASCII box characters (e.g. ┌, ─, │) are present
    assert all(ord(ch) < 128 for ch in output)


def test_render_snapshot_utf8_default() -> None:
    snap = _make_simple_snapshot()
    output = _render_snapshot(snap, ascii_only=False)
    assert "encoding-agent" in output
    # UTF-8 table rendering produces characters outside 0x00-0x7F
    assert any(ord(ch) >= 128 for ch in output)


def test_info_cp1252_stream_execution() -> None:
    snap = _make_simple_snapshot()
    with patch("mvgeos_cli.commands.info._assemble") as mock_assemble:
        mock_assemble.return_value = snap

        buf = io.BytesIO()
        cp1252_stream = io.TextIOWrapper(buf, encoding="cp1252", errors="strict")

        with patch.object(sys, "stdout", cp1252_stream):
            info(agent_name="default-mvge", extension_dir=None, output=None)

        rendered = buf.getvalue().decode("cp1252")
        assert "encoding-agent" in rendered


def test_cli_help_no_em_dash() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "\u2014" not in result.output
    assert "MvgeOS - a Python-based AI coding agent" in result.output


def test_get_console_non_utf8_safe_box() -> None:
    buf = io.BytesIO()
    cp1252_stream = io.TextIOWrapper(buf, encoding="cp1252")
    c = get_console(file=cp1252_stream)
    assert c.safe_box is True


def test_configure_streams_executes() -> None:
    # Verify configure_streams runs without error
    configure_streams()
