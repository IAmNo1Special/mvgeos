from __future__ import annotations

import dataclasses
import importlib.util
import inspect
import json
import re
import site
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import yaml

from mvgeos_runes.manifest import load_manifest
from mvgeos_runes.rune_api import RuneFactory
from mvgeos_runes.types import (
    Diagnostic,
    DiagnosticKind,
    PluginManifest,
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
    base_name = re.split(r"[><=!~;\[]", module_name)[0].strip().replace("-", "_")
    if not base_name:
        return False
    try:
        return importlib.util.find_spec(base_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


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
    search_dirs = [rune_dir_resolved] + list(rune_dir_resolved.parents)[:2]
    for candidate_dir in search_dirs:
        for venv_name in (".venv", "venv"):
            venv_dir = candidate_dir / venv_name
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
        if p.name == "site-packages":
            site.addsitedir(p_str)
        elif p_str not in sys.path:
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

    # Check for non-Python runtime (e.g., TypeScript/JavaScript extensions for Pi)
    if getattr(manifest, "runtime", "").lower() in (
        "typescript",
        "ts",
        "javascript",
        "js",
        "node",
        "bun",
    ) or manifest.entry_point.endswith((".ts", ".js", ".mjs", ".cjs")):
        if diagnostics is not None:
            diagnostics.append(
                Diagnostic(
                    kind=DiagnosticKind.INCOMPATIBLE_RUNTIME,
                    rune_name=manifest.name,
                    message=(
                        f"Skipping extension '{manifest.name}': targets "
                        f"'{getattr(manifest, 'runtime', 'typescript')}' runtime"
                        " (Python host)"
                    ),
                    scope=manifest.scope,
                    path=manifest.path,
                )
            )
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
    except (ValueError, TypeError):
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


def _resolve_search_path(path_str: str | Path, agent_name: str | None = None) -> Path:
    """Expand ~ and replace {agent_name} placeholder in a search path."""
    expanded = str(path_str).replace("{agent_name}", agent_name or "")
    return Path(expanded).expanduser()


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
        path = _resolve_search_path(path_str, agent_name)
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
    (SkillScope.AGENT, Path("~/.agents/agents/{agent_name}/skills")),
]

NAME_REGEX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PLUGIN_NAME_REGEX = re.compile(r"^(?!.*(--|\.\.))[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")
FRONTMATTER_REGEX = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.DOTALL)
UNQUOTED_COLON_REGEX = re.compile(
    r"^(\s*[a-zA-Z0-9_-]+:\s*)([^\"'\r\n#].*:\s*.*)$", re.MULTILINE
)


def _repair_yaml_unquoted_colons(yaml_text: str) -> str:
    """Wrap unquoted YAML values containing colons in quotes for tolerant parsing."""

    def replacer(match: re.Match[str]) -> str:
        key_part = match.group(1)
        val_part = match.group(2).strip()
        escaped_val = val_part.replace('"', '\\"')
        return f'{key_part}"{escaped_val}"'

    return UNQUOTED_COLON_REGEX.sub(replacer, yaml_text)


_SKILL_MANIFEST_CACHE: dict[str, tuple[float, SkillManifest | None]] = {}


def clear_skill_manifest_cache() -> None:
    """Clear cached skill manifests."""
    _SKILL_MANIFEST_CACHE.clear()


