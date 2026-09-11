from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

DEFAULT_MARKETPLACE_URL = (
    "https://raw.githubusercontent.com/IAmNo1Special/mvgeos-marketplace/main/index.json"
)


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

        runes = (
            marketplace_data.get("runes", {})
            if isinstance(marketplace_data, dict)
            else {}
        )
        rune_entry = runes.get(stripped_source)
        git_url = rune_entry.get("git") if isinstance(rune_entry, dict) else None
        if not git_url or not isinstance(git_url, str):
            raise ValueError(f"Rune '{stripped_source}' not found in marketplace.")

        dest = target / stripped_source
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()

        subpath = rune_entry.get("path") if isinstance(rune_entry, dict) else None
        if subpath:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
                subprocess.run(
                    ["git", "clone", "--depth", "1", git_url, str(tmp_dir)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                source_rune_dir = Path(tmp_dir) / str(subpath).strip().strip("/\\")
                shutil.copytree(source_rune_dir, dest)
        else:
            subprocess.run(
                ["git", "clone", git_url, str(dest)],
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
                    ["uv", "pip", "install", *deps],
                    check=True,
                    capture_output=True,
                    text=True,
                )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass

    return dest
