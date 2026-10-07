"""Prove the published distribution is usable by someone who has never seen it.

`publish.yml` already runs `uvx mvgeos --help` from a checkout-free runner, which
proves the name resolves and the console script exists. It proves nothing about
whether the thing then *works*: a package whose Realm Rune is missing, whose
credential never loads, or whose Tome never reaches disk all sail past `--help`
and fail on a stranger's first real task. This harness runs that first real
task and asserts on the three things a Summoner would notice:

1. `uvx mvgeos --help` exits zero.
2. The task produces its artifact, byte for byte.
3. A session Tome lands in ``$HOME/.agents/sessions/`` naming the model that
   served it, and records the Spell that was cast.

"Cold" here is precise, and the distinction matters. The scratch ``HOME`` starts
empty apart from the credential, and the uv cache is a fresh directory, so the
measured install is a real download rather than a cache hit. The process is a
fresh user account, not a fresh container: the kernel and ``PATH`` are the
host's. That is a weaker claim than "clean machine" and the report says so
rather than rounding up.

Usage:
    python scripts/verify_install.py --version 0.6.14
    OPENROUTER_API_KEY=sk-or-... python scripts/verify_install.py --version 0.6.14

The credential is read from ``OPENROUTER_API_KEY`` and written into the scratch
``HOME`` the way a Summoner would, so the run exercises the real key-resolution
path rather than being handed ``--api-key``.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

# The cheapest tool-capable model in the registry, so a release gate costs a
# fraction of a cent instead of a decision about budget. Overridable because a
# flaky upstream model is not a packaging failure and should not read as one.
DEFAULT_MODEL = "openai/gpt-4o-mini"

# The Realm Rune and the Mvge a Summoner installs before their first task, named
# exactly as the README names them.
REALM_RUNE = "openrouter-realm"
MVGE = "coding_mvge"

# OpenRouter rejects a request whose declared ``max_tokens`` exceeds what the
# key's remaining credit can cover, and it rejects it *before* any tokens are
# spent. The engine's default is 4096, which is more than a nearly-exhausted
# key can offer, so the gate would fail on the account's budget rather than on
# the packaging it exists to check. This task needs a fraction of it.
MAX_TOKENS = 2000

# The artifact the task is asked to produce, and what it must contain.
ARTIFACT = "hello.txt"
ARTIFACT_CONTENT = "hello from mvgeos"

TASK = f"Create a file named {ARTIFACT} containing exactly the text: {ARTIFACT_CONTENT}"

# Lines the CLI prints about itself before the model says anything. They are
# local diagnostics, so counting one as the first token would understate the
# time-to-first-token by however long Realm setup took -- which is most of it.
LOCAL_PREAMBLE = re.compile(r"^(WARNING|Error)\s*:", re.IGNORECASE)


def clean_env(home: pathlib.Path, cache: pathlib.Path, api_key: str) -> dict[str, str]:
    """Return an environment that cannot see the machine running the harness.

    Built from nothing rather than filtered from ``os.environ``. A filter has to
    enumerate every variable that could leak state, and forgetting one silently
    turns "a stranger's machine" into "this machine, wearing a hat".
    """
    return {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "UV_CACHE_DIR": str(cache),
        "UV_NO_CONFIG": "1",
        "OPENROUTER_API_KEY": api_key,
        # Rich reflows to the console width, and a wrapped preamble stops
        # looking like a preamble: `--approval-mode` prints one WARNING line at
        # 80 columns and two at 80 if it overflows, so the second half no longer
        # starts with "WARNING:" and reads as model output. Pinning a width wide
        # enough for the CLI's own diagnostics keeps one message on one line,
        # which is what makes the stream machine-readable at all.
        "COLUMNS": "400",
    }


def is_model_output(line: str) -> bool:
    """Whether a line of stdout came from the model rather than the CLI.

    The first non-preamble line is the channeling the task asked to measure, so
    an empty line or a local ``WARNING:`` must not claim the timestamp.
    """
    stripped = line.strip()
    if not stripped:
        return False
    return LOCAL_PREAMBLE.match(stripped) is None


def newest_tome(sessions: pathlib.Path) -> pathlib.Path | None:
    """The most recently written session JSONL, or ``None`` when none exists."""
    if not sessions.is_dir():
        return None
    tomes = [p for p in sessions.glob("*.jsonl") if p.is_file()]
    if not tomes:
        return None
    return max(tomes, key=lambda p: p.stat().st_mtime)


def session_header(tome: pathlib.Path) -> dict[str, Any] | None:
    """The Tome's ``session`` record, which names the model that served it."""
    with tome.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") == "session":
                return entry
    return None


def cast_spells(tome: pathlib.Path) -> list[str]:
    """Names of the Spells the Tome records as cast.

    A Tome with no Spell cast means the model answered from memory and never
    touched the filesystem, so the artifact cannot be attributed to the run.
    """
    cast: list[str] = []
    with tome.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = entry.get("payload") or {}
            for block in payload.get("content") or []:
                if not isinstance(block, dict):
                    continue
                call = block.get("spell_cast") or {}
                name = call.get("name")
                if isinstance(name, str) and name not in cast:
                    cast.append(name)
    return cast


