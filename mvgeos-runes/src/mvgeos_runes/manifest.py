from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from mvgeos_runes.types import ExecutionMode, RuneManifest, RuneShortcut, SigilHook


def _extract_string_list(data: dict[str, Any], key: str) -> list[str]:
    raw = data.get(key, [])
    if not isinstance(raw, list):
        return []
    return [dep for dep in raw if isinstance(dep, str)]


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

    system_deps = _extract_string_list(data, "system_deps")
    python_deps = _extract_string_list(data, "python_deps")

    exec_mode_str = data.get("execution_mode", "parallel")
    try:
        execution_mode = ExecutionMode(exec_mode_str)
    except ValueError:
        execution_mode = ExecutionMode.PARALLEL

    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        enabled = True

    return RuneManifest(
        name=data["name"],
        version=data["version"],
        description=data.get("description", ""),
        hooks=hooks,
        entry_point=data.get("entry_point", ""),
        shortcuts=shortcuts,
        system_deps=system_deps,
        python_deps=python_deps,
        execution_mode=execution_mode,
        enabled=enabled,
    )
