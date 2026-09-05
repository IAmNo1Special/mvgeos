from __future__ import annotations

# MvgeOS implementation of WikiSkill (arxiv:2608.27454) — uses "knowledge"
# throughout (paper's "wiki" -> "knowledge").
# Three-layer: raw_knowledge -> knowledge -> skills (SKILL.md+PURPOSE.md).
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from mvgeos_runes.rune_api import RuneAPI
from mvgeos_runes.types import RuneContext, SigilHook

from coding_mvge.runes.knowledge_skill.consolidator.consolidator import (
    KnowledgeConsolidator,
)
from coding_mvge.runes.knowledge_skill.consolidator.harvester import ExperienceHarvester
from coding_mvge.runes.knowledge_skill.hooks.handlers import KnowledgeHooks
from coding_mvge.runes.knowledge_skill.knowledge.queries import KnowledgeQueries
from coding_mvge.runes.knowledge_skill.knowledge.store import KnowledgeStore
from coding_mvge.runes.knowledge_skill.proposer_mvge import (
    create_proposer_mvge,
    run_proposer,
)
from coding_mvge.runes.knowledge_skill.spells import (
    make_consolidate_spell,
    make_export_spell,
)


def rune_factory(api: RuneAPI) -> None:
    context: RuneContext = api._runner.context
    agent_name = context.agent_name or "coding_mvge"
    api_key = (
        (
            context.api_key
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("MVGEOS_API_KEY")
        )
        if context.mode != "test"
        else None
    )
    config_base = Path(f"~/.agents/.mvgeos/{agent_name}").expanduser()

    # Workspace-aware partitioning in agent scope to prevent cross-project pollution
    cwd_path = Path(context.cwd).resolve() if context.cwd else None
    is_project = bool(
        cwd_path
        and (
            (cwd_path / ".agents").is_dir()
            or (cwd_path / ".git").is_dir()
            or (cwd_path / "pyproject.toml").is_file()
        )
    )

    if is_project and cwd_path:
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", cwd_path.name) or "workspace"
        path_hash = hashlib.sha256(str(cwd_path).encode("utf-8")).hexdigest()[:8]
        ws_slug = f"{clean_name}-{path_hash}"
        knowledge_dir = config_base / "workspaces" / ws_slug / "knowledge"
        raw_knowledge_dir = config_base / "workspaces" / ws_slug / "raw_knowledge"
        project_skills_dir: Path | None = cwd_path / ".agents" / "skills"
    else:
        knowledge_dir = config_base / "knowledge"
        raw_knowledge_dir = config_base / "raw_knowledge"
        project_skills_dir = None

    raw_knowledge_dir.mkdir(parents=True, exist_ok=True)
    target_skills_dir = config_base / "skills"
    knowledge = KnowledgeStore(knowledge_dir)
    knowledge.bind_raw_knowledge(raw_knowledge_dir)
    queries = KnowledgeQueries(knowledge)
    harvester = ExperienceHarvester(
        max_buffer_size=100, persist_path=knowledge_dir / "harvester_buffer.json"
    )
    consolidator = KnowledgeConsolidator(
        knowledge_store=knowledge,
        knowledge_queries=queries,
        harvester=harvester,
        batch_size=20,
        interval_turns=5,
        llm_client=None,
        llm_model="openrouter/auto",
        api_key=api_key,
    )
    subagent_mvge = create_proposer_mvge(api_key=api_key)
    subagent_mvge.event_bus.subscribe(lambda ev: api.emit_event("mvge_event", ev))

    class SubagentRunner:
        async def run(self, auto_apply: bool = True) -> dict[str, Any]:
            return await run_proposer(
                mvge=subagent_mvge,
                knowledge_dir=knowledge_dir,
                raw_knowledge_dir=raw_knowledge_dir,
                target_skills_dir=target_skills_dir,
                project_skills_dir=project_skills_dir,
                available_skills=api.get_skills(),
                auto_apply=auto_apply,
            )

    subagent = SubagentRunner()
    hooks = KnowledgeHooks(harvester, consolidator, knowledge, subagent=subagent)
    hooks.bind_raw(raw_knowledge_dir)
    hooks.register(api)
    api.register_spell(make_consolidate_spell(consolidator))
    api.register_spell(make_export_spell(knowledge, agent_name))
    api.register_command(
        name="knowledge-consolidate",
        description="Force knowledge consolidation",
        handler=lambda _: api._runner.send_message(
            "[knowledge] Consolidation triggered"
        ),
    )
    api.register_command(
        name="knowledge-export",
        description="Export skills as plugin",
        handler=lambda _: api._runner.send_message("[knowledge] Export initiated"),
    )
    api.register_command(
        name="knowledge-stats",
        description="Show knowledge stats",
        handler=lambda _: api._runner.send_message("[knowledge] Stats requested"),
    )

    async def handle_propose(args: Any = None) -> None:
        api.send_message("[knowledge] Skill Proposer sub-agent launched...")
        res = await subagent.run(auto_apply=True)
        if res.get("success"):
            action = res.get("action", "no_action")
            name = res.get("name", "")
            api.send_message(
                f"[knowledge] Skill proposal complete: {action} {name}".strip()
            )
        else:
            api.send_message(f"[knowledge] Skill proposal failed: {res.get('error')}")

    api.register_command(
        name="knowledge-propose",
        description="Run autonomous Skill Proposer sub-agent",
        handler=handle_propose,
    )
    setattr(api._runner, "_knowledge_store", knowledge)  # noqa: B010
    setattr(api._runner, "_knowledge_consolidator", consolidator)  # noqa: B010
    setattr(api._runner, "_knowledge_harvester", harvester)  # noqa: B010
    setattr(api._runner, "_skill_proposer_subagent", subagent)  # noqa: B010

    async def on_agent_start(data: Any) -> None:
        pass

    api.on(SigilHook.AGENT_START, on_agent_start)


def set_llm_client(
    runner: Any, llm_client: Any, model: str = "openrouter/auto"
) -> None:
    target = getattr(runner, "_knowledge_consolidator", None)
    if target is not None:
        target.llm_client = llm_client
        target.llm_model = model
    sub = getattr(runner, "_skill_proposer_subagent", None)
    if sub is not None:
        sub.llm_client = llm_client
        sub.llm_model = model
