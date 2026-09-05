from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from mvgeos_runes.types import ExecutionMode, SpellDefinition


async def execute(
    params: dict[str, Any], signal: Any, on_update: Any, knowledge: Any, agent_name: str
) -> dict[str, Any]:
    skill_names = params.get("skill_names", [])
    output_dir = params.get("output_dir", "")
    plugin_name = params.get("plugin_name", "")
    include_knowledge_refs = params.get(
        "include_knowledge_refs", params.get("include_wiki_refs", True)
    )
    if not skill_names:
        return {"error": "skill_names required"}
    if not output_dir:
        return {"error": "output_dir required"}
    if not plugin_name:
        return {"error": "plugin_name required"}
    from mvgeos_runes.loader import SKILL_SCOPES, load_skills_from_paths

    paths = [(p, scope) for scope, p in SKILL_SCOPES]
    expanded = [
        (Path(str(p).replace("{agent_name}", agent_name)).expanduser(), scope)
        for p, scope in paths
    ]
    loads, _ = load_skills_from_paths(expanded, agent_name)
    by_name = {item.manifest.name: item for item in loads}
    missing = [n for n in skill_names if n not in by_name]
    if missing:
        return {
            "error": f"skills not found: {missing}",
            "available": list(by_name.keys())[:20],
        }
    output_path = Path(output_dir).expanduser() / plugin_name
    output_path.mkdir(parents=True, exist_ok=True)
    skills_dir = output_path / "skills"
    skills_dir.mkdir(exist_ok=True)
    plugin_skills = []
    for name in skill_names:
        load = by_name[name]
        src_dir = Path(load.manifest.path)
        dst_dir = skills_dir / src_dir.name
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        shutil.copytree(src_dir, dst_dir)
        plugin_skills.append({"name": name, "path": f"skills/{dst_dir.name}"})
    plugin_json = {
        "name": plugin_name,
        "version": "1.0.0",
        "description": f"Exported skills from knowledge: {', '.join(skill_names)}",
        "skills": plugin_skills,
        "mcp_servers": [],
        "dependencies": {"python": ">=3.10"},
    }
    (output_path / "plugin.json").write_text(
        json.dumps(plugin_json, indent=2), encoding="utf-8"
    )
    if include_knowledge_refs and hasattr(knowledge, "patterns_dir"):
        kd = output_path / "knowledge" / "patterns"
        kd.mkdir(parents=True, exist_ok=True)
        for name in skill_names:
            hits = (
                await knowledge.search(name, limit=5)
                if hasattr(knowledge, "search")
                else []
            )
            for p in hits:
                src = (
                    Path(p)
                    if isinstance(p, (str, Path))
                    else knowledge.patterns_dir / str(p)
                )
                if src.exists():
                    shutil.copy2(src, kd / src.name)
    return {
        "plugin_path": str(output_path),
        "plugin_json": plugin_json,
        "skills_exported": skill_names,
    }


SPELL = SpellDefinition(
    name="export_skill_plugin",
    description=(
        "Package existing skills (SkillManifest dirs) as an Agent Plugin "
        "(plugin.json). Exports from their resolved SkillManifest.path, "
        "preserving scope."
    ),
    parameters={
        "type": "object",
        "properties": {
            "skill_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Skill names (must match directory/frontmatter, "
                    "discovered via SKILL_SCOPES)"
                ),
            },
            "output_dir": {"type": "string"},
            "plugin_name": {"type": "string"},
            "include_knowledge_refs": {"type": "boolean"},
        },
        "required": ["skill_names", "output_dir", "plugin_name"],
    },
    execution_mode=ExecutionMode.SEQUENTIAL,
    prompt_snippet=(
        "Export skills as portable .agents plugin (plugin.json + skill dirs) "
        "from their existing locations."
    ),
    source_rune="knowledge_skill",
)
