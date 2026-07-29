from __future__ import annotations

from pathlib import Path

from mvgeos_runes.manifest import load_manifest
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