def _parse_skill_manifest(
    path: Path,
    diagnostics: list[SkillDiagnostic] | None = None,
    scope: SkillScope = SkillScope.PROJECT,
    lenient: bool = False,
) -> SkillManifest | None:
    skill_md_path = (path / "SKILL.md").resolve()
    if not skill_md_path.is_file():
        return None

    path_resolved = path.resolve()
    if not str(skill_md_path).startswith(str(path_resolved)):
        if diagnostics is not None:
            diagnostics.append(
                SkillDiagnostic(
                    kind=SkillDiagnosticKind.PATH_ESCAPE,
                    skill_name=path.name,
                    message=(
                        f"SKILL.md in {path.name} resolves outside the skill directory"
                    ),
                    scope=scope,
                    path=str(path),
                )
            )
        return None

    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return None

    content = content.lstrip("\ufeff")
    match = FRONTMATTER_REGEX.match(content)
    if not match:
        if diagnostics is not None:
            diagnostics.append(
                SkillDiagnostic(
                    kind=SkillDiagnosticKind.PARSE_WARNING,
                    skill_name=path.name,
                    message=(
                        f"SKILL.md in {path.name} missing valid '---' "
                        "frontmatter delimiters"
                    ),
                    scope=scope,
                    path=str(path),
                )
            )
        return None

    raw_yaml, body = match.group(1), match.group(2).strip()

    try:
        frontmatter = yaml.safe_load(raw_yaml)
    except yaml.YAMLError:
        repaired_yaml = _repair_yaml_unquoted_colons(raw_yaml)
        try:
            frontmatter = yaml.safe_load(repaired_yaml)
            if diagnostics is not None:
                diagnostics.append(
                    SkillDiagnostic(
                        kind=SkillDiagnosticKind.MALFORMED_YAML,
                        skill_name=path.name,
                        message=(
                            "Repaired unquoted colons in YAML frontmatter for "
                            f"{path.name}"
                        ),
                        scope=scope,
                        path=str(path),
                    )
                )
        except yaml.YAMLError as exc:
            if diagnostics is not None:
                diagnostics.append(
                    SkillDiagnostic(
                        kind=SkillDiagnosticKind.PARSE_WARNING,
                        skill_name=path.name,
                        message=f"Invalid YAML frontmatter in {path.name}: {exc}",
                        scope=scope,
                        path=str(path),
                    )
                )
            return None

    if not isinstance(frontmatter, dict):
        if diagnostics is not None:
            diagnostics.append(
                SkillDiagnostic(
                    kind=SkillDiagnosticKind.PARSE_WARNING,
                    skill_name=path.name,
                    message=f"Frontmatter in {path.name} is not a YAML mapping",
                    scope=scope,
                    path=str(path),
                )
            )
        return None

    description = frontmatter.get("description")
    if (
        not isinstance(description, str)
        or not (1 <= len(description) <= 1024)
        or not description.strip()
    ):
        if diagnostics is not None:
            diagnostics.append(
                SkillDiagnostic(
                    kind=SkillDiagnosticKind.PARSE_WARNING,
                    skill_name=path.name,
                    message=(
                        f"Skill in {path.name} missing or invalid 'description' "
                        "(must be string of 1-1024 chars)"
                    ),
                    scope=scope,
                    path=str(path),
                )
            )
        return None

    name = frontmatter.get("name")
    if not isinstance(name, str) or not (1 <= len(name) <= 64) or not name.strip():
        if not lenient:
            if diagnostics is not None:
                diagnostics.append(
                    SkillDiagnostic(
                        kind=SkillDiagnosticKind.PARSE_WARNING,
                        skill_name=path.name,
                        message=(
                            f"Skill in {path.name} missing or invalid 'name' "
                            "(must be string of 1-64 chars)"
                        ),
                        scope=scope,
                        path=str(path),
                    )
                )
            return None
        name = path.name

    if (not NAME_REGEX.match(name) or name != path.name) and not lenient:
        if diagnostics is not None:
            diagnostics.append(
                SkillDiagnostic(
                    kind=SkillDiagnosticKind.PARSE_WARNING,
                    skill_name=name,
                    message=(
                        f"Skill name '{name}' does not match regex "
                        f"^[a-z0-9]+(-[a-z0-9]+)*$ or directory '{path.name}'"
                    ),
                    scope=scope,
                    path=str(path),
                )
            )
        return None

    def _get_str(key: str) -> str:
        val = frontmatter.get(key, "")
        return val if isinstance(val, str) else ""

    metadata = frontmatter.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    version = _get_str("version")
    if not version and isinstance(metadata.get("version"), str):
        version = metadata["version"]

    compatibility = _get_str("compatibility")
    if len(compatibility) > 500:
        compatibility = compatibility[:500]

    disable_model_invocation = frontmatter.get("disable-model-invocation", False)
    if not isinstance(disable_model_invocation, bool):
        disable_model_invocation = False

    return SkillManifest(
        name=name,
        description=description.strip(),
        scope=scope,
        path=str(path_resolved),
        location=str(skill_md_path),
        version=version,
        license=_get_str("license"),
        compatibility=compatibility,
        metadata=metadata,
        allowed_tools=_get_str("allowed-tools"),
        disable_model_invocation=disable_model_invocation,
        body=body,
    )