def run_uvx(
    version: str,
    env: dict[str, str],
    args: list[str],
    *,
    cwd: pathlib.Path,
) -> tuple[int, str, float]:
    """Run ``uvx --from mvgeos==VERSION mvgeos ...`` under ``env``.

    Returns the exit code, the combined output, and the elapsed seconds.
    """
    command = ["uvx", "--from", f"mvgeos=={version}", "mvgeos", *args]
    started = time.monotonic()
    process = subprocess.run(
        command,
        env=scrubbed(env),
        cwd=cwd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    elapsed = time.monotonic() - started
    return process.returncode, process.stdout + process.stderr, elapsed


def scrubbed(env: dict[str, str]) -> dict[str, str]:
    """The child environment, minus the private ``_``-prefixed carrier keys."""
    return {k: v for k, v in env.items() if not k.startswith("_")}


def stamp_lines(lines: list[tuple[float, str]]) -> str:
    """Render ``(elapsed, text)`` pairs as the timestamped transcript.

    Every line keeps the moment it actually arrived. An earlier version stamped
    only the first of several and printed 0.00s for the rest, which makes a real
    gap look like simultaneity -- the one thing a timing report must not do.
    """
    return "\n".join(f"[{elapsed:7.2f}s] {text}" for elapsed, text in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="released version to test")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="model slug to run")
    parser.add_argument(
        "--provider",
        default="openrouter",
        help="Realm to force; the slug alone derives one from its prefix",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=MAX_TOKENS,
        help="cap the model's declared budget; keeps the gate off the key's limit",
    )
    parser.add_argument(
        "--help-only",
        action="store_true",
        help="prove resolution only, skipping the paid task",
    )
    parser.add_argument("--keep", action="store_true", help="keep the scratch HOME")
    arguments = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print(
            "verify_install failed: OPENROUTER_API_KEY is not set. Without a "
            "credential there is no first real task to run, and a green gate "
            "that never called a model would be a lie.",
            file=sys.stderr,
        )
        return 2

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="mvgeos-verify-"))
    home = scratch / "home"
    cache = scratch / "cache"
    work = scratch / "work"
    for directory in (home / ".agents" / "auth", cache, work):
        directory.mkdir(parents=True, exist_ok=True)

    # Seed only the credential. A Summoner types it; the Rune and the Mvge are
    # installed by the run below, so that path is exercised too.
    (home / ".agents" / "auth" / "openrouter.json").write_text(
        json.dumps({"api_key": api_key}), encoding="utf-8"
    )
    env = clean_env(home, cache, api_key)
    version = arguments.version

    failures: list[str] = []
    stamps: list[float] = []
    try:
        print(f"verify_install: mvgeos=={version} on a scratch HOME")
        print(f"  HOME   {home}")
        print(f"  cache  {cache} (empty: the install below is a real download)")

        code, output, elapsed = run_uvx(version, env, ["--help"], cwd=work)
        print(f"\n[1/4] uvx mvgeos --help -> exit {code} in {elapsed:.2f}s")
        if code != 0:
            failures.append(f"`--help` exited {code}")
            print(output[-2000:])

        if arguments.help_only:
            for failure in failures:
                print(f"verify_install failed: {failure}", file=sys.stderr)
            return 1 if failures else 0

        code, output, _ = run_uvx(
            version,
            env,
            ["rune", "install", REALM_RUNE, "--confirm-python-deps"],
            cwd=work,
        )
        print(f"[2/4] rune install {REALM_RUNE} -> exit {code}")
        if code != 0:
            failures.append(f"`rune install {REALM_RUNE}` exited {code}")
            print(output[-2000:])

        code, output, _ = run_uvx(
            version,
            env,
            ["mvge", "install", "--confirm-python-deps", MVGE],
            cwd=work,
        )
        print(f"[3/4] mvge install {MVGE} -> exit {code}")
        if code != 0:
            failures.append(f"`mvge install {MVGE}` exited {code}")
            print(output[-2000:])

        task_args = [
            "--agent-name",
            MVGE,
            "--model",
            arguments.model,
            "--provider",
            arguments.provider,
            "--approval-mode",
            "allow-all",
            "--max-tokens",
            str(arguments.max_tokens),
            TASK,
        ]
        started = time.monotonic()
        process = subprocess.Popen(
            [
                "uvx",
                "--from",
                f"mvgeos=={version}",
                "mvgeos",
                *task_args,
            ],
            env=scrubbed(env),
            cwd=work,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        lines: list[tuple[float, str]] = []
        assert process.stdout is not None
        for line in process.stdout:
            elapsed = time.monotonic() - started
            text = line.rstrip("\n")
            if text.strip() and is_model_output(text) and not stamps:
                stamps.append(elapsed)
            lines.append((elapsed, text))
        code = process.wait()
        total = time.monotonic() - started

        print(f"[4/4] real task -> exit {code} in {total:.2f}s")
        print(stamp_lines(lines))
        if code != 0:
            failures.append(f"the task exited {code}")

        artifact = work / ARTIFACT
        if not artifact.is_file():
            failures.append(f"{ARTIFACT} was never created")
        elif artifact.read_text(encoding="utf-8") != ARTIFACT_CONTENT:
            failures.append(f"{ARTIFACT} does not contain the requested text")

        tome = newest_tome(home / ".agents" / "sessions")
        if tome is None:
            failures.append("no session Tome was persisted")
        else:
            header = session_header(tome)
            if header is None:
                failures.append(f"{tome.name} has no session header")
            elif header.get("model") != arguments.model:
                failures.append(
                    f"Tome names model {header.get('model')!r}, expected "
                    f"{arguments.model!r}"
                )
            spells = cast_spells(tome)
            if not spells:
                failures.append(f"{tome.name} records no Spell cast")
            else:
                print(f"\ntome   {tome.name} ({tome.stat().st_size} bytes)")
                print(f"model  {header.get('model') if header else None}")
                print(f"spells {', '.join(spells)}")
    finally:
        if arguments.keep:
            print(f"\nscratch kept at {scratch}")
        else:
            shutil.rmtree(scratch, ignore_errors=True)

    print()
    if stamps:
        print(f"cold to first token: {stamps[0]:.2f}s")
    if failures:
        for failure in failures:
            print(f"verify_install failed: {failure}", file=sys.stderr)
        return 1
    print("verify_install ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
