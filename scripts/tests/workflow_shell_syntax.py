"""Tests that every `run` block in a workflow is syntactically valid bash.

This is the sibling of `workflow_heredocs.py`, and it closes a gap this session
kept walking into. #212 broke the release toolchain with a Python
`IndentationError` inside a `run:` block, and `workflow_heredocs.py` now catches
that. But the block around it was shell, and nothing checked the shell either:
a re-indentation that loses an `if` or a `fi` is exactly as invisible to
`yaml.safe_load` as the Python error was, and it fails the same way -- on a
push to main, after the merge.

`bash -n` is the whole check. It reads and parses without executing, so it
catches unbalanced `if`/`fi`, unclosed quotes and heredocs, a `done` with no
`do`, and a step that was truncated mid-word. It cannot catch a wrong command or
a bad variable, and is not asked to.

On expressions. GitHub substitutes `${{ ... }}` into the script *before* the
shell sees it, so the bytes bash reads are not the bytes in the file. They are
replaced here with a plain word, which is what an expression like a version or a
runner name expands to. Checking the raw text instead would be checking a script
that never ran -- the same mistake, in the other direction, as reading a raw
heredoc instead of the yaml-stripped one.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

#: Shells a `run` block can name. Only bash is supported: no workflow here
#: overrides `shell:`, and a `shell: python` step checked with `bash -n` would
#: either fail for the wrong reason or pass for the wrong reason.
SUPPORTED_SHELLS = {None, "bash"}

#: A GitHub expression, replaced with a placeholder before parsing.
EXPRESSION = re.compile(r"\$\{\{[^}]*\}\}")


def _run_blocks() -> list[tuple[pathlib.Path, str, str, str, str | None]]:
    """Every `run` block as (workflow, job, step, script, shell)."""
    found: list[tuple[pathlib.Path, str, str, str, str | None]] = []
    for workflow in WORKFLOWS:
        document = yaml.safe_load(workflow.read_text())
        for job_name, job in (document.get("jobs") or {}).items():
            for index, step in enumerate(job.get("steps") or []):
                script = step.get("run")
                if not isinstance(script, str):
                    continue
                found.append(
                    (
                        workflow,
                        job_name,
                        step.get("name") or f"step {index}",
                        script,
                        step.get("shell"),
                    )
                )
    return found


def _bash_sees(script: str) -> str:
    """The script as the shell receives it: expressions already substituted."""
    return EXPRESSION.sub("__GITHUB_EXPRESSION__", script)


def test_the_workflow_files_are_where_this_test_expects() -> None:
    """A glob that matches nothing passes every other test here vacuously."""
    names = {workflow.name for workflow in WORKFLOWS}
    assert names == {"ci.yml", "publish.yml", "release.yml", "scorecard.yml"}


def test_at_least_one_run_block_was_found() -> None:
    """The glob has to match something for the check to be worth running."""
    assert _run_blocks(), (
        "no run block found in any workflow, which means this file checks "
        "nothing. Either every run block was removed or moved into a composite "
        "action, or the glob is wrong."
    )


def test_no_step_asks_for_a_shell_this_test_cannot_check() -> None:
    """`bash -n` on a `shell: python` step is wrong in one direction or the other.

    Left unhandled, adding such a step either fails this test for a reason that
    is not the step's fault, or -- worse -- gets its shell syntax checked as if
    it were bash. Failing loudly means the shell set stays a decision, not an
    accident.
    """
    unsupported = [
        (workflow.name, job_name, step_name, shell)
        for workflow, job_name, step_name, _script, shell in _run_blocks()
        if shell not in SUPPORTED_SHELLS
    ]
    assert not unsupported, (
        "these steps declare a shell this test does not check: "
        f"{unsupported}. Add support for it before adding the step, or the "
        "step goes unchecked."
    )


@pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="no bash on this runner; nothing here can be checked",
)
@pytest.mark.parametrize(
    ("workflow", "job_name", "step_name", "script", "_shell"),
    _run_blocks(),
    ids=lambda value: value.name if isinstance(value, pathlib.Path) else "",
)
def test_every_run_block_is_valid_bash(
    workflow: pathlib.Path,
    job_name: str,
    step_name: str,
    script: str,
    _shell: str | None,
) -> None:
    """A step that does not parse never starts, and looks like a logic failure.

    `bash -n` parses without executing, so this is safe to run in a test and
    catches the class of mistake a re-indentation introduces: an `if` that lost
    its `fi`, a quote that was not closed, a heredoc that was truncated. All of
    it is valid YAML.

    The script is written to stdin rather than to a file. A named file was the
    first version and it broke the windows job, because `tempfile` hands back
    `C:\\Users\\...` and the `bash` on a Windows runner -- Git Bash -- does not
    resolve that path, so it exits 1 with nothing on stderr. Via stdin there is
    no path to disagree about.
    """
    result = subprocess.run(
        ["bash", "-n"],
        input=_bash_sees(script),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"{workflow.name}: job {job_name!r}, step {step_name!r} is not valid "
        f"bash:\n{result.stderr.strip()}\nThis is YAML-valid, and the step fails "
        "only when the job runs."
    )