def load_skill_manifest(
    path: Path,
    diagnostics: list[SkillDiagnostic] | None = None,
    scope: SkillScope = SkillScope.PROJECT,
    lenient: bool = False,
) -> SkillManifest | None:
    """Load a skill manifest from a SKILL.md file with YAML frontmatter."""
    skill_md_path = path / "SKILL.md"
    if not skill_md_path.exists():
        return None
    try:
        mtime = skill_md_path.stat().st_mtime
    except OSError:
        return None

    cache_key = f"{skill_md_path.resolve()}:{lenient}"
    cached = _SKILL_MANIFEST_CACHE.get(cache_key)
    if cached is not None and cached[0] == mtime:
        return dataclasses.replace(cached[1]) if cached[1] is not None else None

    manifest = _parse_skill_manifest(
        path, diagnostics=diagnostics, scope=scope, lenient=lenient
    )
    _SKILL_MANIFEST_CACHE[cache_key] = (mtime, manifest)
    return dataclasses.replace(manifest) if manifest is not None else None


def load_skill_manifests(
    skills_dir: Path,
    scope: SkillScope = SkillScope.PROJECT,
    diagnostics: list[SkillDiagnostic] | None = None,
    lenient: bool = False,
) -> list[SkillManifest]:
    """Load all skill manifests from a skills directory."""
    if not skills_dir.exists():
        return []
    manifests: list[SkillManifest] = []
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        diag_len_before = len(diagnostics) if diagnostics is not None else 0
        manifest = load_skill_manifest(
            entry, diagnostics=diagnostics, scope=scope, lenient=lenient
        )
        if manifest is None:
            if diagnostics is not None and len(diagnostics) == diag_len_before:
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
        manifests.append(manifest)
    return manifests


