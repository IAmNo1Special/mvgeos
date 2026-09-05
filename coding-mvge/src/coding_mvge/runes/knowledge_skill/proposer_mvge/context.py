from __future__ import annotations

import contextlib
import dataclasses
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any


@dataclasses.dataclass
class ProposerContext:
    knowledge_dir: Path
    raw_knowledge_dir: Path
    target_skills_dir: Path
    project_skills_dir: Path | None = None
    available_skills: dict[str, Any] = dataclasses.field(default_factory=dict)
    auto_apply: bool = True
    latest_proposal: dict[str, Any] | None = None


def _default_paths() -> ProposerContext:
    base = Path(
        os.environ.get("MVGEOS_AGENT_CONFIG_DIR", "~/.agents/.mvgeos/coding_mvge")
    ).expanduser()

    k_env = os.environ.get("MVGEOS_KNOWLEDGE_DIR")
    k_dir = (
        Path(k_env).expanduser().resolve() if k_env else (base / "knowledge").resolve()
    )
    r_env = os.environ.get("MVGEOS_RAW_KNOWLEDGE_DIR")
    r_dir = (
        Path(r_env).expanduser().resolve()
        if r_env
        else (base / "raw_knowledge").resolve()
    )

    skills_env = os.environ.get("MVGEOS_TARGET_SKILLS_DIR")
    if skills_env:
        t_dir = Path(skills_env).expanduser().resolve()
    else:
        t_dir = (base / "skills").resolve()

    p_skills_env = os.environ.get("MVGEOS_PROJECT_SKILLS_DIR")
    p_dir: Path | None = None
    if p_skills_env:
        p_dir = Path(p_skills_env).expanduser().resolve()
    elif Path(".agents/skills").is_dir():
        p_dir = Path(".agents/skills").resolve()

    return ProposerContext(
        knowledge_dir=k_dir,
        raw_knowledge_dir=r_dir,
        target_skills_dir=t_dir,
        project_skills_dir=p_dir,
        available_skills={},
        auto_apply=True,
    )


_GLOBAL_CONTEXT = _default_paths()


def get_proposer_context() -> ProposerContext:
    return _GLOBAL_CONTEXT


def set_proposer_context(
    knowledge_dir: Path | None = None,
    raw_knowledge_dir: Path | None = None,
    target_skills_dir: Path | None = None,
    project_skills_dir: Path | None = None,
    available_skills: dict[str, Any] | list[Any] | None = None,
    auto_apply: bool = True,
) -> ProposerContext:
    global _GLOBAL_CONTEXT
    ctx = _GLOBAL_CONTEXT
    if knowledge_dir is not None:
        ctx.knowledge_dir = Path(knowledge_dir).expanduser().resolve()
    if raw_knowledge_dir is not None:
        ctx.raw_knowledge_dir = Path(raw_knowledge_dir).expanduser().resolve()
    if target_skills_dir is not None:
        ctx.target_skills_dir = Path(target_skills_dir).expanduser().resolve()
    if project_skills_dir is not None:
        ctx.project_skills_dir = Path(project_skills_dir).expanduser().resolve()
    if available_skills is not None:
        if isinstance(available_skills, list):
            skills_dict: dict[str, Any] = {}
            for item in available_skills:
                name = getattr(item, "name", None)
                if name:
                    skills_dict[name] = item
                elif isinstance(item, dict) and "name" in item:
                    skills_dict[item["name"]] = item
            ctx.available_skills = skills_dict
        elif isinstance(available_skills, dict):
            ctx.available_skills = available_skills
    ctx.auto_apply = auto_apply
    return ctx


@contextlib.contextmanager
def scoped_proposer_context(
    knowledge_dir: Path | None = None,
    raw_knowledge_dir: Path | None = None,
    target_skills_dir: Path | None = None,
    project_skills_dir: Path | None = None,
    available_skills: dict[str, Any] | list[Any] | None = None,
    auto_apply: bool = True,
) -> Iterator[ProposerContext]:
    global _GLOBAL_CONTEXT
    old_ctx = dataclasses.replace(
        _GLOBAL_CONTEXT,
        available_skills=dict(_GLOBAL_CONTEXT.available_skills),
    )
    set_proposer_context(
        knowledge_dir=knowledge_dir,
        raw_knowledge_dir=raw_knowledge_dir,
        target_skills_dir=target_skills_dir,
        project_skills_dir=project_skills_dir,
        available_skills=available_skills,
        auto_apply=auto_apply,
    )
    try:
        yield _GLOBAL_CONTEXT
    finally:
        _GLOBAL_CONTEXT = old_ctx


def record_proposal_result(proposal: dict[str, Any]) -> None:
    _GLOBAL_CONTEXT.latest_proposal = proposal


def get_latest_proposal() -> dict[str, Any] | None:
    return _GLOBAL_CONTEXT.latest_proposal
