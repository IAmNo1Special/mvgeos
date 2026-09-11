from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mvgeos_provider.registry import RealmRegistry
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    Diagnostic,
    DiagnosticKind,
    RuneContext,
    RuneLoad,
    RuneManifest,
    RuneScope,
    RuneShortcut,
    SkillDiagnostic,
    SkillDiagnosticKind,
    SkillLoad,
    SkillManifest,
    SkillScope,
)

from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.rune_lifecycle import RuneLifecycle


def _manifest(name: str = "acme", **kwargs: Any) -> RuneManifest:
    defaults: dict[str, Any] = {
        "version": "1.0.0",
        "description": f"{name} rune",
        "shortcuts": [RuneShortcut(key="ctrl+a", description="acme")],
    }
    defaults.update(kwargs)
    return RuneManifest(name=name, **defaults)


def _diag(name: str = "broken") -> Diagnostic:
    return Diagnostic(
        kind=DiagnosticKind.LOAD_FAILURE,
        rune_name=name,
        message="failed to load",
        scope=RuneScope.USER,
        path="/tmp/runes",
    )


def _skill_diag() -> SkillDiagnostic:
    return SkillDiagnostic(
        kind=SkillDiagnosticKind.PARSE_WARNING,
        skill_name="bad-skill",
        message="could not parse skill manifest",
        scope=SkillScope.PROJECT,
        path="/tmp/skills/bad-skill",
    )


def _skill_load(name: str = "good-skill") -> SkillLoad:
    return SkillLoad(
        manifest=SkillManifest(
            name=name,
            description=f"{name} skill",
            scope=SkillScope.PROJECT,
            path=f"/tmp/skills/{name}",
        )
    )


class TestResolvePaths:
    def test_agent_placeholder_maps_to_agent_scope(self) -> None:
        lifecycle = RuneLifecycle(
            agent_name="coder",
            runes_paths=["~/.agents/.mvgeos/{agent_name}/runes"],
        )

        result = lifecycle.resolve_paths()

        expected = Path("~/.agents/.mvgeos/coder/runes").expanduser()
        assert result == [(expected, RuneScope.AGENT)]

    def test_global_mvgeos_dir_maps_to_user_scope(self) -> None:
        lifecycle = RuneLifecycle(
            agent_name="coder",
            runes_paths=["~/.agents/.mvgeos/runes"],
        )

        result = lifecycle.resolve_paths()

        expected = Path("~/.agents/.mvgeos/runes").expanduser()
        assert result == [(expected, RuneScope.USER)]

    def test_custom_dir_maps_to_project_scope(self) -> None:
        lifecycle = RuneLifecycle(
            agent_name="coder",
            runes_paths=["extensions/runes"],
        )

        result = lifecycle.resolve_paths()

        assert result == [(Path("extensions/runes"), RuneScope.PROJECT)]

    def test_order_is_preserved(self) -> None:
        paths = [
            "extensions/runes",
            "~/.agents/.mvgeos/runes",
            "~/.agents/.mvgeos/{agent_name}/runes",
        ]
        lifecycle = RuneLifecycle(agent_name="coder", runes_paths=paths)

        result = lifecycle.resolve_paths()
        scopes = [scope for _, scope in result]

        assert scopes == [RuneScope.PROJECT, RuneScope.USER, RuneScope.AGENT]

    def test_already_resolved_agent_path_maps_to_agent_scope(self) -> None:
        lifecycle = RuneLifecycle(
            agent_name="coder",
            runes_paths=["~/.agents/.mvgeos/coder/runes"],
        )
        result = lifecycle.resolve_paths()
        expected = Path("~/.agents/.mvgeos/coder/runes").expanduser()
        assert result == [(expected, RuneScope.AGENT)]


