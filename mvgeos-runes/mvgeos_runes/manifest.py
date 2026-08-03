from __future__ import annotations

import contextlib
import json
from pathlib import Path

from mvgeos_runes.types import RuneManifest, RuneShortcut, SigilHook


def load_manifest(path: Path) -> RuneManifest | None:
    manifest_path = path / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return None

    if "name" not in data or "version" not in data:
        return None

    hooks = []
    for hook_str in data.get("hooks", []):
        with contextlib.suppress(ValueError):
            hooks.append(SigilHook(hook_str))

    shortcuts = []
    for sc_data in data.get("shortcuts", []):
        if isinstance(sc_data, str):
            shortcuts.append(RuneShortcut(key=sc_data))
        elif isinstance(sc_data, dict):
            shortcuts.append(
                RuneShortcut(
                    key=sc_data.get("key", ""),
                    description=sc_data.get("description", ""),
                )
            )

    return RuneManifest(
        name=data["name"],
        version=data["version"],
        description=data.get("description", ""),
        hooks=hooks,
        entry_point=data.get("entry_point", ""),
        shortcuts=shortcuts,
    )
