from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import cast

from mvgeos_runes.manifest import load_manifest
from mvgeos_runes.rune_api import RuneFactory
from mvgeos_runes.types import RuneManifest


class RuneLoader:
    def __init__(self, extensions_dir: Path) -> None:
        self._extensions_dir = extensions_dir

    def load_all(self) -> list[RuneManifest]:
        if not self._extensions_dir.exists():
            return []
        manifests: list[RuneManifest] = []
        for entry in self._extensions_dir.iterdir():
            if entry.is_dir():
                manifest = load_manifest(entry)
                if manifest is not None:
                    manifests.append(manifest)
        return manifests

    def load_factories(self) -> list[RuneFactory]:
        return load_factories(self._extensions_dir)


def load_factory_from_manifest(
    manifest: RuneManifest,
    rune_dir: Path,
) -> RuneFactory | None:
    if not manifest.entry_point:
        return None
    entry = (rune_dir / manifest.entry_point).resolve()
    if not entry.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        f"mvgeos_rune_{manifest.name}", str(entry)
    )
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    factory = getattr(mod, "rune_factory", None)
    if factory is None:
        return None
    return cast(RuneFactory, factory)


def load_factories(extensions_dir: Path) -> list[RuneFactory]:
    if not extensions_dir.exists():
        return []
    factories: list[RuneFactory] = []
    for entry in extensions_dir.iterdir():
        if not entry.is_dir():
            continue
        manifest = load_manifest(entry)
        if manifest is None:
            continue
        factory = load_factory_from_manifest(manifest, entry)
        if factory is not None:
            factories.append(factory)
    return factories


def load_manifests(extensions_dir: Path) -> list[RuneManifest]:
    if not extensions_dir.exists():
        return []
    manifests: list[RuneManifest] = []
    for entry in extensions_dir.iterdir():
        if not entry.is_dir():
            continue
        manifest = load_manifest(entry)
        if manifest is not None:
            manifests.append(manifest)
    return manifests
