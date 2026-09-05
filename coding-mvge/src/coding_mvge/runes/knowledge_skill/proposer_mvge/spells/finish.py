from __future__ import annotations

import difflib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from mvgeos_agent.types import SpellResult, SpellStatus

from coding_mvge.runes.knowledge_skill.proposer_mvge.context import (
    get_proposer_context,
    record_proposal_result,
)

NAME_REGEX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


async def finish(proposal: dict[str, Any] | str) -> SpellResult:
    """Submit the final skill proposal.

    Validates schema, records the proposal to the skill-impact audit trail,
    and applies changes to the target skills directory if enabled.
    """
    if isinstance(proposal, str):
        try:
            proposal_dict = json.loads(proposal)
        except Exception as exc:
            return SpellResult(
                spell_name="finish",
                status=SpellStatus.ERROR,
                error_message=f"Invalid JSON proposal: {exc}",
            )
    else:
        proposal_dict = proposal

    ctx = get_proposer_context()
    action = proposal_dict.get("action", "")

    if action in ("no_action", "NO_ACTION"):
        res = {"success": True, "action": "no_action"}
        await _record_impact(
            ctx.knowledge_dir,
            {"name": "none", "action": "no_action"},
            diff="",
        )
        record_proposal_result(res)
        return SpellResult(
            spell_name="finish",
            status=SpellStatus.SUCCESS,
            content=json.dumps(res),
        )

    skill_name = proposal_dict.get("name", "")
    if not skill_name or not (1 <= len(skill_name) <= 64):
        return SpellResult(
            spell_name="finish",
            status=SpellStatus.ERROR,
            error_message="name must be non-empty and 1-64 characters",
        )
    if not NAME_REGEX.match(skill_name):
        return SpellResult(
            spell_name="finish",
            status=SpellStatus.ERROR,
            error_message=f"name {skill_name!r} must match ^[a-z0-9]+(-[a-z0-9]+)*$",
        )

    diff = ""
    applied_path: Path | None = None
    applied_scope: str = "agent"
    skill_dir: Path | None = None

    if action == "create":
        skill_md = proposal_dict.get("skill_md", "")
        purpose_md = proposal_dict.get("purpose_md", "")
        if not skill_md or not purpose_md:
            return SpellResult(
                spell_name="finish",
                status=SpellStatus.ERROR,
                error_message="create requires both skill_md and purpose_md",
            )

        target_scope = str(proposal_dict.get("scope", "")).lower()
        if (target_scope == "project" or not target_scope) and ctx.project_skills_dir:
            target_parent = ctx.project_skills_dir
            applied_scope = "project"
        else:
            target_parent = ctx.target_skills_dir
            applied_scope = "agent"

        diff = f"--- /dev/null\n+++ {skill_name}/SKILL.md\n" + "\n".join(
            f"+{line}" for line in skill_md.splitlines()
        )

        if ctx.auto_apply and target_parent:
            skill_dir = target_parent / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
            (skill_dir / "PURPOSE.md").write_text(purpose_md, encoding="utf-8")
            applied_path = skill_dir

    elif action == "patch":
        edits = proposal_dict.get("edits", [])
        if not edits:
            return SpellResult(
                spell_name="finish",
                status=SpellStatus.ERROR,
                error_message="patch requires at least one edit operation",
            )

        manifest = ctx.available_skills.get(skill_name)
        origin_scope: str | None = None
        origin_dir: Path | None = None
        if manifest:
            origin_scope = getattr(manifest, "scope", None) or (
                manifest.get("scope") if isinstance(manifest, dict) else None
            )
            raw_path = getattr(manifest, "path", None) or (
                manifest.get("path") if isinstance(manifest, dict) else None
            )
            if raw_path:
                origin_dir = Path(raw_path).resolve()

        fork_to_project = bool(
            proposal_dict.get("fork_to_project")
            or str(proposal_dict.get("scope", "")).lower() == "project"
        )

        skill_dir = None
        # Fork user skill to project if project specialization requested
        if (
            origin_dir
            and origin_scope
            and str(origin_scope).lower() == "user"
            and fork_to_project
            and ctx.project_skills_dir
        ):
            skill_dir = ctx.project_skills_dir / skill_name
            if not skill_dir.exists() and origin_dir.exists():
                shutil.copytree(origin_dir, skill_dir, dirs_exist_ok=True)
            applied_scope = "project"
        elif origin_dir and (origin_dir / "SKILL.md").exists():
            skill_dir = origin_dir
            applied_scope = str(origin_scope).lower() if origin_scope else "unknown"
        elif (
            ctx.project_skills_dir
            and (ctx.project_skills_dir / skill_name / "SKILL.md").exists()
        ):
            skill_dir = ctx.project_skills_dir / skill_name
            applied_scope = "project"
        elif (
            ctx.target_skills_dir
            and (ctx.target_skills_dir / skill_name / "SKILL.md").exists()
        ):
            skill_dir = ctx.target_skills_dir / skill_name
            applied_scope = "agent"

        if not skill_dir or not (skill_dir / "SKILL.md").exists():
            return SpellResult(
                spell_name="finish",
                status=SpellStatus.ERROR,
                error_message=f"Skill {skill_name!r} not found for patching",
            )

        sk_path = skill_dir / "SKILL.md"
        original_text = sk_path.read_text(encoding="utf-8")
        patched_text = original_text

        for edit in edits:
            op = edit.get("op")
            tgt = edit.get("target")
            content = edit.get("content", "")
            if op == "append":
                patched_text += content
            elif op == "replace":
                if tgt is None or tgt not in patched_text:
                    return SpellResult(
                        spell_name="finish",
                        status=SpellStatus.ERROR,
                        error_message=f"replace target not found: {tgt!r}",
                    )
                patched_text = patched_text.replace(tgt, content, 1)
            elif op == "insert_after":
                if tgt is None or tgt not in patched_text:
                    return SpellResult(
                        spell_name="finish",
                        status=SpellStatus.ERROR,
                        error_message=f"insert_after target not found: {tgt!r}",
                    )
                idx = patched_text.index(tgt) + len(tgt)
                patched_text = patched_text[:idx] + content + patched_text[idx:]
            else:
                return SpellResult(
                    spell_name="finish",
                    status=SpellStatus.ERROR,
                    error_message=f"Unknown patch op {op!r}",
                )

        diff_lines = list(
            difflib.unified_diff(
                original_text.splitlines(keepends=True),
                patched_text.splitlines(keepends=True),
                fromfile=f"a/{skill_name}/SKILL.md",
                tofile=f"b/{skill_name}/SKILL.md",
            )
        )
        diff = "".join(diff_lines)

        if ctx.auto_apply:
            sk_path.write_text(patched_text, encoding="utf-8")
            applied_path = skill_dir
    else:
        return SpellResult(
            spell_name="finish",
            status=SpellStatus.ERROR,
            error_message=f"Unknown proposal action {action!r}",
        )

    await _record_impact(
        ctx.knowledge_dir,
        {"name": skill_name, "action": action, "scope": applied_scope},
        diff=diff,
    )

    result_payload = {
        "success": True,
        "action": action,
        "name": skill_name,
        "scope": applied_scope,
        "diff": diff,
        "path": str(applied_path) if applied_path else None,
    }
    record_proposal_result(result_payload)
    return SpellResult(
        spell_name="finish",
        status=SpellStatus.SUCCESS,
        content=json.dumps(result_payload),
    )


async def _record_impact(
    knowledge_dir: Path, proposal: dict[str, Any], diff: str
) -> None:
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    impact_file = knowledge_dir / "skill-impact.md"
    scope_str = f" [{proposal.get('scope')}]" if proposal.get("scope") else ""
    entry = (
        f"\n## [{proposal.get('action')}]{scope_str} {proposal.get('name')}\n"
        f"- Status: Accepted\n"
        f"- Diff:\n```diff\n{diff}\n```\n"
    )
    if impact_file.exists():
        existing = impact_file.read_text(encoding="utf-8")
        impact_file.write_text(existing + entry, encoding="utf-8")
    else:
        impact_file.write_text(f"# Skill Impact Audit Trail\n{entry}", encoding="utf-8")