def load_plugin_manifest(
    plugin_dir: Path,
    diagnostics: list[SkillDiagnostic] | None = None,
) -> PluginManifest | None:
    """Load and validate an Agent Plugin manifest (plugin.json) per spec v1.0.0."""
    if not plugin_dir.is_dir():
        return None

    resolved_plugin_dir = plugin_dir.resolve()
    plugin_json_path = (plugin_dir / "plugin.json").resolve()

    if not str(plugin_json_path).startswith(str(resolved_plugin_dir)):
        if diagnostics is not None:
            diagnostics.append(
                SkillDiagnostic(
                    kind=SkillDiagnosticKind.PATH_ESCAPE,
                    skill_name=plugin_dir.name,
                    message=(
                        f"plugin.json in {plugin_dir.name} resolves outside the "
                        "plugin root"
                    ),
                    path=str(plugin_dir),
                )
            )
        return None

    if not plugin_json_path.is_file():
        if diagnostics is not None:
            diagnostics.append(
                SkillDiagnostic(
                    kind=SkillDiagnosticKind.INVALID_PLUGIN,
                    skill_name=plugin_dir.name,
                    message=f"Missing plugin.json manifest in {plugin_dir.name}",
                    path=str(plugin_dir),
                )
            )
        return None

    try:
        raw_text = plugin_json_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except Exception as exc:
        if diagnostics is not None:
            diagnostics.append(
                SkillDiagnostic(
                    kind=SkillDiagnosticKind.INVALID_PLUGIN,
                    skill_name=plugin_dir.name,
                    message=f"Invalid JSON in plugin.json for {plugin_dir.name}: {exc}",
                    path=str(plugin_dir),
                )
            )
        return None

    if not isinstance(data, dict):
        if diagnostics is not None:
            diagnostics.append(
                SkillDiagnostic(
                    kind=SkillDiagnosticKind.INVALID_PLUGIN,
                    skill_name=plugin_dir.name,
                    message=(
                        f"plugin.json root in {plugin_dir.name} must be a JSON object"
                    ),
                    path=str(plugin_dir),
                )
            )
        return None

    schema_val = data.get("$schema")
    if not isinstance(schema_val, str) or "agent-plugins.org" not in schema_val:
        if diagnostics is not None:
            diagnostics.append(
                SkillDiagnostic(
                    kind=SkillDiagnosticKind.INVALID_PLUGIN,
                    skill_name=plugin_dir.name,
                    message=(
                        "Missing or unsupported $schema in plugin.json for "
                        f"{plugin_dir.name}"
                    ),
                    path=str(plugin_dir),
                )
            )
        return None

    name = data.get("name")
    if (
        not isinstance(name, str)
        or not (1 <= len(name) <= 64)
        or not PLUGIN_NAME_REGEX.match(name)
    ):
        if diagnostics is not None:
            diagnostics.append(
                SkillDiagnostic(
                    kind=SkillDiagnosticKind.INVALID_PLUGIN,
                    skill_name=str(name or plugin_dir.name),
                    message=(
                        f"Invalid plugin name '{name}' in plugin.json for "
                        f"{plugin_dir.name}"
                    ),
                    path=str(plugin_dir),
                )
            )
        return None

    version = str(data.get("version", ""))
    description = str(data.get("description", ""))
    raw_author = data.get("author")
    author: dict[str, Any] = dict(raw_author) if isinstance(raw_author, dict) else {}
    homepage = str(data.get("homepage", ""))
    repository = str(data.get("repository", ""))
    license_val = str(data.get("license", ""))
    raw_keywords = data.get("keywords")
    keywords: list[str] = (
        [str(k) for k in raw_keywords] if isinstance(raw_keywords, list) else []
    )
    raw_extensions = data.get("extensions")
    extensions: dict[str, Any] = (
        dict(raw_extensions) if isinstance(raw_extensions, dict) else {}
    )

    return PluginManifest(
        name=name,
        schema=schema_val,
        version=version,
        description=description,
        author=author,
        homepage=homepage,
        repository=repository,
        license=license_val,
        keywords=keywords,
        extensions=extensions,
        path=str(resolved_plugin_dir),
    )


def load_skills_from_paths(
    paths: Sequence[tuple[str | Path, SkillScope]],
    agent_name: str | None = None,
    lenient: bool = False,
) -> tuple[list[SkillLoad], list[SkillDiagnostic]]:
    """Load skills from multiple paths in precedence order (first wins).

    Args:
        paths: List of (path, scope) tuples, paths can include ~ and
            {agent_name} placeholder
        agent_name: Agent name to substitute {agent_name} placeholder
        lenient: Whether to tolerate non-fatal cosmetic name/directory mismatches

    Returns:
        Tuple of (skill_loads, diagnostics). SkillLoads are deduped
        by manifest name (first-wins), with the winner's scope recorded.
    """
    loads: list[SkillLoad] = []
    diagnostics: list[SkillDiagnostic] = []
    seen_names: dict[str, tuple[SkillScope, str]] = {}

    for path_str, scope in paths:
        path = _resolve_search_path(path_str, agent_name)
        if not path.exists():
            continue
        manifests = load_skill_manifests(
            path, scope=scope, diagnostics=diagnostics, lenient=lenient
        )
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


def get_default_skill_paths(
    agent_name: str,
    global_dir: Path | None = None,
) -> list[tuple[Path, SkillScope]]:
    """Get the default skill discovery paths in precedence order (highest first)."""
    result: list[tuple[Path, SkillScope]] = []
    effective_global = (
        global_dir if global_dir is not None else Path("~/.agents").expanduser()
    )
    result.append((Path(".agents/skills"), SkillScope.PROJECT))
    result.append((effective_global / "skills", SkillScope.USER))
    result.append(
        (effective_global / "agents" / (agent_name or "") / "skills", SkillScope.AGENT)
    )
    return result


