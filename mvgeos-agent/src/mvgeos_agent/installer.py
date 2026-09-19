from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
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


def _confirm_python_deps_install(deps: list[str], *, confirm: bool | None) -> bool:
    """Decide whether to run ``uv add`` for manifest-declared deps.

    Args:
        deps: The dependency specifiers from the manifest.
        confirm: ``True`` installs without prompting, ``False`` skips,
            ``None`` (default) prompts interactively and fails closed
            (skips) when stdin is not a TTY.

    Returns:
        True when the dependencies should be installed.
    """
    if confirm is True:
        return True
    if confirm is False:
        logger.info("Skipping python dependency install (confirm_python_deps=False).")
        return False
    if not sys.stdin.isatty():
        logger.warning(
            "Non-interactive session: skipping install of unreviewed python "
            "dependencies %s. Re-run with confirm_python_deps=True to install.",
            deps,
        )
        return False
    print("The mvge manifest declares the following python dependencies:")  # noqa: T201
    for dep in deps:
        print(f"  - {dep}")  # noqa: T201
    try:
        answer = input("Install them with 'uv add'? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def _fetch_marketplace_data(
    marketplace_url: str = DEFAULT_MARKETPLACE_URL,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Fetch marketplace index data with fallbacks for CDN caching and branch delays."""
    first_error: Exception | None = None
    data: Any = None
    try:
        response = httpx.get(marketplace_url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        first_error = exc

    if isinstance(data, dict):
        mvges = data.get("mvges") or data.get("agents")
        if isinstance(mvges, dict) and mvges:
            return data

    # Fallback 1: If URL has /main/, try /HEAD/ (bypasses Fastly branch caching)
    if "/main/" in marketplace_url:
        head_url = marketplace_url.replace("/main/", "/HEAD/")
        try:
            head_resp = httpx.get(head_url, timeout=timeout)
            head_resp.raise_for_status()
            head_data = head_resp.json()
            if isinstance(head_data, dict):
                head_mvges = head_data.get("mvges") or head_data.get("agents")
                if isinstance(head_mvges, dict) and head_mvges:
                    return head_data
        except Exception:
            pass

    # Fallback 2: GitHub Contents API for official marketplace
    if (
        "githubusercontent.com" in marketplace_url
        and "mvgeos-marketplace" in marketplace_url
    ):
        try:
            api_url = (
                "https://api.github.com/repos/IAmNo1Special/mvgeos-marketplace"
                "/contents/index.json"
            )
            api_resp = httpx.get(
                api_url,
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=timeout,
            )
            api_resp.raise_for_status()
            api_json = api_resp.json()
            if isinstance(api_json, dict) and "content" in api_json:
                decoded = base64.b64decode(api_json["content"]).decode("utf-8")
                api_data = json.loads(decoded)
                if isinstance(api_data, dict):
                    api_mvges = api_data.get("mvges") or api_data.get("agents")
                    if isinstance(api_mvges, dict) and api_mvges:
                        return api_data
        except Exception:
            pass

    if first_error is not None and not isinstance(data, dict):
        raise first_error

    return data if isinstance(data, dict) else {}


def fetch_marketplace_mvges(
    marketplace_url: str = DEFAULT_MARKETPLACE_URL,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Fetch available mvges (agents) from the marketplace index."""
    try:
        data = _fetch_marketplace_data(marketplace_url, timeout=timeout)
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
    path = _dest_within_target(target, _validate_install_name(name, kind="mvge"))
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
    confirm_python_deps: bool | None = None,
) -> Path:
    """Install an agent mvge from local path, Git repository, or marketplace.

    Args:
        source: Local path, git URL, or marketplace mvge name.
        target_dir: Install target directory (default ``~/.agents/agents``).
        marketplace_url: Marketplace index URL.
        confirm_python_deps: Gate for installing ``python_deps`` declared in
            the installed manifest. ``True`` installs without prompting,
            ``False`` skips, ``None`` (default) prompts interactively and
            fails closed (skips) in non-interactive sessions.
    """
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
        dest = _dest_within_target(
            target, _validate_install_name(source_path.name, kind="mvge")
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
        _validate_install_name(name, kind="mvge")
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
            marketplace_data = _fetch_marketplace_data(marketplace_url, timeout=15.0)
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

        _validate_install_name(stripped_source, kind="mvge")
        dest = _dest_within_target(target, stripped_source)
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()

        subpath = mvge_entry.get("path") if isinstance(mvge_entry, dict) else None
        if subpath:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
                try:
                    subprocess.run(
                        ["git", "clone", "--depth", "1", "--", git_url, str(tmp_dir)],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    source_mvge_dir = Path(tmp_dir) / str(subpath).strip().strip("/\\")
                    shutil.copytree(source_mvge_dir, dest)
                except (subprocess.CalledProcessError, OSError):
                    local_candidate: Path | None = None
                    for base in (
                        os.environ.get("MVGEOS_MARKETPLACE_DIR"),
                        str(Path.home() / "Desktop" / "mvgeos-marketplace"),
                    ):
                        if base:
                            cand = Path(base).expanduser() / str(subpath).strip().strip(
                                "/\\"
                            )
                            if cand.is_dir():
                                local_candidate = cand
                                break
                    if local_candidate is not None:
                        shutil.copytree(local_candidate, dest)
                    else:
                        raise
        else:
            subprocess.run(
                ["git", "clone", "--", git_url, str(dest)],
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
                if _confirm_python_deps_install(deps, confirm=confirm_python_deps):
                    subprocess.run(
                        ["uv", "add", *deps],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                else:
                    logger.warning(
                        "Skipping unreviewed python dependencies for %s: %s",
                        dest,
                        deps,
                    )
        if (dest / "pyproject.toml").is_file():
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["uv", "add", "--editable", str(dest)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass

    return dest
