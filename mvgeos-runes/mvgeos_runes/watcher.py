from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from mvgeos_runes.loader import load_factory_from_manifest
from mvgeos_runes.manifest import load_manifest
from mvgeos_runes.rune_runner import RuneRunner

logger = logging.getLogger(__name__)


class _RuneReloadHandler(FileSystemEventHandler):
    def __init__(
        self,
        extensions_dir: Path,
        reload_callback: Any,
        debounce_seconds: float = 0.5,
    ) -> None:
        super().__init__()
        self._extensions_dir = extensions_dir
        self._callback = reload_callback
        self._debounce_seconds = debounce_seconds
        self._pending: set[str] = set()
        self._debounce_task: asyncio.Task[Any] | None = None

    def _schedule_reload(self, rune_name: str) -> None:
        self._pending.add(rune_name)

        async def _debounced() -> None:
            await asyncio.sleep(self._debounce_seconds)
            pending = self._pending.copy()
            self._pending.clear()
            for name in pending:
                try:
                    await self._callback(name)
                except Exception:
                    logger.exception("Failed to reload rune %s", name)

        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = asyncio.create_task(_debounced())

    def _find_rune_dir(self, path: str) -> str | None:
        src_path = Path(path)
        try:
            relative = src_path.relative_to(self._extensions_dir)
        except ValueError:
            return None
        parts = relative.parts
        if parts:
            return parts[0]
        return None

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        rune_name = self._find_rune_dir(str(event.src_path))
        if rune_name:
            self._schedule_reload(rune_name)

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        rune_name = self._find_rune_dir(str(event.src_path))
        if rune_name:
            self._schedule_reload(rune_name)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        rune_name = self._find_rune_dir(str(event.src_path))
        if rune_name:
            self._schedule_reload(rune_name)


class RuneWatcher:
    def __init__(self, extensions_dir: Path, runner: RuneRunner) -> None:
        self._extensions_dir = extensions_dir
        self._runner = runner
        self._observer: Any = None
        self._handler: _RuneReloadHandler | None = None

    async def _reload_rune(self, rune_name: str) -> None:
        rune_dir = self._extensions_dir / rune_name
        if not rune_dir.is_dir():
            logger.warning("Rune directory vanished: %s", rune_dir)
            return

        manifest = load_manifest(rune_dir)
        if manifest is None:
            logger.warning("Manifest invalid or missing after reload: %s", rune_dir)
            return

        factory = load_factory_from_manifest(manifest, rune_dir)
        if factory is None:
            logger.warning("Factory not found after reload: %s", rune_name)
            return

        for sc in manifest.shortcuts:
            self._runner.register_shortcut(sc)

        logger.info("Reloading rune: %s (%s)", rune_name, manifest.version)
        api = self._runner.create_api()
        result = factory(api)
        if isinstance(result, Awaitable):
            await result

    async def start(self) -> None:
        if self._observer is not None:
            return

        self._handler = _RuneReloadHandler(self._extensions_dir, self._reload_rune)
        self._observer = Observer()
        self._observer.schedule(
            self._handler, str(self._extensions_dir), recursive=True
        )
        self._observer.start()
        logger.info("Rune watcher started for %s", self._extensions_dir)

    async def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            self._handler = None
            logger.info("Rune watcher stopped")
