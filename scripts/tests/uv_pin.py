"""Tests for the release toolchain pin.

Every workflow installs uv with `astral-sh/setup-uv@v7`, which without a
`version:` input installs whatever is newest that morning. That is a
reasonable default and the wrong one here, because uv writes its own version
into the ``Generator:`` line of every wheel it builds. A uv released between two
runs over the same commit therefore produces a different wheel, and
`uv publish --check-url` treats a same-name-different-bytes file as an error
rather than as something to skip. That is what stopped a re-dispatch from
resuming a release: the six packages already on PyPI were rebuilt at different
hashes and the run refused to move past the first of them.

The pin is what makes a rebuild byte-identical, so it is worth a test rather
than a code review convention. These read the workflow files as data; there is
no script to unit test, because the thing that can be wrong is a workflow
someone edits by hand.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

#: The version every workflow installs. `pyproject.toml` declares no
#: `required-version`, so this constant is the only place the answer lives.
PINNED_UV_VERSION = "0.12.24"

WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def _all_steps() -> list[tuple[pathlib.Path, str, dict]]:
    """Every setup-uv step in the repository as (workflow, job name, step)."""
    found: list[tuple[pathlib.Path, str, dict]] = []
    for workflow in WORKFLOWS:
        document = yaml.safe_load(workflow.read_text())
        for job_name, job in (document.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                if step.get("uses", "").startswith("astral-sh/setup-uv"):
                    found.append((workflow, job_name, step))
    return found


def test_the_workflow_files_are_where_this_test_expects() -> None:
    """A glob that matches nothing passes every other test here vacuously."""
    names = {workflow.name for workflow in WORKFLOWS}
    assert names == {"ci.yml", "publish.yml", "release.yml", "scorecard.yml"}


def test_every_workflow_that_installs_uv_was_found() -> None:
    """There is at least one pin to check, and it is in the release workflow."""
    workflows = {workflow.name for workflow, _, _ in _all_steps()}
    assert "publish.yml" in workflows


@pytest.mark.parametrize(
    ("workflow", "job_name", "step"),
    _all_steps(),
    ids=lambda value: value.name if isinstance(value, pathlib.Path) else "",
)
def test_setup_uv_step_pins_its_version(
    workflow: pathlib.Path, job_name: str, step: dict
) -> None:
    """An unpinned uv makes a rebuild of the same commit produce new bytes.

    uv stamps `Generator: uv <version>` into every wheel's `WHEEL` metadata,
    which changes the `RECORD` hash and therefore the wheel. `uv publish
    --check-url` skips a file already on the index only when the hash matches,
    so an unpinned build cannot resume a partial release: it stops on the first
    package that already landed.
    """
    assert (step.get("with") or {}).get("version") == PINNED_UV_VERSION, (
        f"{workflow.name}: job {job_name!r} installs uv without pinning it to "
        f"{PINNED_UV_VERSION}. Either a rebuild of the same commit will produce "
        "a different wheel than the one already on PyPI, or the pin has drifted "
        "from the version that built the published artifacts. Both break "
        "re-dispatching a release."
    )


@pytest.mark.parametrize(
    ("workflow", "job_name", "step"),
    _all_steps(),
    ids=lambda value: value.name if isinstance(value, pathlib.Path) else "",
)
def test_setup_uv_step_keeps_its_existing_inputs(
    workflow: pathlib.Path, job_name: str, step: dict
) -> None:
    """Adding a pin must not drop `enable-cache`, which the cache jobs set."""
    with_block = step.get("with") or {}
    assert "version" in with_block
    if workflow.name == "publish.yml" and job_name in {"verify", "verify-install"}:
        assert with_block.get("enable-cache") is False
