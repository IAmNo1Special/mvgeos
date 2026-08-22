from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mvgeos_runes.loader import (
    get_default_skill_paths,
    load_runes_from_paths,
    load_skills_from_paths,
)
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import RuneContext, RuneScope

from mvgeos_agent.base_mvge import BaseMvge
from mvgeos_agent.rune_lifecycle import RuneLifecycle

_RUNE_PY = """
from mvgeos_runes.types import SpellDefinition


class EchoSpell(SpellDefinition):
    async def execute(self, spell_cast_id, params, signal=None, on_update=None):
        return {"status": "ok"}


def rune_factory(api):
    api.register_spell(EchoSpell(name="echo_spell", description="Echo"))
    api.register_command("echo-cmd", "Echo command")
    api.register_shortcut("ctrl-e", "Echo shortcut")
    api.register_provider("acme", {"baseUrl": "https://acme.test/v1"})
"""


@pytest.fixture
def runes_dir(tmp_path: Path) -> Path:
    root = tmp_path / "runes"
    rune_dir = root / "echo-rune"
    rune_dir.mkdir(parents=True)
    manifest = {
        "name": "echo-rune",
        "version": "1.0.0",
        "description": "Echo rune",
        "entry_point": "rune.py",
    }
    (rune_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (rune_dir / "rune.py").write_text(_RUNE_PY, encoding="utf-8")
    return root


async def _reference_inline_load(
    agent_name: str,
    api_key: str,
    runes_paths: list[Path],
    registry: Any,
) -> RuneRunner:
    """The pre-extraction inline BaseMvge._load_runes() logic, verbatim."""
    paths_with_scope = []
    for path in runes_paths:
        resolved = Path(str(path).replace("{agent_name}", agent_name)).expanduser()
        if ".mvgeos/runes" in str(path) and "{agent_name}" not in str(path):
            scope = RuneScope.USER
        elif "{agent_name}" in str(path):
            scope = RuneScope.AGENT
        else:
            scope = RuneScope.PROJECT
        paths_with_scope.append((resolved, scope))

    loads, diagnostics = load_runes_from_paths(paths_with_scope, agent_name)

    runner = RuneRunner()
    runner.bind_context(
        RuneContext(
            cwd=str(Path.cwd()),
            mode="cli",
            agent_name=agent_name,
            api_key=api_key,
        )
    )

    if loads:
        await runner.load_rune_loads(loads, diagnostics)
        for pname, pconfig in runner.get_registered_providers().items():
            registry.register_provider(pname, pconfig)
    elif diagnostics:
        runner.extend_diagnostics(diagnostics)

    skill_paths = get_default_skill_paths(agent_name)
    skill_loads, skill_diagnostics = load_skills_from_paths(skill_paths, agent_name)
    if skill_loads:
        runner.load_skills(skill_loads, diagnostics=skill_diagnostics)
    elif skill_diagnostics:
        runner.extend_skill_diagnostics(skill_diagnostics)

    return runner


def _runner_state(runner: RuneRunner) -> dict[str, Any]:
    return {
        "manifests": sorted(m.name for m in runner.loaded_manifests),
        "spells": sorted(s.name for s in runner.get_all_registered_spells()),
        "commands": [c.name for c in runner.get_commands()],
        "shortcuts": sorted(sc.key for sc in runner.get_shortcuts()),
        "providers": dict(sorted(runner.get_registered_providers().items())),
        "active_spells": runner.get_active_spells(),
        "skills": [s.name for s in runner.get_skills()],
        "skill_catalog": runner.get_skill_catalog(),
        "context": runner.context,
        "diagnostics": [
            (d.kind.value, d.rune_name, d.message) for d in runner.diagnostics
        ],
        "skill_diagnostics": [
            (d.kind.value, d.skill_name, d.message) for d in runner.skill_diagnostics
        ],
    }


@pytest.mark.asyncio
async def test_standalone_load_builds_full_runner(runes_dir: Path) -> None:
    class _Registry:
        def __init__(self) -> None:
            self.configs: dict[str, dict] = {}

        def register_provider(self, name: str, config: dict) -> None:
            self.configs[name] = config

    registry = _Registry()
    lifecycle = RuneLifecycle(
        agent_name="tester",
        api_key="key-1",
        runes_paths=[runes_dir],
        provider_registry=registry,
    )
    runner = await lifecycle.load()

    state = _runner_state(runner)
    assert state["manifests"] == ["echo-rune"]
    assert state["spells"] == ["echo_spell"]
    assert state["commands"] == ["echo-cmd"]
    assert state["shortcuts"] == ["ctrl-e"]
    assert state["providers"] == {"acme": {"baseUrl": "https://acme.test/v1"}}
    assert state["active_spells"] == ["echo_spell"]
    assert registry.configs == {"acme": {"baseUrl": "https://acme.test/v1"}}
    assert runner.context.agent_name == "tester"
    assert runner.context.api_key == "key-1"


@pytest.mark.asyncio
async def test_lifecycle_matches_reference_inline_semantics(runes_dir: Path) -> None:
    class _Registry:
        def register_provider(self, name: str, config: dict) -> None:
            pass

    reference = await _reference_inline_load(
        "tester", "key-1", [runes_dir], _Registry()
    )

    lifecycle = RuneLifecycle(
        agent_name="tester",
        api_key="key-1",
        runes_paths=[runes_dir],
    )
    loaded = await lifecycle.load()

    assert _runner_state(loaded) == _runner_state(reference)


@pytest.mark.asyncio
async def test_base_mvge_load_matches_standalone_lifecycle(runes_dir: Path) -> None:
    agent = BaseMvge(api_key="key-2", runes_paths=[str(runes_dir)])
    lifecycle = RuneLifecycle(
        agent_name=agent.environment.agent_name,
        api_key="key-2",
        runes_paths=[runes_dir],
    )
    standalone = await lifecycle.load()
    try:
        await agent._load_runes()

        assert agent.runner is not None
        assert _runner_state(agent.runner) == _runner_state(standalone)
        assert agent._rune_lifecycle is not None
        assert agent.environment.diagnostics == agent.diagnostics
        assert len(lifecycle.watchers) == 0

        started = agent._rune_lifecycle.watchers
        assert len(started) == 1
    finally:
        await agent.close()


@pytest.mark.asyncio
async def test_base_mvge_close_stops_watchers(runes_dir: Path) -> None:
    agent = BaseMvge(api_key="key-3", runes_paths=[str(runes_dir)])
    await agent._load_runes()

    lifecycle = agent._rune_lifecycle
    assert lifecycle is not None
    assert len(lifecycle.watchers) == 1

    await agent.close()

    assert lifecycle.watchers == []
    assert agent._rune_lifecycle is None
    assert agent.runner is None


@pytest.mark.asyncio
async def test_standalone_watchers_start_and_stop(runes_dir: Path) -> None:
    empty_root = runes_dir.parent / "empty"
    empty_root.mkdir()
    missing = runes_dir.parent / "missing"

    lifecycle = RuneLifecycle(
        agent_name="watcher-agent",
        runes_paths=[str(runes_dir), str(missing)],
    )
    await lifecycle.load()
    await lifecycle.start()

    assert len(lifecycle.watchers) == 1

    await lifecycle.shutdown()
    assert lifecycle.watchers == []

    await lifecycle.shutdown()
