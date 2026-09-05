from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mvgeos_agent import Mvge

from coding_mvge.runes.knowledge_skill.proposer_mvge.context import (
    get_latest_proposal,
    get_proposer_context,
    record_proposal_result,
    set_proposer_context,
)

PROPOSER_DIR = Path(__file__).resolve().parent


def create_proposer_mvge(
    api_key: str | None = None,
    provider_name: str | None = None,
    **kwargs: Any,
) -> Mvge:
    """Create a standalone Proposer Mvge instance via file-based construction."""
    return Mvge(
        name="proposer_mvge",
        api_key=api_key,
        provider_name=provider_name,
        caller_dir=PROPOSER_DIR,
        **kwargs,
    )


proposer_mvge = create_proposer_mvge()


async def run_proposer(
    mvge: Mvge | None = None,
    *,
    knowledge_dir: Path | None = None,
    raw_knowledge_dir: Path | None = None,
    target_skills_dir: Path | None = None,
    project_skills_dir: Path | None = None,
    available_skills: dict[str, Any] | list[Any] | None = None,
    auto_apply: bool = True,
    user_prompt: str | None = None,
) -> dict[str, Any]:
    """Execute the Proposer Mvge to generate a skill proposal."""
    agent = mvge or proposer_mvge

    if (
        knowledge_dir is not None
        or raw_knowledge_dir is not None
        or target_skills_dir is not None
        or project_skills_dir is not None
        or available_skills is not None
    ):
        set_proposer_context(
            knowledge_dir=knowledge_dir,
            raw_knowledge_dir=raw_knowledge_dir,
            target_skills_dir=target_skills_dir,
            project_skills_dir=project_skills_dir,
            available_skills=available_skills,
            auto_apply=auto_apply,
        )
    else:
        ctx = get_proposer_context()
        ctx.auto_apply = auto_apply

    ctx = get_proposer_context()
    ctx.latest_proposal = None
    if user_prompt is None:
        index_file = ctx.knowledge_dir / "index.md"
        impact_file = ctx.knowledge_dir / "skill-impact.md"
        logs_file = ctx.knowledge_dir / "logs.md"

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
        for name, sk in ctx.available_skills.items():
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

    proposal_result = get_latest_proposal()
    if proposal_result is not None:
        return proposal_result

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

    # If finish spell wasn't executed directly, extract JSON
    # from invocation text if present
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
            res = {"success": True, **parsed}
            record_proposal_result(res)
            return res
        except Exception:
            pass

    return {"success": True, "action": "no_action", "content": response_text}


__all__ = ["PROPOSER_DIR", "create_proposer_mvge", "proposer_mvge", "run_proposer"]
