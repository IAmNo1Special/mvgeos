from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from coding_mvge.runes.skill_evolution.queries import SkillEvolutionQueries
from coding_mvge.runes.skill_evolution.store import SkillEvolutionStore


class SkillPluginExporter:
    def __init__(
        self,
        store: SkillEvolutionStore,
        queries: SkillEvolutionQueries | None = None,
        agent_name: str = "coding_mvge",
    ):
        self.store = store
        self.queries = queries
        self.agent_name = agent_name

    async def export_skills(
        self,
        skill_names: list[str],
        output_dir: str | Path,
        plugin_name: str,
        agent_name: str | None = None,
        include_evolution_refs: bool = True,
    ) -> dict[str, Any]:
        actual_agent = agent_name or self.agent_name
        from mvgeos_runes.loader import SKILL_SCOPES, load_skills_from_paths

        paths = [(p, scope) for scope, p in SKILL_SCOPES]
        expanded = [
            (Path(str(p).replace("{agent_name}", actual_agent)).expanduser(), scope)
            for p, scope in paths
        ]
        loads, _ = load_skills_from_paths(expanded, actual_agent)
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
        if include_evolution_refs:
            kd = output_path / "skill_evolution" / "patterns"
            kd.mkdir(parents=True, exist_ok=True)
            for name in skill_names:
                hits = (
                    await self.store.search(name, limit=5)
                    if hasattr(self.store, "search")
                    else []
                )
                for p in hits:
                    src = (
                        Path(p)
                        if isinstance(p, (str, Path))
                        else self.store.patterns_dir / str(p)
                    )
                    if src.exists():
                        shutil.copy2(src, kd / src.name)
        return {
            "plugin_path": str(output_path),
            "plugin_json": plugin_json,
            "skills_exported": skill_names,
        }

    async def export_spells(self, *a: Any, **kw: Any) -> Any:
        return await self.export_skills(*a, **kw)

    async def export_plugin(self, *a: Any, **kw: Any) -> Any:
        return await self.export_skills(*a, **kw)
