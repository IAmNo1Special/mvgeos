from __future__ import annotations

import importlib.util
import inspect
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import yaml

from mvgeos_runes.manifest import load_manifest
from mvgeos_runes.rune_api import RuneFactory
from mvgeos_runes.types import (
    Diagnostic,
    DiagnosticKind,
    RuneLoad,
    RuneManifest,
    RuneScope,
    SkillDiagnostic,
    SkillDiagnosticKind,
    SkillLoad,
    SkillManifest,
    SkillScope,
)


def check_python_dep_installed(module_name: str) -> bool:
    """Return True if a Python module is importable by importlib."""
    return importlib.util.find_spec(module_name) is not None


def _missing_dep_diagnostic(manifest: RuneManifest, dep: str) -> Diagnostic:
    """Build the MISSING_DEP diagnostic for a single uninstalled dependency."""
    return Diagnostic(
        kind=DiagnosticKind.MISSING_DEP,
        rune_name=manifest.name,
        message=(
            f"Rune '{manifest.name}' requires python dependency '{dep}' "
            "which is not installed. Run 'mvgeos setup install' to install it."
        ),
        scope=manifest.scope,
        path=manifest.path,
    )


def discover_rune_site_packages(rune_dir: Path) -> list[Path]:
    """Return rune-local import roots (venv site-packages, entry dir, rune dir).

    A rune may bundle python_deps in its own ``.venv``/``venv`` site-packages;
    these must be on ``sys.path`` *before* dependency inspection so bundled
    deps are not falsely reported as missing.
    """
    rune_dir_resolved = rune_dir.resolve()
    site_pkg_paths: list[Path] = []
    for venv_name in (".venv", "venv"):
        venv_dir = rune_dir_resolved / venv_name
        if venv_dir.is_dir():
            win_sp = venv_dir / "Lib" / "site-packages"
            if win_sp.is_dir() and win_sp not in site_pkg_paths:
                site_pkg_paths.append(win_sp)
            lib_dir = venv_dir / "lib"
            if lib_dir.is_dir():
                posix_sp = lib_dir / "site-packages"
                if posix_sp.is_dir() and posix_sp not in site_pkg_paths:
                    site_pkg_paths.append(posix_sp)
                for sp in sorted(lib_dir.glob("python*/site-packages")):
                    if sp.is_dir() and sp not in site_pkg_paths:
                        site_pkg_paths.append(sp)
    site_pkg_paths.append(rune_dir_resolved)
    return site_pkg_paths


def _inject_rune_paths(rune_dir: Path, entry: Path) -> None:
    """Put rune-local import roots on ``sys.path`` so bundled deps resolve."""
    for p in discover_rune_site_packages(rune_dir):
        p_str = str(p)
        if p_str not in sys.path:
            sys.path.insert(0, p_str)
    entry_parent = entry.parent.resolve()
    entry_parent_str = str(entry_parent)
    if entry_parent_str not in sys.path:
        sys.path.insert(0, entry_parent_str)


def preflight_rune_deps(
    manifest: RuneManifest,
) -> list[str]:
    """Return the list of declared python_deps that are not installed."""
    return [dep for dep in manifest.python_deps if not check_python_dep_installed(dep)]


