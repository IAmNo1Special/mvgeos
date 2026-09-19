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


def _manifest_install_name(source_dir: Path, *, kind: str) -> str:
    """Read the install directory name from a staged source's manifest.

    The manifest ``name`` is the single source of truth for install, list,
    and uninstall, so the three commands always agree on where a rune lives.

    Raises:
        ValueError: If the manifest is missing, unreadable, nameless, or
            the name fails the install-name allowlist (e.g. traversal).
    """
    manifest_path = source_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Invalid {kind}: manifest.json missing.")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid {kind}: manifest.json unreadable: {exc}") from exc
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Invalid {kind}: manifest.json missing 'name'.")
    return _validate_install_name(name.strip(), kind=kind)


def _clear_dest(dest: Path) -> None:
    """Remove an existing install destination (dir or file)."""
    if dest.exists():
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        else:
            dest.unlink()


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


def set_rune_enabled(name: str, enabled: bool, target_dir: Path | None = None) -> bool:
    """Set the enabled flag in an installed rune's manifest.json.

    Returns True when the manifest was updated, False when the rune
    is not installed or its manifest cannot be read/written.
    """
    target = (
        target_dir.expanduser()
        if target_dir is not None
        else Path("~/.agents/extensions").expanduser()
    )
    rune_dir = _dest_within_target(target, _validate_install_name(name, kind="rune"))
    manifest_path = rune_dir / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        with manifest_path.open("r", encoding="utf-8-sig") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(manifest, dict):
        return False
    manifest["enabled"] = bool(enabled)
    try:
        with manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
    except OSError:
        return False
    return True


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
        if not source_path.is_dir():
            raise ValueError(f"Invalid rune: not a directory: {source_path}")
        # The manifest name is the single source of truth for the install
        # directory, so install/list/uninstall always agree. Read it before
        # touching the target: a bad manifest fails without copying.
        name = _manifest_install_name(source_path, kind="rune")
        dest = _dest_within_target(target, name)
        if source_path.resolve() != dest.resolve():
            _clear_dest(dest)
            shutil.copytree(source_path, dest)
    elif stripped_source.startswith(
        ("git@", "git://", "http://", "https://", "ssh://")
    ) or stripped_source.endswith(".git"):
        # Preflight: reject obviously-malicious URLs before cloning. The
        # URL basename is only a sanity check here -- the manifest name
        # decides the actual install directory below.
        url_basename = stripped_source.rstrip("/").split("/")[-1].removesuffix(".git")
        _validate_install_name(url_basename, kind="rune")
        # Clone to a staging dir first so the manifest name (not the URL
        # basename) decides the install directory.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
            staged = Path(tmp_dir) / "repo"
            subprocess.run(
                ["git", "clone", "--", stripped_source, str(staged)],
                check=True,
                capture_output=True,
                text=True,
            )
            name = _manifest_install_name(staged, kind="rune")
            dest = _dest_within_target(target, name)
            _clear_dest(dest)
            shutil.copytree(staged, dest)
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
        subpath = rune_entry.get("path") if isinstance(rune_entry, dict) else None
        # Stage in a temp dir first so the manifest name (not the marketplace
        # key) decides the install directory.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
            if subpath:
                subprocess.run(
                    ["git", "clone", "--depth", "1", "--", git_url, str(tmp_dir)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                staged = Path(tmp_dir) / str(subpath).strip().strip("/\\")
            else:
                subprocess.run(
                    ["git", "clone", "--", git_url, str(tmp_dir)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                staged = Path(tmp_dir)
            name = _manifest_install_name(staged, kind="rune")
            dest = _dest_within_target(target, name)
            _clear_dest(dest)
            shutil.copytree(staged, dest)

    # The manifest was already validated from the staged source; dest carries
    # an identical copy.
    manifest_path = dest / "manifest.json"
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
