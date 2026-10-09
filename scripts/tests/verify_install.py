"""Tests for the install-verification harness.

`scripts/verify_install.py` exists to answer one question for a release: would a
stranger who has never seen this repository get a working `mvgeos`? The
expensive half of that -- installing from PyPI, calling a model -- is mocked out
by never being run here. What is under test is every judgement the harness makes
about what it saw, because each of those can be wrong while still printing a
confident green summary:

* an environment that leaks the host's ``HOME`` and quietly turns "a stranger's
  machine" into this machine;
* a sandbox that binds the operator's own directory and calls itself clean;
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


def _scratch(tmp_path: pathlib.Path) -> pathlib.Path:
    scratch = tmp_path / "scratch"
    for name in ("home", "cache", "work", "harness"):
        (scratch / name).mkdir(parents=True, exist_ok=True)
    return scratch


def _bound_sources(command: list[str]) -> list[str]:
    """The host paths a bwrap argv exposes, read off the command itself."""
    return [command[i + 1] for i, arg in enumerate(command) if arg == "--ro-bind"]


def _bound_writes(command: list[str]) -> list[str]:
    """The host paths a bwrap argv mounts read-write."""
    return [command[i + 1] for i, arg in enumerate(command) if arg == "--bind"]


@pytest.mark.skipif(
    os.name == "nt",
    reason=(
        "The sandbox argv is Linux-only. SANDBOX_BINDS is a tuple of absolute "
        "POSIX paths, and bubblewrap does not exist on Windows, so there is no "
        "OS bind for the command to carry and the assertion cannot pass. The "
        "harness only reaches this code on a Linux runner; a Windows sandbox "
        "would remove the skip."
    ),
)
def test_sandbox_binds_no_host_state(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sandbox must expose the scratch and the OS, never the operator.

    Binding the host's ``HOME`` would let a green run pass off state the release
    gate was supposed to prove nothing about. Binding the harness *in place* is
    the subtler version of the same mistake: bubblewrap materialises a
    destination's parents, so it rebuilds the operator's whole tree with the
    checkout at the bottom of it. Nothing under ``$HOME`` may appear at all.
    """
    home = tmp_path / "home-of-somebody"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    monkeypatch.setattr(verify_install.shutil, "which", lambda _: "/usr/bin/bwrap")

    command = verify_install.sandbox_command(_scratch(tmp_path), ["python3", "x.py"])

    assert command is not None
    sources = _bound_sources(command) + _bound_writes(command)
    assert "/usr" in sources
    assert [source for source in sources if str(home) in source] == []
    assert [source for source in sources if ".paperclip" in source] == []
    assert [source for source in sources if source.startswith(str(tmp_path))] == [
        str(_scratch(tmp_path))
    ]


def test_sandbox_keeps_the_network(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unsharing the network would prove a run fails offline, not one that works.

    PyPI resolution and the Realm call are the two things under test, so the net
    namespace has to stay the host's. ``--unshare-all`` is the trap: it reads
    like everything-isolated and quietly takes the network with it, so both that
    and the explicit flag are rejected rather than just the obvious one.
    """
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(verify_install.shutil, "which", lambda _: "/usr/bin/bwrap")

    command = verify_install.sandbox_command(_scratch(tmp_path), ["python3"])

    assert command is not None
    assert "--unshare-net" not in command
    assert "--unshare-all" not in command


def test_no_sandbox_is_reported_rather_than_assumed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A host without bwrap gets no sandbox, and that must be visible."""
    monkeypatch.setattr(verify_install.shutil, "which", lambda _: None)

    command = verify_install.sandbox_command(_scratch(tmp_path), ["python3"])

    assert command is None


def test_host_paths_reachable_spots_a_leaked_directory(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reachable host path is the one thing that voids the whole run."""
    present = tmp_path / "visible"
    present.mkdir()
    monkeypatch.setenv(
        verify_install.SANDBOX_HOST_PATHS,
        json.dumps([str(present), str(tmp_path / "hidden")]),
    )

    assert verify_install.host_paths_reachable() == [str(present)]


def test_host_paths_reachable_is_empty_outside_a_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(verify_install.SANDBOX_HOST_PATHS, raising=False)

    assert verify_install.host_paths_reachable() == []


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


def _coherent(version: str) -> dict[str, str]:
    return dict.fromkeys(verify_install.RELEASE_PACKAGES, version)


def test_a_coherent_tree_is_accepted() -> None:
    assert verify_install.lockstep_failures(_coherent("0.6.17"), "0.6.17") == []


def test_the_half_landed_release_is_detected() -> None:
    """The 2026-10-09 tree: six at 0.6.17, root at 0.6.16, gui never attempted.

    Every constraint `mvgeos 0.6.16` declared was satisfied by this tree --
    `mvgeos-cli>=0.6.16` against a 0.6.17 cli -- and `uvx mvgeos --help` exited
    zero on it. It is the shape the assertion exists to refuse.
    """
    resolved = _coherent("0.6.17")
    resolved["mvgeos"] = "0.6.16"
    del resolved["mvgeos-gui"]

    failures = verify_install.lockstep_failures(resolved, "0.6.17")

    assert len(failures) == 2
    assert any("mvgeos-gui" in failure for failure in failures)
    assert any("mvgeos 0.6.16" in failure for failure in failures)


def test_a_probe_that_ran_nothing_is_a_failure_not_a_pass() -> None:
    """An empty mapping is "the probe failed", not "nothing is wrong"."""
    failures = verify_install.lockstep_failures({}, "0.6.17")

    assert len(failures) == 1
    assert "probe returned nothing" in failures[0]


def test_a_missing_name_alone_is_enough_to_fail() -> None:
    resolved = _coherent("0.6.17")
    del resolved["mvgeos-tome"]

    failures = verify_install.lockstep_failures(resolved, "0.6.17")

    assert len(failures) == 1
    assert "mvgeos-tome" in failures[0]
