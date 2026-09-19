from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MARKETPLACE_URL = (
    "https://raw.githubusercontent.com/IAmNo1Special/mvgeos-marketplace/main/index.json"
)

# Allowlist for install/uninstall directory names. Anything outside this set
# (path separators, "..", URL-encoded tricks) is rejected before it can reach
# the filesystem.
_INSTALL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_install_name(name: str, *, kind: str) -> str:
    """Validate an install/uninstall name against the allowlist.

    Args:
        name: The directory name to validate.
        kind: Human label used in the error ("mvge" or "rune").

    Raises:
        ValueError: If the name is not a plain ``^[A-Za-z0-9_-]+$`` name.
    """
    if not _INSTALL_NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid {kind} name {name!r}: must match ^[A-Za-z0-9_-]+$.")
    return name


def _dest_within_target(target: Path, name: str) -> Path:
    """Return ``target / name`` after asserting it stays inside ``target``.

    Defense-in-depth alongside :func:`_validate_install_name`: catches
    symlink swaps and other resolution tricks even for well-formed names.

    Raises:
        ValueError: If the resolved destination escapes the target directory.
    """
    dest = target / name
    resolved_target = target.resolve()
    resolved_dest = dest.resolve()
    if resolved_dest != resolved_target and not resolved_dest.is_relative_to(
        resolved_target
    ):
        raise ValueError(
            f"Install destination {str(dest)!r} escapes target directory "
            f"{str(target)!r}."
        )
    return dest


def fetch_marketplace_runes(
    marketplace_url: str = DEFAULT_MARKETPLACE_URL,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Fetch available runes from the marketplace index."""
    try:
        response = httpx.get(marketplace_url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning(
            "Failed to fetch marketplace runes from '%s': %s",
            marketplace_url,
            exc,
        )
        return {}

    if isinstance(data, dict):
        runes = data.get("runes", {})
        if isinstance(runes, dict):
            return runes
    return {}


def list_installed_runes(
    target_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """List installed extension runes from the target directory."""
    target = (
        target_dir.expanduser()
        if target_dir is not None
        else Path("~/.agents/extensions").expanduser()
    )
    if not target.is_dir():
        return []

    installed: list[dict[str, Any]] = []
    for subdir in target.iterdir():
        if not subdir.is_dir():
            continue
        manifest_path = subdir / "manifest.json"
        if manifest_path.is_file():
            try:
                with manifest_path.open("r", encoding="utf-8-sig") as f:
                    manifest = json.load(f)
            except Exception:
                continue

            if not isinstance(manifest, dict):
                continue

            raw_types = manifest.get("types")
            types: list[str] = []
            if isinstance(raw_types, list):
                types = [str(t) for t in raw_types if t]
            elif "type" in manifest and manifest["type"]:
                types = [str(manifest["type"])]
            installed.append(
                {
                    "name": manifest.get("name", subdir.name),
                    "version": manifest.get("version", "unknown"),
                    "description": manifest.get("description", ""),
                    "runtime": manifest.get("runtime", "python"),
                    "enabled": manifest.get("enabled", True),
                    "path": str(subdir),
                    "hooks": manifest.get("hooks", []),
                    "python_deps": manifest.get("python_deps", []),
                    "type": types[0] if types else manifest.get("type", ""),
                    "types": types,
                    "created_at": manifest.get("created_at", ""),
                    "updated_at": manifest.get(
                        "updated_at", manifest.get("last_updated", "")
                    ),
                }
            )

    installed.sort(key=lambda r: str(r.get("name", "")))
    return installed


def uninstall_rune(name: str, target_dir: Path | None = None) -> bool:
    """Uninstall an installed rune by name."""
    target = (
        target_dir.expanduser()
        if target_dir is not None
        else Path("~/.agents/extensions").expanduser()
    )
    path = _dest_within_target(target, _validate_install_name(name, kind="rune"))
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
    return False


def install_rune(
    source: str,
    target_dir: Path | None = None,
    marketplace_url: str = DEFAULT_MARKETPLACE_URL,
) -> Path:
    """Install an extension rune from local path, Git repository, or marketplace."""
    stripped_source = source.strip()
    if not stripped_source:
        raise ValueError("Rune source cannot be empty.")

    target = (
        target_dir.expanduser()
        if target_dir is not None
        else Path("~/.agents/extensions").expanduser()
    )
    target.mkdir(parents=True, exist_ok=True)

    source_path = Path(stripped_source).expanduser()
    if source_path.exists():
        dest = _dest_within_target(
            target, _validate_install_name(source_path.name, kind="rune")
        )
        if source_path.resolve() != dest.resolve():
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.copytree(source_path, dest)
    elif stripped_source.startswith(
        ("git@", "git://", "http://", "https://", "ssh://")
    ) or stripped_source.endswith(".git"):
        name = stripped_source.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        _validate_install_name(name, kind="rune")
        dest = _dest_within_target(target, name)
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        subprocess.run(
            ["git", "clone", "--", stripped_source, str(dest)],
            check=True,
            capture_output=True,
            text=True,
        )
    else:
        try:
            response = httpx.get(marketplace_url, timeout=15.0)
            response.raise_for_status()
            marketplace_data = response.json()
        except Exception as exc:
            raise ValueError(
                f"Failed to fetch marketplace index from '{marketplace_url}': {exc}"
            ) from exc

        runes = (
            marketplace_data.get("runes", {})
            if isinstance(marketplace_data, dict)
            else {}
        )
        rune_entry = runes.get(stripped_source)
        git_url = rune_entry.get("git") if isinstance(rune_entry, dict) else None
        if not git_url or not isinstance(git_url, str):
            raise ValueError(f"Rune '{stripped_source}' not found in marketplace.")

        _validate_install_name(stripped_source, kind="rune")
        dest = _dest_within_target(target, stripped_source)
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()

        subpath = rune_entry.get("path") if isinstance(rune_entry, dict) else None
        if subpath:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
                subprocess.run(
                    ["git", "clone", "--depth", "1", "--", git_url, str(tmp_dir)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                source_rune_dir = Path(tmp_dir) / str(subpath).strip().strip("/\\")
                shutil.copytree(source_rune_dir, dest)
        else:
            subprocess.run(
                ["git", "clone", "--", git_url, str(dest)],
                check=True,
                capture_output=True,
                text=True,
            )

    manifest_path = dest / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Invalid rune: manifest.json missing.")

    try:
        with manifest_path.open("r", encoding="utf-8-sig") as f:
            manifest_data = json.load(f)
        python_deps = manifest_data.get("python_deps")
        if python_deps and isinstance(python_deps, list):
            deps = [str(d) for d in python_deps if str(d).strip()]
            if deps:
                subprocess.run(
                    ["uv", "add", *deps],
                    check=True,
                    capture_output=True,
                    text=True,
                )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass

    return dest
