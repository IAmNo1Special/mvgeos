from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from coding_mvge.runes.knowledge_skill.knowledge.queries import KnowledgeQueries
from coding_mvge.runes.knowledge_skill.knowledge.store import KnowledgeStore


class PluginExporter:
    def __init__(self, knowledge: KnowledgeStore, queries: KnowledgeQueries):
        self.knowledge = knowledge
        self.queries = queries

    async def export_skills(
        self,
        skill_names: list[str],
        output_dir: Path,
        plugin_name: str,
        agent_name: str,
        include_knowledge_refs: bool = True,
    ) -> Path:
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
            raise ValueError(f"skills not found: {missing}")
        output_path = Path(output_dir).expanduser() / plugin_name
        output_path.mkdir(parents=True, exist_ok=True)
        skills_dir = output_path / "skills"
        skills_dir.mkdir(exist_ok=True)
        plugin_skills = []
        for name in skill_names:
            src_dir = Path(by_name[name].manifest.path)
            dst_dir = skills_dir / src_dir.name
            if dst_dir.exists():
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
            plugin_skills.append({"name": name, "path": f"skills/{dst_dir.name}"})
        plugin_json = {
            "name": plugin_name,
            "version": "1.0.0",
            "description": f"Exported skills: {', '.join(skill_names)}",
            "skills": plugin_skills,
            "mcp_servers": [],
            "dependencies": {"python": ">=3.10"},
        }
        (output_path / "plugin.json").write_text(
            json.dumps(plugin_json, indent=2), encoding="utf-8"
        )
        if include_knowledge_refs:
            kd = output_path / "knowledge" / "patterns"
            kd.mkdir(parents=True, exist_ok=True)
            for name in skill_names:
                hits = (
                    await self.knowledge.search(name, limit=5)
                    if hasattr(self.knowledge, "search")
                    else []
                )
                for p in hits:
                    src = Path(p)
                    if src.exists():
                        shutil.copy2(src, kd / src.name)
        return output_path

    async def export_spells(self, *a: Any, **kw: Any) -> Any:
        return await self.export_skills(*a, **kw)