def load_factory_from_manifest(
    manifest: RuneManifest,
    rune_dir: Path,
    diagnostics: list[Diagnostic] | None = None,
) -> RuneFactory | None:
    if not manifest.entry_point:
        return None

    entry = (rune_dir / manifest.entry_point).resolve()

    # Inject rune-local import roots (including any bundled venv) BEFORE
    # dependency inspection, so deps shipped inside the rune are not
    # falsely reported as missing.
    _inject_rune_paths(rune_dir, entry)

    missing = preflight_rune_deps(manifest)
    if missing:
        if diagnostics is not None:
            for dep in missing:
                diagnostics.append(_missing_dep_diagnostic(manifest, dep))
        return None

    if not entry.exists():
        if diagnostics is not None:
            diagnostics.append(
                Diagnostic(
                    kind=DiagnosticKind.LOAD_FAILURE,
                    rune_name=manifest.name,
                    message=f"Entry point file does not exist: {entry}",
                    scope=manifest.scope,
                    path=manifest.path,
                )
            )
        return None

    spec = importlib.util.spec_from_file_location(
        f"mvgeos_rune_{manifest.name}", str(entry)
    )

    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as err:
        if diagnostics is not None:
            msg = f"Failed to execute rune module {manifest.name}: {err}"
            if manifest.python_deps:
                msg += f" (declared python_deps: {', '.join(manifest.python_deps)})"
            diagnostics.append(
                Diagnostic(
                    kind=DiagnosticKind.LOAD_FAILURE,
                    rune_name=manifest.name,
                    message=msg,
                    scope=manifest.scope,
                    path=manifest.path,
                )
            )
        return None
    factory = getattr(mod, "rune_factory", None)
    if factory is None or not callable(factory):
        if diagnostics is not None:
            diagnostics.append(
                Diagnostic(
                    kind=DiagnosticKind.LOAD_FAILURE,
                    rune_name=manifest.name,
                    message=(
                        f"Rune '{manifest.name}' does not export a callable "
                        "'rune_factory' function"
                    ),
                    scope=manifest.scope,
                    path=manifest.path,
                )
            )
        return None

    try:
        sig = inspect.signature(factory)
        params = list(sig.parameters.values())
        if not params and not any(
            p.kind == inspect.Parameter.VAR_POSITIONAL for p in params
        ):
            if diagnostics is not None:
                diagnostics.append(
                    Diagnostic(
                        kind=DiagnosticKind.LOAD_FAILURE,
                        rune_name=manifest.name,
                        message=(
                            f"Rune factory '{manifest.name}' signature expects "
                            "at least 1 argument (RuneAPI)"
                        ),
                        scope=manifest.scope,
                        path=manifest.path,
                    )
                )
            return None
    except ValueError, TypeError:
        pass

    return cast(RuneFactory, factory)


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
                factory = load_factory_from_manifest(
                    manifest, Path(manifest.path), diagnostics=diagnostics
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


# Skill discovery constants
SKILL_SCOPES = [
    (SkillScope.PROJECT, Path(".agents/skills")),
    (SkillScope.USER, Path("~/.agents/skills")),
    (SkillScope.AGENT, Path("~/.agents/.mvgeos/{agent_name}/skills")),
]

NAME_REGEX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def load_skill_manifest(path: Path) -> SkillManifest | None:
    """Load a skill manifest from a SKILL.md file with YAML frontmatter."""
    skill_md_path = path / "SKILL.md"
    if not skill_md_path.exists():
        return None
    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return None

    content = content.lstrip("\ufeff")

    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        frontmatter = yaml.safe_load(parts[1])
    except Exception:
        return None

    if not isinstance(frontmatter, dict):
        return None

    name = frontmatter.get("name")
    if not name or not isinstance(name, str):
        return None

    if not (1 <= len(name) <= 64):
        return None

    if not NAME_REGEX.match(name):
        return None

    if name != path.name:
        return None

    description = frontmatter.get("description")
    if not description or not isinstance(description, str):
        return None

    if not (1 <= len(description) <= 1024):
        return None

    license_val = frontmatter.get("license", "")
    if not isinstance(license_val, str):
        license_val = ""

    compatibility = frontmatter.get("compatibility", "")
    if not isinstance(compatibility, str):
        compatibility = ""

    metadata = frontmatter.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    allowed_tools = frontmatter.get("allowed-tools", "")
    if not isinstance(allowed_tools, str):
        allowed_tools = ""

    disable_model_invocation = frontmatter.get("disable-model-invocation", False)
    if not isinstance(disable_model_invocation, bool):
        disable_model_invocation = False

    version = frontmatter.get("version", "")
    if not isinstance(version, str):
        version = ""

    return SkillManifest(
        name=name,
        description=description,
        scope=SkillScope.PROJECT,  # Will be set by caller
        path=str(path),
        version=version,
        license=license_val,
        compatibility=compatibility,
        metadata=metadata,
        allowed_tools=allowed_tools,
        disable_model_invocation=disable_model_invocation,
    )


def load_skill_manifests(
    skills_dir: Path,
    scope: SkillScope = SkillScope.PROJECT,
    diagnostics: list[SkillDiagnostic] | None = None,
) -> list[SkillManifest]:
    """Load all skill manifests from a skills directory."""
    if not skills_dir.exists():
        return []
    manifests: list[SkillManifest] = []
    for entry in skills_dir.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        manifest = load_skill_manifest(entry)
        if manifest is None:
            if diagnostics is not None:
                diagnostics.append(
                    SkillDiagnostic(
                        kind=SkillDiagnosticKind.PARSE_WARNING,
                        skill_name=entry.name,
                        message=f"Could not parse skill manifest in {entry.name}",
                        scope=scope,
                        path=str(entry),
                    )
                )
            continue
        manifest.scope = scope
        manifest.path = str(entry)
        manifests.append(manifest)
    return manifests


def load_skills_from_paths(
    paths: Sequence[tuple[str | Path, SkillScope]],
    agent_name: str | None = None,
) -> tuple[list[SkillLoad], list[SkillDiagnostic]]:
    """Load skills from multiple paths in precedence order (first wins).

    Args:
        paths: List of (path, scope) tuples, paths can include ~ and
            {agent_name} placeholder
        agent_name: Agent name to substitute {agent_name} placeholder

    Returns:
        Tuple of (skill_loads, diagnostics). SkillLoads are deduped
        by manifest name (first-wins), with the winner's scope recorded.
    """
    loads: list[SkillLoad] = []
    diagnostics: list[SkillDiagnostic] = []
    seen_names: dict[str, tuple[SkillScope, str]] = {}

    for path_str, scope in paths:
        expanded = str(path_str).replace("{agent_name}", agent_name or "")
        path = Path(expanded).expanduser()
        if not path.exists():
            continue
        manifests = load_skill_manifests(path, scope=scope, diagnostics=diagnostics)
        for manifest in manifests:
            if manifest.name in seen_names:
                winner_scope, winner_path = seen_names[manifest.name]
                diagnostics.append(
                    SkillDiagnostic(
                        kind=SkillDiagnosticKind.SHADOWED_SKILL,
                        skill_name=manifest.name,
                        message=(
                            f"Skill '{manifest.name}' from {scope.value} "
                            f"({path}) shadowed by {winner_scope.value} "
                            f"({winner_path})"
                        ),
                        scope=scope,
                        path=str(path),
                    )
                )
                continue
            seen_names[manifest.name] = (scope, str(path))
            loads.append(SkillLoad(manifest=manifest))

    return loads, diagnostics


def get_default_skill_paths(agent_name: str) -> list[tuple[Path, SkillScope]]:
    """Get the default skill discovery paths in precedence order (highest first)."""
    result: list[tuple[Path, SkillScope]] = []
    for scope, path_template in SKILL_SCOPES:
        path_str = str(path_template).replace("{agent_name}", agent_name)
        path = Path(path_str).expanduser()
        result.append((path, scope))
    return result
