from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mvgeos_agent.types import SpellResult, SpellStatus

from coding_mvge.runes.knowledge_skill.proposer_mvge.context import get_proposer_context


def _resolve_safe_path(
    path_str: str,
    knowledge_dir: Path,
    raw_knowledge_dir: Path,
    target_skills_dir: Path | None = None,
    project_skills_dir: Path | None = None,
    available_skills: dict[str, Any] | None = None,
) -> Path | None:
    """Resolve path and verify it stays inside knowledge, raw, or skill directories."""
    clean = path_str.strip().lstrip("/").replace("\\", "/")
    if ".." in clean:
        return None

    # Handle traces/ alias
    if clean.startswith("traces/"):
        rel = clean[len("traces/") :]
        candidate = raw_knowledge_dir / "traces" / rel
        if candidate.exists():
            return candidate
        candidate_raw = raw_knowledge_dir / rel
        if candidate_raw.exists():
            return candidate_raw
        for match in raw_knowledge_dir.rglob(f"*{rel}*"):
            if match.is_file():
                return match
        return candidate

    # Handle skills/ alias (e.g. skills/foo/SKILL.md)
    if clean.startswith("skills/"):
        sub = clean[len("skills/") :]
        parts = sub.split("/", 1)
        sk_name = parts[0]
        file_rel = parts[1] if len(parts) > 1 else "SKILL.md"

        if available_skills and sk_name in available_skills:
            manifest = available_skills[sk_name]
            raw_path = getattr(manifest, "path", None) or (
                manifest.get("path") if isinstance(manifest, dict) else None
            )
            if raw_path:
                sk_dir = Path(raw_path).resolve()
                cand = (sk_dir / file_rel).resolve()
                if cand.is_relative_to(sk_dir) and cand.exists():
                    return cand

        if project_skills_dir:
            cand = (project_skills_dir / sub).resolve()
            if cand.is_relative_to(project_skills_dir) and cand.exists():
                return cand

        if target_skills_dir:
            cand = (target_skills_dir / sub).resolve()
            if cand.is_relative_to(target_skills_dir) and cand.exists():
                return cand

    # Handle knowledge/ alias
    if clean.startswith("knowledge/"):
        clean = clean[len("knowledge/") :]

    target = (knowledge_dir / clean).resolve()
    if target.is_relative_to(knowledge_dir) and target.exists():
        return target

    target_raw = (raw_knowledge_dir / clean).resolve()
    if target_raw.is_relative_to(raw_knowledge_dir) and target_raw.exists():
        return target_raw

    if target.is_relative_to(knowledge_dir):
        return target

    return None


async def read_file(path: str) -> SpellResult:
    """Read a file safely from the persistent knowledge base, traces, or skills.

    Restricted strictly to knowledge/, raw_knowledge/, and discovered skills/.
    Supports reading pattern files (e.g. 'knowledge/patterns/retry.md'),
    raw execution traces (e.g. 'traces/task_123.json'), and skill files
    (e.g. 'skills/foo/SKILL.md').
    """
    ctx = get_proposer_context()
    target = _resolve_safe_path(
        path_str=path,
        knowledge_dir=ctx.knowledge_dir,
        raw_knowledge_dir=ctx.raw_knowledge_dir,
        target_skills_dir=ctx.target_skills_dir,
        project_skills_dir=ctx.project_skills_dir,
        available_skills=ctx.available_skills,
    )
    if target is None:
        return SpellResult(
            spell_name="read_file",
            status=SpellStatus.ERROR,
            error_message=f"Access denied or invalid path: {path!r}",
        )
    if not await asyncio.to_thread(target.exists):
        return SpellResult(
            spell_name="read_file",
            status=SpellStatus.ERROR,
            error_message=f"File not found: {path!r}",
        )
    try:
        content = await asyncio.to_thread(target.read_text, encoding="utf-8")
        return SpellResult(
            spell_name="read_file",
            status=SpellStatus.SUCCESS,
            content=content,
        )
    except Exception as exc:
        return SpellResult(
            spell_name="read_file",
            status=SpellStatus.ERROR,
            error_message=f"Error reading {path!r}: {exc}",
        )
