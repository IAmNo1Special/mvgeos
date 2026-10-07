"""Tests for the install-verification harness.

`scripts/verify_install.py` exists to answer one question for a release: would a
stranger who has never seen this repository get a working `mvgeos`? The
expensive half of that -- installing from PyPI, calling a model -- is mocked out
by never being run here. What is under test is every judgement the harness makes
about what it saw, because each of those can be wrong while still printing a
confident green summary:

* an environment that leaks the host's ``HOME`` and quietly turns "a stranger's
  machine" into this machine;
* a wrapped ``WARNING:`` miscounted as the model's first token, which
  understates time-to-first-token by however long Realm setup took;
* a Tome with no Spell cast reported as a completed task.

The transcript helpers are the fragile part. An earlier revision stamped only
the first of several lines and printed ``0.00s`` for the rest, which renders a
real gap as simultaneity. ``test_each_line_keeps_its_own_arrival_time`` is the
regression that stops that coming back.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest
import verify_install


def test_clean_env_cannot_see_the_host(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The harness must not inherit state from the machine running it."""
    monkeypatch.setenv("MVGEOS_SESSION", "leaked")
    monkeypatch.setenv("HOME", "/home/somebody-else")

    env = verify_install.clean_env(tmp_path / "home", tmp_path / "cache", "sk-or-v")

    assert env["HOME"] == str(tmp_path / "home")
    assert env["OPENROUTER_API_KEY"] == "sk-or-v"
    assert "MVGEOS_SESSION" not in env
    # Rich reflows to the console width; the harness needs it pinned so a
    # multi-line preamble stays recognisable as one message.
    assert env["COLUMNS"] == "400"
    assert not [key for key in env if key.startswith("_")]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("WARNING: --approval-mode=allow-all: approved.", False),
        ("Error: API key required.", False),
        ("", False),
        ("   ", False),
        ("The file hello.txt has been created.", True),
        ("Stop reason: stop", True),
    ],
)
def test_local_preamble_is_not_the_first_token(line: str, expected: bool) -> None:
    assert verify_install.is_model_output(line) is expected


def test_each_line_keeps_its_own_arrival_time() -> None:
    """Regression: a transcript that flattens later lines to 0.00s."""
    transcript = verify_install.stamp_lines(
        [(0.61, "WARNING: local"), (2.56, "The file hello.txt has been created.")]
    )

    assert "[   0.61s] WARNING: local" in transcript
    assert "[   2.56s] The file hello.txt has been created." in transcript


def _tome(
    tmp_path: pathlib.Path,
    name: str,
    model: str,
    spells: list[str],
) -> pathlib.Path:
    """A minimal Tome: a session header plus one message per Spell cast."""
    sessions = tmp_path / ".agents" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    path = sessions / name
    records: list[dict[str, object]] = [
        {"type": "session", "id": "abc", "model": model, "spells": spells}
    ]
    for spell in spells:
        records.append(
            {
                "type": "message",
                "payload": {
                    "role": "assistant",
                    "content": [{"type": "spell_cast", "spell_cast": {"name": spell}}],
                },
            }
        )
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def test_newest_tome_prefers_the_most_recent(tmp_path: pathlib.Path) -> None:
    older = _tome(tmp_path, "older.jsonl", "openai/gpt-4o-mini", ["write"])
    newer = _tome(tmp_path, "newer.jsonl", "openai/gpt-4o-mini", ["write"])
    # Lock files sit beside the Tomes and must never be mistaken for one.
    (older.parent / "newer.jsonl.lock").write_text("", encoding="utf-8")
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    assert verify_install.newest_tome(older.parent) == newer


def test_newest_tome_is_none_when_nothing_persisted(
    tmp_path: pathlib.Path,
) -> None:
    assert verify_install.newest_tome(tmp_path / "sessions") is None


def test_session_header_survives_a_corrupt_leading_line(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text(
        "{not json\n" + json.dumps({"type": "session", "model": "openai/gpt-4o-mini"}),
        encoding="utf-8",
    )

    header = verify_install.session_header(path)

    assert header is not None
    assert header["model"] == "openai/gpt-4o-mini"


def test_cast_spells_names_the_spell_once(tmp_path: pathlib.Path) -> None:
    path = _tome(tmp_path, "t.jsonl", "openai/gpt-4o-mini", ["write", "write", "read"])

    assert verify_install.cast_spells(path) == ["write", "read"]


def test_a_tome_with_no_spell_cast_is_detectable(tmp_path: pathlib.Path) -> None:
    """The run must not count as a completed task when nothing was written."""
    path = _tome(tmp_path, "t.jsonl", "openai/gpt-4o-mini", [])

    assert verify_install.cast_spells(path) == []