def discover_plugin_skill_paths(
    cwd: Path | None = None,
    global_dir: Path | None = None,
    diagnostics: list[SkillDiagnostic] | None = None,
) -> list[tuple[Path, SkillScope]]:
    """Discover skill directories inside valid Agent Plugins.

    Discovers plugins in:
    - .agents/plugins/*/skills (PROJECT scope)
    - ~/.agents/plugins/*/skills (USER scope)
    """
    results: list[tuple[Path, SkillScope]] = []
    base_cwd = cwd if cwd is not None else Path.cwd()
    effective_global = (
        global_dir if global_dir is not None else Path("~/.agents").expanduser()
    )

    plugin_candidates: list[tuple[Path, SkillScope]] = [
        (base_cwd / ".agents" / "plugins", SkillScope.PROJECT),
        (effective_global / "plugins", SkillScope.USER),
    ]

    for pdir, scope in plugin_candidates:
        if not pdir.is_dir():
            continue
        for entry in sorted(pdir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            manifest = load_plugin_manifest(entry, diagnostics=diagnostics)
            if manifest is None:
                continue
            skills_sub = entry / "skills"
            if skills_sub.is_dir():
                results.append((skills_sub, scope))

    return results


def get_prioritized_skill_search_paths(
    agent_name: str,
    cwd: Path | None = None,
    global_dir: Path | None = None,
    diagnostics: list[SkillDiagnostic] | None = None,
) -> list[tuple[Path, SkillScope]]:
    """Return all skill discovery paths in strict precedence order (highest first):
    1. Project standalone skills: <cwd>/.agents/skills (PROJECT)
    2. Project plugin skills: <cwd>/.agents/plugins/*/skills (PROJECT)
    3. User standalone skills: ~/.agents/skills or <global_dir>/skills (USER)
    4. User plugin skills: ~/.agents/plugins/*/skills or
       <global_dir>/plugins/*/skills (USER)
    5. Agent standalone skills: ~/.agents/agents/{agent_name}/skills (AGENT)
    """
    effective_cwd = cwd if cwd is not None else Path.cwd()
    effective_global = (
        global_dir if global_dir is not None else Path("~/.agents").expanduser()
    )

    paths: list[tuple[Path, SkillScope]] = [
        (effective_cwd / ".agents" / "skills", SkillScope.PROJECT),
    ]

    # Project plugins
    proj_plugins = effective_cwd / ".agents" / "plugins"
    if proj_plugins.is_dir():
        for p in sorted(proj_plugins.iterdir()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            manifest = load_plugin_manifest(p, diagnostics=diagnostics)
            if manifest is not None and (p / "skills").is_dir():
                paths.append((p / "skills", SkillScope.PROJECT))

    # User standalone
    paths.append((effective_global / "skills", SkillScope.USER))

    # User plugins
    user_plugins = effective_global / "plugins"
    if user_plugins.is_dir():
        for p in sorted(user_plugins.iterdir()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            manifest = load_plugin_manifest(p, diagnostics=diagnostics)
            if manifest is not None and (p / "skills").is_dir():
                paths.append((p / "skills", SkillScope.USER))

    # Agent standalone
    agent_path = effective_global / "agents" / (agent_name or "") / "skills"
    paths.append((agent_path, SkillScope.AGENT))

    # Agent plugins
    agent_plugins = effective_global / "agents" / (agent_name or "") / "plugins"
    if agent_plugins.is_dir():
        for p in sorted(agent_plugins.iterdir()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            manifest = load_plugin_manifest(p, diagnostics=diagnostics)
            if manifest is not None and (p / "skills").is_dir():
                paths.append((p / "skills", SkillScope.AGENT))

    return paths
