"""Standalone rune lifecycle for MvgeOS agents.

Single owner of the rune side of agent startup: resolves scoped discovery
paths, loads runes and skills into a RuneRunner, registers rune-provided
providers with the RealmRegistry, refreshes the environment's diagnostic
view, and manages hot-reload watchers.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Sequence
from pathlib import Path

from mvgeos_provider.registry import RealmRegistry
from mvgeos_runes.loader import (
    discover_plugin_skill_paths,
    get_default_skill_paths,
    load_runes_from_paths,
    load_skills_from_paths,
)
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    ResourcesDiscoverData,
    RuneContext,
    RuneScope,
    SigilHook,
    SkillScope,
)
from mvgeos_runes.watcher import RuneWatcher

from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.sandbox import MvgeSandbox

logger = logging.getLogger(__name__)


class RuneLifecycle:
    """Loads runes into a runner, starts watchers, and stops them again.

    Callers hand this module the agent name, API key, configured rune
    paths, the current environment, and the provider registry; they get
    back a fully loaded RuneRunner from :meth:`load`, hot-reload watchers
    from :meth:`start`, and a clean stop via :meth:`shutdown`.
    """

    def __init__(
        self,
        *,
        agent_name: str,
        api_key: str = "",
        runes_paths: Sequence[str | Path] = (),
        environment: MvgeEnvironment | None = None,
        provider_registry: RealmRegistry | None = None,
        runner: RuneRunner | None = None,
        cwd: str | None = None,
        mode: str = "cli",
    ) -> None:
        self._agent_name = agent_name
        self._api_key = api_key
        self._runes_paths: list[str | Path] = list(runes_paths)
        self._environment = environment
        self._provider_registry = provider_registry
        self._mode = mode
        self._cwd = cwd if cwd is not None else str(Path.cwd())
        self._runner = runner
        self._watchers: list[RuneWatcher] = []
        self._watched_paths: set[str] = set()
        self._paths_with_scope: list[tuple[Path, RuneScope]] = []

    @property
    def runner(self) -> RuneRunner | None:
        """The active RuneRunner, populated after :meth:`load`."""
        return self._runner

    @property
    def environment(self) -> MvgeEnvironment | None:
        """The environment passed in, refreshed with post-load diagnostics."""
        return self._environment

    @property
    def watchers(self) -> list[RuneWatcher]:
        return list(self._watchers)

    def resolve_paths(self) -> list[tuple[Path, RuneScope]]:
        """Resolve configured rune paths to (path, scope) pairs.

        Paths containing ``{agent_name}`` or pointing to ``.mvgeos/{agent_name}/runes``
        are agent-scoped; ``.mvgeos/runes`` directories are user-scoped;
        everything else is project-scoped.
        """
        result: list[tuple[Path, RuneScope]] = []
        for path in self._runes_paths:
            path_str = str(path)
            resolved = Path(
                path_str.replace("{agent_name}", self._agent_name)
            ).expanduser()
            posix_path = resolved.as_posix()
            if "{agent_name}" in path_str or (
                self._agent_name and f".mvgeos/{self._agent_name}/runes" in posix_path
            ):
                scope = RuneScope.AGENT
            elif ".mvgeos/runes" in posix_path:
                scope = RuneScope.USER
            else:
                scope = RuneScope.PROJECT
            result.append((resolved, scope))
        return result

    async def load(self) -> RuneRunner:
        """Load runes and skills from all scopes into the runner.

        Creates the RuneRunner on first call (binding the rune context),
        registers rune-declared providers with the provider registry,
        retains discovery diagnostics when nothing loads, and refreshes
        the injected environment with the combined diagnostics and the
        active runner.
        """
        paths_with_scope = self.resolve_paths()
        loads, diagnostics = await asyncio.to_thread(
            load_runes_from_paths, paths_with_scope, self._agent_name
        )
        runner = self._ensure_runner()

        if loads:
            await runner.load_rune_loads(loads, diagnostics)
            if self._provider_registry is not None:
                for pname, pconfig in runner.get_registered_providers().items():
                    if isinstance(pconfig, dict):
                        self._provider_registry.register_provider(pname, pconfig)
                for prefix, factory in runner.get_registered_realm_factories().items():
                    self._provider_registry.register_realm_factory(prefix, factory)
        elif diagnostics:
            runner.extend_diagnostics(diagnostics)

        skill_paths = list(get_default_skill_paths(self._agent_name))
        skill_paths.extend(discover_plugin_skill_paths(cwd=Path(self._cwd)))

        # Dynamic Resource Discovery hook (SigilHook.RESOURCES_DISCOVER)
        res_data = ResourcesDiscoverData(cwd=self._cwd, reason="startup")
        res_result = await runner.emit_chain(SigilHook.RESOURCES_DISCOVER, res_data)

        dynamic_paths: list[str | Path] = []
        if isinstance(res_result, ResourcesDiscoverData):
            dynamic_paths.extend(res_result.skill_paths)
        elif isinstance(res_result, dict):
            dynamic_paths.extend(res_result.get("skill_paths", []))
        dynamic_paths.extend(runner.get_registered_skill_paths())

        for dp in dynamic_paths:
            resolved_dp = Path(dp).expanduser().resolve()
            if resolved_dp.exists():
                if (resolved_dp / "SKILL.md").is_file():
                    skill_paths.append((resolved_dp.parent, SkillScope.PROJECT))
                else:
                    skill_paths.append((resolved_dp, SkillScope.PROJECT))

        skill_loads, skill_diagnostics = await asyncio.to_thread(
            load_skills_from_paths, skill_paths, self._agent_name
        )
        if skill_loads:
            runner.load_skills(skill_loads, diagnostics=skill_diagnostics)
        elif skill_diagnostics:
            runner.extend_skill_diagnostics(skill_diagnostics)

        for sdiag in skill_diagnostics:
            logger.warning(
                "Skill diagnostic: %s (skill=%s, scope=%s, path=%s)",
                sdiag.message,
                sdiag.skill_name,
                sdiag.scope.value if sdiag.scope else "unknown",
                sdiag.path,
            )

        self._paths_with_scope = paths_with_scope

        if self._environment is not None:
            self._environment = dataclasses.replace(
                self._environment,
                diagnostics=list(runner.diagnostics) + list(runner.skill_diagnostics),
                runner=runner,
            )
        return runner

    async def start(self) -> None:
        """Start hot-reload watchers for every existing rune path.

        May be called before :meth:`load`, in which case the configured
        rune paths are resolved on demand. Paths already being watched
        are skipped so repeated start calls never spawn duplicate
        observers.
        """
        runner = self._ensure_runner()
        paths_with_scope = self._paths_with_scope or self.resolve_paths()
        for path, _scope in paths_with_scope:
            if not path.exists() or str(path) in self._watched_paths:
                continue
            watcher = RuneWatcher(path, runner)
            await watcher.start()
            self._watchers.append(watcher)
            self._watched_paths.add(str(path))

    async def shutdown(self) -> None:
        """Stop every watcher started by :meth:`start`."""
        for watcher in self._watchers:
            await watcher.stop()
        self._watchers.clear()
        self._watched_paths.clear()

    def _ensure_runner(self) -> RuneRunner:
        if self._runner is None:
            self._runner = RuneRunner(sandbox_factory=MvgeSandbox)
            self._runner.bind_context(
                RuneContext(
                    cwd=self._cwd,
                    mode=self._mode,
                    agent_name=self._agent_name,
                    api_key=self._api_key,
                )
            )
        return self._runner
