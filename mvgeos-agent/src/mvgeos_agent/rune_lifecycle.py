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
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from mvgeos_core.sandbox import MvgeSandbox
from mvgeos_provider.registry import RealmRegistry
from mvgeos_runes.loader import (
    load_runes_from_paths,
)
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    ResourcesDiscoverData,
    RuneContext,
    RuneScope,
    SigilHook,
)
from mvgeos_runes.watcher import RuneWatcher

from mvgeos_agent.environment import MvgeEnvironment

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
        global_dir: Path | None = None,
        reload_callback: Callable[[], Any] | None = None,
        extra_watch_dirs: Sequence[str | Path] = (),
    ) -> None:
        self._agent_name = agent_name
        self._api_key = api_key
        self._runes_paths: list[str | Path] = list(runes_paths)
        self._environment = environment
        self._provider_registry = provider_registry
        self._mode = mode
        self._cwd = cwd if cwd is not None else str(Path.cwd())
        self._global_dir = global_dir
        self._runner = runner
        # Watchers keyed by their canonical (resolved absolute) path: one
        # structure serves dedupe at start and per-watcher bookkeeping at
        # shutdown.
        self._watched: dict[str, RuneWatcher] = {}
        self._paths_with_scope: list[tuple[Path, RuneScope]] = []
        # Engine reload trigger: when set, watchers run in trigger mode and
        # call this (Mvge.reload) instead of reloading runes themselves.
        self._reload_callback = reload_callback
        self._extra_watch_dirs: list[Path] = [Path(d) for d in extra_watch_dirs]

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
        return list(self._watched.values())

    def resolve_paths(self) -> list[tuple[Path, RuneScope]]:
        """Resolve configured rune paths to (path, scope) pairs.

        Paths containing ``{agent_name}`` or pointing to
        ``agents/{agent_name}/extensions`` are agent-scoped; user-level
        ``~/.agents/extensions`` directories are user-scoped; everything else
        is project-scoped.
        """
        result: list[tuple[Path, RuneScope]] = []
        user_ext_posix = Path("~/.agents/extensions").expanduser().as_posix()
        for path in self._runes_paths:
            path_str = str(path)
            resolved = Path(
                path_str.replace("{agent_name}", self._agent_name)
            ).expanduser()
            posix_path = resolved.as_posix()
            if "{agent_name}" in path_str or (
                self._agent_name
                and (
                    f"agents/{self._agent_name}/extensions" in posix_path
                    or f".mvgeos/{self._agent_name}/runes" in posix_path
                )
            ):
                scope = RuneScope.AGENT
            elif (
                posix_path == user_ext_posix
                or "~/.agents/extensions" in path_str
                or ".mvgeos/runes" in posix_path
            ):
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

        # Dynamic Resource Discovery hook (SigilHook.RESOURCES_DISCOVER)
        res_data = ResourcesDiscoverData(cwd=self._cwd, reason="startup")
        await runner.emit_chain(SigilHook.RESOURCES_DISCOVER, res_data)

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
        observers. When a reload callback is set, every watcher runs in
        trigger mode: file events fire ``Mvge.reload()`` instead of
        reloading runes directly.
        """
        runner = self._ensure_runner()
        paths_with_scope = self._paths_with_scope or self.resolve_paths()
        for path, _scope in paths_with_scope:
            # Canonicalize to the resolved absolute path: the exists gate,
            # the watcher, and the dedupe key must all name the same
            # directory (a CWD-relative entry keeps its anchor; resolve()
            # only makes it absolute).
            key = str(Path(path).expanduser().resolve())
            if key in self._watched or not Path(key).exists():
                continue
            watcher = RuneWatcher(
                Path(key), runner, reload_callback=self._reload_callback
            )
            await watcher.start()
            self._watched[key] = watcher
        await self.watch_dirs(self._extra_watch_dirs)

    async def watch_dirs(self, dirs: Sequence[str | Path]) -> None:
        """Watch additional directories with the reload callback.

        No-op without a reload callback: extra trigger dirs are only
        meaningful for the engine reload. Already-watched and missing
        directories are skipped. Used after a reload to pick up trigger
        dirs that appeared since startup (e.g. a new spells directory).
        """
        if self._reload_callback is None:
            return
        runner = self._ensure_runner()
        for raw in dirs:
            key = str(Path(raw).expanduser().resolve())
            if key in self._watched or not Path(key).is_dir():
                continue
            watcher = RuneWatcher(
                Path(key), runner, reload_callback=self._reload_callback
            )
            await watcher.start()
            self._watched[key] = watcher

    async def shutdown(self) -> None:
        """Stop every watcher started by :meth:`start`.

        Not fail-fast: every watcher is attempted even when one raises.
        Watchers that stopped are dropped; failures are collected and
        raised together at the end. A watcher that failed to stop stays
        registered so a retry (the engine's retired-shutdown loop)
        attempts it again.
        """
        errors: list[str] = []
        remaining: dict[str, RuneWatcher] = {}
        for key, watcher in self._watched.items():
            try:
                await watcher.stop()
            except Exception as exc:
                errors.append(f"{key}: {exc}")
                remaining[key] = watcher
        self._watched = remaining
        if errors:
            raise RuntimeError(
                "rune watcher shutdown failed: " + "; ".join(errors)
            )

    def _ensure_runner(self) -> RuneRunner:
        if self._runner is None:
            self._runner = RuneRunner(sandbox_factory=MvgeSandbox)
            self._runner.bind_context(
                RuneContext(
                    cwd=self._cwd,
                    project_root=str(Path(self._cwd).resolve()),
                    mode=self._mode,
                    agent_name=self._agent_name,
                    api_key=self._api_key,
                )
            )
        return self._runner
