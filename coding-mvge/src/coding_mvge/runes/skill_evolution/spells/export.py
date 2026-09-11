from __future__ import annotations

from typing import Any

from mvgeos_core.spells import ExecutionMode
from mvgeos_runes.types import SpellDefinition

from coding_mvge.runes.skill_evolution.export.plugin_exporter import SkillPluginExporter


def make_export_spell(store: Any, agent_name: str) -> SpellDefinition:
    exporter = SkillPluginExporter(store=store, agent_name=agent_name)

    async def execute(
        params: dict[str, Any], signal: Any = None, on_update: Any = None
    ) -> dict[str, Any]:
        skill_names = params.get("skill_names", [])
        output_dir = params.get("output_dir", "")
        plugin_name = params.get("plugin_name", "")
        include_refs = params.get(
            "include_evolution_refs",
            params.get("include_knowledge_refs", params.get("include_wiki_refs", True)),
        )
        if not skill_names:
            return {"error": "skill_names required"}
        if not output_dir:
            return {"error": "output_dir required"}
        if not plugin_name:
            return {"error": "plugin_name required"}

        return await exporter.export_skills(
            skill_names=skill_names,
            output_dir=output_dir,
            plugin_name=plugin_name,
            agent_name=agent_name,
            include_evolution_refs=include_refs,
        )

    return SpellDefinition(
        name="skill_evolution_export",
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
                "include_evolution_refs": {"type": "boolean"},
            },
            "required": ["skill_names", "output_dir", "plugin_name"],
        },
        execution_mode=ExecutionMode.SEQUENTIAL,
        prompt_snippet=(
            "Export skills as portable .agents plugin (plugin.json + skill dirs) "
            "from their existing locations."
        ),
        source_rune="skill_evolution",
        handler=execute,
    )