class TestLoad:
    @pytest.mark.asyncio
    async def test_load_returns_runner_with_bound_context(self) -> None:
        lifecycle = RuneLifecycle(
            agent_name="tester",
            api_key="secret",
            cwd="/proj",
            mode="cli",
        )

        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=([], []),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            runner = await lifecycle.load()

        assert isinstance(runner, RuneRunner)
        assert lifecycle.runner is runner
        assert runner.context == RuneContext(
            cwd="/proj",
            mode="cli",
            agent_name="tester",
            api_key="secret",
        )

    @pytest.mark.asyncio
    async def test_load_reuses_existing_runner(self) -> None:
        existing = RuneRunner()
        lifecycle = RuneLifecycle(agent_name="tester", runner=existing)

        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=([], []),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            runner = await lifecycle.load()

        assert runner is existing

    @pytest.mark.asyncio
    async def test_second_load_reuses_same_runner(self) -> None:
        lifecycle = RuneLifecycle(agent_name="tester")

        empty: tuple[list[Any], list[Any]] = ([], [])
        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=empty,
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=empty,
            ),
        ):
            first = await lifecycle.load()
            second = await lifecycle.load()

        assert first is second

    @pytest.mark.asyncio
    async def test_load_registers_manifest_shortcuts(self) -> None:
        loads = [RuneLoad(manifest=_manifest())]
        lifecycle = RuneLifecycle(agent_name="tester")

        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=(loads, []),
            ) as mock_load,
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            runner = await lifecycle.load()

        mock_load.assert_called_once_with(lifecycle.resolve_paths(), "tester")
        assert [m.name for m in runner.loaded_manifests] == ["acme"]
        assert [sc.key for sc in runner.get_shortcuts()] == ["ctrl+a"]

    @pytest.mark.asyncio
    async def test_load_retains_diagnostics_without_loads(self) -> None:
        diag = _diag()
        lifecycle = RuneLifecycle(agent_name="tester")

        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=([], [diag]),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            runner = await lifecycle.load()

        assert runner.diagnostics == [diag]

    @pytest.mark.asyncio
    async def test_load_registers_providers_into_registry(self) -> None:
        def factory(api: Any) -> None:
            api.register_provider("acme", {"baseUrl": "https://acme.test"})

        loads = [RuneLoad(manifest=_manifest(), factory=factory)]
        registry = MagicMock(spec=RealmRegistry)
        lifecycle = RuneLifecycle(agent_name="tester", provider_registry=registry)

        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=(loads, []),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            await lifecycle.load()

        registry.register_provider.assert_called_once_with(
            "acme", {"baseUrl": "https://acme.test"}
        )

    @pytest.mark.asyncio
    async def test_load_without_registry_skips_provider_registration(self) -> None:
        def factory(api: Any) -> None:
            api.register_provider("acme", {"baseUrl": "https://acme.test"})

        loads = [RuneLoad(manifest=_manifest(), factory=factory)]
        lifecycle = RuneLifecycle(agent_name="tester")

        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=(loads, []),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            await lifecycle.load()

    @pytest.mark.asyncio
    async def test_load_skills_via_default_paths(self) -> None:
        skill_paths = [(Path("/skills"), SkillScope.USER)]
        lifecycle = RuneLifecycle(agent_name="tester")

        empty: tuple[list[Any], list[Any]] = ([], [])
        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=empty,
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.get_default_skill_paths",
                return_value=skill_paths,
            ) as mock_paths,
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([_skill_load()], []),
            ) as mock_load_skills,
        ):
            runner = await lifecycle.load()

        mock_paths.assert_called_once_with("tester")
        mock_load_skills.assert_called_once_with(skill_paths, "tester")
        assert [s.name for s in runner.get_skills()] == ["good-skill"]

    @pytest.mark.asyncio
    async def test_load_retains_skill_diagnostics_without_loads(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        sdiag = _skill_diag()
        lifecycle = RuneLifecycle(agent_name="tester")

        empty: tuple[list[Any], list[Any]] = ([], [])
        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=empty,
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], [sdiag]),
            ),
            caplog.at_level(logging.DEBUG, logger="mvgeos_agent.rune_lifecycle"),
        ):
            runner = await lifecycle.load()

        assert runner.skill_diagnostics == [sdiag]
        # Individual diagnostic now logged at DEBUG
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.DEBUG
        assert "bad-skill" in caplog.records[0].message

    @pytest.mark.asyncio
    async def test_load_skills_scope_order_dedupe(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Skills with same name in different scopes: highest scope wins."""
        # Create skill directories with same name in different scopes
        user_skills = tmp_path / "user_skills"
        agent_skills = tmp_path / "agent_skills"
        user_skills.mkdir()
        agent_skills.mkdir()

        # USER scope skill (higher precedence in SKILL_SCOPES order)
        user_skill_dir = user_skills / "duplicate-skill"
        user_skill_dir.mkdir()
        md_user = (
            "---\nname: duplicate-skill\n"
            "description: user scope skill\nversion: 1.0.0\n---\n"
        )
        (user_skill_dir / "SKILL.md").write_text(md_user)

        # AGENT scope skill (lower precedence)
        agent_skill_dir = agent_skills / "duplicate-skill"
        agent_skill_dir.mkdir()
        md_agent = (
            "---\nname: duplicate-skill\n"
            "description: agent scope skill\nversion: 1.0.0\n---\n"
        )
        (agent_skill_dir / "SKILL.md").write_text(md_agent)

        # Paths in precedence order: USER first, then AGENT
        paths = [
            (str(user_skills), SkillScope.USER),
            (str(agent_skills), SkillScope.AGENT),
        ]

        lifecycle = RuneLifecycle(agent_name="tester")

        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=([], []),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.get_default_skill_paths",
                return_value=paths,
            ),
            caplog.at_level(logging.DEBUG, logger="mvgeos_agent.rune_lifecycle"),
            caplog.at_level(logging.DEBUG, logger="mvgeos_runes.loader"),
        ):
            runner = await lifecycle.load()

        # Verify dedupe logic: only 1 skill loaded (USER scope wins)
        skills = runner.get_skills()
        assert len(skills) == 1
        assert skills[0].name == "duplicate-skill"
        assert skills[0].scope == SkillScope.USER

        # Verify individual shadow diagnostic was logged at DEBUG level
        shadow_logs = [
            r
            for r in caplog.records
            if "shadowed" in r.message.lower() and r.levelno == logging.DEBUG
        ]
        assert len(shadow_logs) == 1

        # Verify summary warning with count
        summary_logs = [
            r
            for r in caplog.records
            if "shadows (user-scope takes precedence)" in r.message
        ]
        assert len(summary_logs) == 1
        assert summary_logs[0].levelno == logging.WARNING
        assert "1 shadows" in summary_logs[0].message

    @pytest.mark.asyncio
    async def test_environment_refreshed_after_load(self, tmp_path: Path) -> None:
        environment = MvgeEnvironment.resolve(
            "tester",
            project_dir=tmp_path,
            config_dir=tmp_path / "agent_config",
        )
        diag = _diag()
        sdiag = _skill_diag()
        lifecycle = RuneLifecycle(
            agent_name="tester",
            environment=environment,
        )

        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=([], [diag]),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], [sdiag]),
            ),
        ):
            runner = await lifecycle.load()

        refreshed = lifecycle.environment
        assert refreshed is not environment
        assert refreshed is not None
        assert refreshed.runner is runner
        assert refreshed.diagnostics == runner.diagnostics + runner.skill_diagnostics


def _watcher_factory(
    log: list[MagicMock],
) -> Callable[..., MagicMock]:
    def _make(*args: Any) -> MagicMock:
        watcher = MagicMock(start=AsyncMock(), stop=AsyncMock())
        log.append(watcher)
        return watcher

    return _make


class TestStartAndShutdown:
    @pytest.mark.asyncio
    async def test_start_creates_watchers_for_existing_paths_only(
        self, tmp_path: Path
    ) -> None:
        runes_dir = tmp_path / "runes"
        runes_dir.mkdir()
        missing = tmp_path / "missing"
        lifecycle = RuneLifecycle(
            agent_name="tester",
            runes_paths=[str(runes_dir), str(missing)],
        )
        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=([], []),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            await lifecycle.load()

        created: list[MagicMock] = []
        with patch(
            "mvgeos_agent.rune_lifecycle.RuneWatcher",
            side_effect=_watcher_factory(created),
        ):
            await lifecycle.start()

        assert len(created) == 1
        created[0].start.assert_awaited_once()
        assert lifecycle.watchers == created

    @pytest.mark.asyncio
    async def test_start_passes_resolved_path_and_runner(self, tmp_path: Path) -> None:
        runes_dir = tmp_path / "runes"
        runes_dir.mkdir()
        lifecycle = RuneLifecycle(agent_name="tester", runes_paths=[str(runes_dir)])
        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=([], []),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            runner = await lifecycle.load()

        created: list[MagicMock] = []
        with patch(
            "mvgeos_agent.rune_lifecycle.RuneWatcher",
            side_effect=_watcher_factory(created),
        ) as watcher_cls:
            await lifecycle.start()

        watcher_cls.assert_called_once_with(runes_dir, runner)

    @pytest.mark.asyncio
    async def test_start_skips_already_watched_paths(self, tmp_path: Path) -> None:
        runes_dir = tmp_path / "runes"
        runes_dir.mkdir()
        lifecycle = RuneLifecycle(agent_name="tester", runes_paths=[str(runes_dir)])
        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=([], []),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            await lifecycle.load()

        created: list[MagicMock] = []
        with patch(
            "mvgeos_agent.rune_lifecycle.RuneWatcher",
            side_effect=_watcher_factory(created),
        ) as watcher_cls:
            await lifecycle.start()
            await lifecycle.start()

        assert watcher_cls.call_count == 1
        assert len(lifecycle.watchers) == 1

    @pytest.mark.asyncio
    async def test_start_before_load_resolves_configured_paths(
        self, tmp_path: Path
    ) -> None:
        runes_dir = tmp_path / "runes"
        runes_dir.mkdir()
        lifecycle = RuneLifecycle(agent_name="tester", runes_paths=[str(runes_dir)])

        created: list[MagicMock] = []
        with patch(
            "mvgeos_agent.rune_lifecycle.RuneWatcher",
            side_effect=_watcher_factory(created),
        ):
            await lifecycle.start()

        assert len(created) == 1
        created[0].start.assert_awaited_once()
        assert lifecycle.runner is not None
        assert lifecycle.watchers == created

    @pytest.mark.asyncio
    async def test_shutdown_stops_all_watchers_and_clears(self, tmp_path: Path) -> None:
        runes_dir = tmp_path / "runes"
        runes_dir.mkdir()
        lifecycle = RuneLifecycle(agent_name="tester", runes_paths=[str(runes_dir)])
        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=([], []),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            await lifecycle.load()

        created: list[MagicMock] = []
        with patch(
            "mvgeos_agent.rune_lifecycle.RuneWatcher",
            side_effect=_watcher_factory(created),
        ):
            await lifecycle.start()

        await lifecycle.shutdown()

        created[0].stop.assert_awaited_once()
        assert lifecycle.watchers == []

    @pytest.mark.asyncio
    async def test_restart_after_shutdown(self, tmp_path: Path) -> None:
        runes_dir = tmp_path / "runes"
        runes_dir.mkdir()
        lifecycle = RuneLifecycle(agent_name="tester", runes_paths=[str(runes_dir)])
        with (
            patch(
                "mvgeos_agent.rune_lifecycle.load_runes_from_paths",
                return_value=([], []),
            ),
            patch(
                "mvgeos_agent.rune_lifecycle.load_skills_from_paths",
                return_value=([], []),
            ),
        ):
            await lifecycle.load()

        created: list[MagicMock] = []
        with patch(
            "mvgeos_agent.rune_lifecycle.RuneWatcher",
            side_effect=_watcher_factory(created),
        ):
            await lifecycle.start()
            await lifecycle.shutdown()
            await lifecycle.start()

        assert len(created) == 2
        assert lifecycle.watchers == [created[1]]

    @pytest.mark.asyncio
    async def test_shutdown_without_watchers_is_noop(self) -> None:
        lifecycle = RuneLifecycle(agent_name="tester")

        await lifecycle.shutdown()

        assert lifecycle.watchers == []
