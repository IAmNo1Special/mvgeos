from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from mvgeos_agent import Mvge

from coding_mvge.runes.skill_evolution.engine import SkillEvolutionEngine
from coding_mvge.runes.skill_evolution.proposer_mvge.spells.finish import (
    get_active_engine,
    make_finish_spell,
    set_active_engine,
)
from coding_mvge.runes.skill_evolution.proposer_mvge.spells.read_file import (
    make_read_file_spell,
)

PROPOSER_DIR = Path(__file__).resolve().parent


@contextmanager
def scoped_proposer_context(
    engine: SkillEvolutionEngine | None = None,
    *,
    evolution_dir: Path | None = None,
    raw_experience_dir: Path | None = None,
    target_skills_dir: Path | None = None,
    project_skills_dir: Path | None = None,
    available_skills: dict[str, Any] | list[Any] | None = None,
    auto_apply: bool = True,
    # Support legacy param names in tests for seamless migration
    knowledge_dir: Path | None = None,
    raw_knowledge_dir: Path | None = None,
) -> Iterator[SkillEvolutionEngine]:
    """Context manager for scoping a SkillEvolutionEngine to the current
    async context."""
    if engine is None:
        evo_dir = (
            evolution_dir or knowledge_dir or Path(".agents/.mvgeos/skill_evolution")
        )
        raw_dir = (
            raw_experience_dir
            or raw_knowledge_dir
            or Path(".agents/.mvgeos/raw_experience")
        )
        skills_dir = target_skills_dir or Path(".agents/skills")
        engine = SkillEvolutionEngine(
            evolution_dir=evo_dir,
            raw_experience_dir=raw_dir,
            target_skills_dir=skills_dir,
            project_skills_dir=project_skills_dir,
            available_skills=available_skills,
            auto_apply=auto_apply,
        )
    prev = get_active_engine()
    set_active_engine(engine)
    try:
        yield engine
    finally:
        set_active_engine(prev)


def create_proposer_mvge(
    engine: SkillEvolutionEngine | None = None,
    api_key: str | None = None,
    provider_name: str | None = None,
    **kwargs: Any,
) -> Mvge:
    """Create a standalone Proposer Mvge instance via file-based construction."""
    spells = kwargs.pop("spells", None)
    if spells is None and engine is not None:
        spells = [make_finish_spell(engine), make_read_file_spell(engine)]
    return Mvge(
        name="proposer_mvge",
        api_key=api_key,
        provider_name=provider_name,
        caller_dir=PROPOSER_DIR,
        spells=spells,
        **kwargs,
    )


proposer_mvge = create_proposer_mvge()


async def run_proposer(
    mvge: Mvge | None = None,
    *,
    engine: SkillEvolutionEngine | None = None,
    evolution_dir: Path | None = None,
    raw_experience_dir: Path | None = None,
    target_skills_dir: Path | None = None,
    project_skills_dir: Path | None = None,
    available_skills: dict[str, Any] | list[Any] | None = None,
    auto_apply: bool = True,
    user_prompt: str | None = None,
    # Legacy kwargs for compatibility
    knowledge_dir: Path | None = None,
    raw_knowledge_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the Proposer Mvge to generate a skill proposal."""
    agent = mvge or proposer_mvge

    if engine is None:
        active = get_active_engine()
        if active is not None:
            engine = active
            engine.auto_apply = auto_apply
            if available_skills is not None:
                engine.available_skills = engine._normalize_skills(available_skills)
        else:
            evo_dir = (
                evolution_dir
                or knowledge_dir
                or Path(".agents/.mvgeos/skill_evolution")
            )
            raw_dir = (
                raw_experience_dir
                or raw_knowledge_dir
                or Path(".agents/.mvgeos/raw_experience")
            )
            skills_dir = target_skills_dir or Path(".agents/skills")
            engine = SkillEvolutionEngine(
                evolution_dir=evo_dir,
                raw_experience_dir=raw_dir,
                target_skills_dir=skills_dir,
                project_skills_dir=project_skills_dir,
                available_skills=available_skills,
                auto_apply=auto_apply,
            )

    set_active_engine(engine)
    engine.reset_latest_proposal()

    # Bind spells to engine on the agent instance
    agent._spells = [make_finish_spell(engine), make_read_file_spell(engine)]
    if agent._state is not None:
        agent._state.spells = agent._build_spells()

    if user_prompt is None:
        index_file = engine.evolution_dir / "index.md"
        impact_file = engine.evolution_dir / "skill-impact.md"
        logs_file = engine.evolution_dir / "logs.md"

        index_text = (
            index_file.read_text(encoding="utf-8")
            if index_file.exists()
            else "No index."
        )
        impact_text = (
            impact_file.read_text(encoding="utf-8")
            if impact_file.exists()
            else "No past proposals."
        )
        logs_text = (
            logs_file.read_text(encoding="utf-8") if logs_file.exists() else "No logs."
        )

        skills_summary = []
        for name, sk in engine.available_skills.items():
            scope = getattr(sk, "scope", None) or (
                sk.get("scope") if isinstance(sk, dict) else "unknown"
            )
            desc = getattr(sk, "description", "") or (
                sk.get("description", "") if isinstance(sk, dict) else ""
            )
            skills_summary.append(f"- {name} [{scope}]: {desc}")
        skills_text = (
            "\n".join(skills_summary) if skills_summary else "None registered."
        )

        user_prompt = (
            f"KNOWLEDGE INDEX:\n{index_text}\n\n"
            f"SKILL IMPACT AUDIT TRAIL:\n{impact_text}\n\n"
            f"AVAILABLE DISCOVERED SKILLS (BY SCOPE):\n{skills_text}\n\n"
            f"TRAINING SUMMARY:\n{logs_text[-2000:]}\n\n"
            "Analyze knowledge patterns and traces. Call finish() with your proposal."
        )

    invocation = await agent.run(user_prompt)

    latest_proposal = engine.get_latest_proposal()
    if latest_proposal is not None:
        return latest_proposal

    response_text = ""
    if hasattr(invocation, "content"):
        content = getattr(invocation, "content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    response_text += block.get("text", "")
                elif isinstance(block, str):
                    response_text += block
        elif isinstance(content, str):
            response_text = content
    elif hasattr(invocation, "text"):
        response_text = getattr(invocation, "text", "")

    # If finish spell wasn't executed directly, extract JSON from invocation
    # text if present
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
            res = {"success": True, **parsed}
            engine.latest_proposal = res
            return res
        except Exception:
            pass

    return {"success": True, "action": "no_action", "content": response_text}


__all__ = [
    "PROPOSER_DIR",
    "create_proposer_mvge",
    "proposer_mvge",
    "run_proposer",
    "scoped_proposer_context",
]
