from __future__ import annotations

import contextlib
import json
import logging
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


def fetch_marketplace_mvges(
    marketplace_url: str = DEFAULT_MARKETPLACE_URL,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Fetch available mvges (agents) from the marketplace index."""
    try:
        response = httpx.get(marketplace_url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning(
            "Failed to fetch marketplace mvges from '%s': %s",
            marketplace_url,
            exc,
        )
        return {}

    if isinstance(data, dict):
        mvges = data.get("mvges") or data.get("agents") or {}
        if isinstance(mvges, dict):
            return mvges
    return {}


def list_installed_mvges(
    target_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """List installed mvges from the target directory."""
    target = (
        target_dir.expanduser()
        if target_dir is not None
        else Path("~/.agents/agents").expanduser()
    )
    if not target.is_dir():
        return []

    installed: list[dict[str, Any]] = []
    for subdir in target.iterdir():
        if not subdir.is_dir():
            continue
        manifest_path = subdir / "manifest.json"
        agent_md_path = subdir / "agent.md"
        spells_dir = subdir / "spells"

        manifest: dict[str, Any] = {}
        if manifest_path.is_file():
            try:
                with manifest_path.open("r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        manifest = data
            except Exception:
                pass

        spells: list[str] = manifest.get("spells", [])
        if not spells and spells_dir.is_dir():
            spells = [
                f.stem
                for f in sorted(spells_dir.iterdir())
                if f.is_file() and f.suffix == ".py" and not f.name.startswith("_")
            ]

        installed.append(
            {
                "name": manifest.get("name", subdir.name),
                "version": manifest.get("version", "unknown"),
                "description": manifest.get("description", ""),
                "runtime": manifest.get("runtime", "python"),
                "enabled": manifest.get("enabled", True),
                "path": str(subdir),
                "spells": spells,
                "has_manifest": manifest_path.is_file(),
                "has_agent_md": agent_md_path.is_file(),
            }
        )

    installed.sort(key=lambda r: str(r.get("name", "")))
    return installed


def uninstall_mvge(name: str, target_dir: Path | None = None) -> bool:
    """Uninstall an installed mvge by name."""
    target = (
        target_dir.expanduser()
        if target_dir is not None
        else Path("~/.agents/agents").expanduser()
    )
    path = target / name
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
    return False


def install_mvge(
    source: str,
    target_dir: Path | None = None,
    marketplace_url: str = DEFAULT_MARKETPLACE_URL,
) -> Path:
    """Install an agent mvge from local path, Git repository, or marketplace."""
    stripped_source = source.strip()
    if not stripped_source:
        raise ValueError("Mvge source cannot be empty.")

    target = (
        target_dir.expanduser()
        if target_dir is not None
        else Path("~/.agents/agents").expanduser()
    )
    target.mkdir(parents=True, exist_ok=True)

    source_path = Path(stripped_source).expanduser()
    if source_path.exists():
        dest = target / source_path.name
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
        dest = target / name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        subprocess.run(
            ["git", "clone", stripped_source, str(dest)],
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

        mvges = (
            marketplace_data.get("mvges") or marketplace_data.get("agents") or {}
            if isinstance(marketplace_data, dict)
            else {}
        )
        mvge_entry = mvges.get(stripped_source)
        if not mvge_entry and isinstance(mvges, dict):
            for alt in (
                stripped_source.replace("-", "_"),
                stripped_source.replace("_", "-"),
            ):
                if alt in mvges:
                    mvge_entry = mvges[alt]
                    break

        git_url = mvge_entry.get("git") if isinstance(mvge_entry, dict) else None
        if not git_url or not isinstance(git_url, str):
            raise ValueError(f"Mvge '{stripped_source}' not found in marketplace.")

        dest = target / stripped_source
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()

        subpath = mvge_entry.get("path") if isinstance(mvge_entry, dict) else None
        if subpath:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
                subprocess.run(
                    ["git", "clone", "--depth", "1", git_url, str(tmp_dir)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                source_mvge_dir = Path(tmp_dir) / str(subpath).strip().strip("/\\")
                shutil.copytree(source_mvge_dir, dest)
        else:
            subprocess.run(
                ["git", "clone", git_url, str(dest)],
                check=True,
                capture_output=True,
                text=True,
            )

    manifest_path = dest / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Invalid mvge: manifest.json missing.")

    try:
        with manifest_path.open("r", encoding="utf-8-sig") as f:
            manifest_data = json.load(f)
        python_deps = manifest_data.get("python_deps")
        if python_deps and isinstance(python_deps, list):
            deps = [str(d) for d in python_deps if str(d).strip()]
            if deps:
                subprocess.run(
                    ["uv", "pip", "install", *deps],
                    check=True,
                    capture_output=True,
                    text=True,
                )
        if (dest / "pyproject.toml").is_file():
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["uv", "pip", "install", "-e", str(dest)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass

    return dest
