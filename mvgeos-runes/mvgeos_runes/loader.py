from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from mvgeos_runes.manifest import load_manifest
from mvgeos_runes.rune_api import RuneFactory
from mvgeos_runes.types import (
    Diagnostic,
    DiagnosticKind,
    RuneLoad,
    RuneManifest,
    RuneScope,
)


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
                if manifest is not None and manifest.enabled:
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
        if manifest is None or not manifest.enabled:
            continue
        factory = load_factory_from_manifest(manifest, entry)
        if factory is not None:
            factories.append(factory)
    return factories


def load_manifests(
    extensions_dir: Path,
    scope: RuneScope = RuneScope.PROJECT,
    diagnostics: list[Diagnostic] | None = None,
) -> list[RuneManifest]:
    if not extensions_dir.exists():
        return []
    manifests: list[RuneManifest] = []
    for entry in extensions_dir.iterdir():
        if not entry.is_dir():
            continue
        manifest = load_manifest(entry)
        if manifest is None:
            if diagnostics is not None:
                diagnostics.append(
                    Diagnostic(
                        kind=DiagnosticKind.PARSE_WARNING,
                        rune_name=entry.name,
                        message=f"Could not parse manifest in {entry.name}",
                        scope=scope,
                        path=str(entry),
                    )
                )
            continue
        if not manifest.enabled:
            continue
        manifest.scope = scope
        manifest.path = str(entry)
        manifests.append(manifest)
    return manifests


def load_runes_from_paths(
    paths: Sequence[tuple[str | Path, RuneScope]],
    agent_name: str | None = None,
) -> tuple[list[RuneLoad], list[Diagnostic]]:
    """Load runes from multiple paths in precedence order (first wins).

    Args:
        paths: List of (path, scope) tuples, paths can include ~ and
            {agent_name} placeholder
        agent_name: Agent name to substitute {agent_name} placeholder

    Returns:
        Tuple of (rune_loads, diagnostics). RuneLoads are deduped
        by manifest name (first-wins), with the winner's scope recorded.
    """
    loads: list[RuneLoad] = []
    diagnostics: list[Diagnostic] = []
    seen_names: dict[str, tuple[RuneScope, str]] = {}

    for path_str, scope in paths:
        expanded = str(path_str).replace("{agent_name}", agent_name or "")
        path = Path(expanded).expanduser()
        if not path.exists():
            continue
        manifests = load_manifests(path, scope=scope, diagnostics=diagnostics)
        for manifest in manifests:
            factory = None
            if manifest.path:
                factory = load_factory_from_manifest(manifest, Path(manifest.path))
                if factory is None and manifest.entry_point:
                    diagnostics.append(
                        Diagnostic(
                            kind=DiagnosticKind.LOAD_FAILURE,
                            rune_name=manifest.name,
                            message=(
                                f"Failed to load factory for rune "
                                f"'{manifest.name}' from "
                                f"{manifest.entry_point}"
                            ),
                            scope=manifest.scope,
                            path=manifest.path,
                        )
                    )
            if manifest.name in seen_names:
                winner_scope, winner_path = seen_names[manifest.name]
                diagnostics.append(
                    Diagnostic(
                        kind=DiagnosticKind.SHADOWED_RUNE,
                        rune_name=manifest.name,
                        message=(
                            f"Rune '{manifest.name}' from {scope.value} "
                            f"({path}) shadowed by {winner_scope.value} "
                            f"({winner_path})"
                        ),
                        scope=scope,
                        path=str(path),
                    )
                )
                continue
            seen_names[manifest.name] = (scope, str(path))
            loads.append(RuneLoad(manifest=manifest, factory=factory))

    return loads, diagnostics
