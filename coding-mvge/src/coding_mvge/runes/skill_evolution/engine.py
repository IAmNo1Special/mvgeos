from __future__ import annotations

import difflib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from mvgeos_agent.types import SpellResult, SpellStatus

from coding_mvge.runes.skill_evolution.models import SkillEvolutionResult

NAME_REGEX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillEvolutionEngine:
    """Deep module for executing skill proposals, mutations, diffs, and audit logs.

    Encapsulates schema validation, directory scoping, patch operations, unified diff
    generation, impact recording, and restricted file reading behind a clean seam.
    """

    def __init__(
        self,
        evolution_dir: Path,
        raw_experience_dir: Path,
        target_skills_dir: Path,
        project_skills_dir: Path | None = None,
        available_skills: dict[str, Any] | list[Any] | None = None,
        auto_apply: bool = True,
    ) -> None:
        self.evolution_dir = Path(evolution_dir).expanduser().resolve()
        self.raw_experience_dir = Path(raw_experience_dir).expanduser().resolve()
        self.target_skills_dir = Path(target_skills_dir).expanduser().resolve()
        self.project_skills_dir = (
            Path(project_skills_dir).expanduser().resolve()
            if project_skills_dir
            else None
        )
        self.available_skills = self._normalize_skills(available_skills)
        self.auto_apply = auto_apply
        self.latest_proposal: dict[str, Any] | None = None

    def reset_latest_proposal(self) -> None:
        self.latest_proposal = None

    def get_latest_proposal(self) -> dict[str, Any] | None:
        return self.latest_proposal

    @staticmethod
    def _normalize_skills(
        skills: dict[str, Any] | list[Any] | None,
    ) -> dict[str, Any]:
        if not skills:
            return {}
        if isinstance(skills, dict):
            return dict(skills)
        result: dict[str, Any] = {}
        for item in skills:
            name = getattr(item, "name", None)
            if name:
                result[name] = item
            elif isinstance(item, dict) and "name" in item:
                result[item["name"]] = item
        return result

    def resolve_safe_path(self, path_str: str) -> Path | None:
        """Resolve path and verify it stays strictly inside evolution, traces,
        or skills."""
        clean = path_str.strip().lstrip("/").replace("\\", "/")
        if ".." in clean:
            return None

        # Handle traces/ alias
        if clean.startswith("traces/"):
            rel = clean[len("traces/") :]
            candidate = self.raw_experience_dir / "traces" / rel
            if candidate.exists():
                return candidate
            candidate_raw = self.raw_experience_dir / rel
            if candidate_raw.exists():
                return candidate_raw
            for match in self.raw_experience_dir.rglob(f"*{rel}*"):
                if match.is_file():
                    return match
            return candidate

        # Handle skills/ alias (e.g. skills/foo/SKILL.md)
        if clean.startswith("skills/"):
            sub = clean[len("skills/") :]
            parts = sub.split("/", 1)
            sk_name = parts[0]
            file_rel = parts[1] if len(parts) > 1 else "SKILL.md"

            if self.available_skills and sk_name in self.available_skills:
                manifest = self.available_skills[sk_name]
                raw_path = getattr(manifest, "path", None) or (
                    manifest.get("path") if isinstance(manifest, dict) else None
                )
                if raw_path:
                    sk_dir = Path(raw_path).resolve()
                    cand = (sk_dir / file_rel).resolve()
                    if cand.is_relative_to(sk_dir) and cand.exists():
                        return cand

            if self.project_skills_dir:
                cand = (self.project_skills_dir / sub).resolve()
                if cand.is_relative_to(self.project_skills_dir) and cand.exists():
                    return cand

            if self.target_skills_dir:
                cand = (self.target_skills_dir / sub).resolve()
                if cand.is_relative_to(self.target_skills_dir) and cand.exists():
                    return cand

        # Handle skill_evolution/ or legacy knowledge/ alias
        if clean.startswith("skill_evolution/"):
            clean = clean[len("skill_evolution/") :]
        elif clean.startswith("knowledge/"):
            clean = clean[len("knowledge/") :]

        target = (self.evolution_dir / clean).resolve()
        if target.is_relative_to(self.evolution_dir) and target.exists():
            return target

        target_raw = (self.raw_experience_dir / clean).resolve()
        if target_raw.is_relative_to(self.raw_experience_dir) and target_raw.exists():
            return target_raw

        if target.is_relative_to(self.evolution_dir):
            return target

        return None

    async def read_file(self, path: str) -> SpellResult:
        """Safely read a file within evolution store, traces, or skills."""
        target = self.resolve_safe_path(path)
        if target is None or not target.exists() or not target.is_file():
            return SpellResult(
                spell_name="read_file",
                status=SpellStatus.ERROR,
                error_message=f"Path not found or outside allowed scopes: {path}",
            )
        try:
            content = target.read_text(encoding="utf-8")
            return SpellResult(
                spell_name="read_file",
                status=SpellStatus.SUCCESS,
                content=content,
            )
        except Exception as exc:
            return SpellResult(
                spell_name="read_file",
                status=SpellStatus.ERROR,
                error_message=f"Failed to read file: {exc}",
            )

    async def apply_proposal(
        self, proposal: dict[str, Any] | str
    ) -> SkillEvolutionResult:
        """Validate, diff, apply, and record a skill proposal."""
        if isinstance(proposal, str):
            try:
                proposal_dict = json.loads(proposal)
            except Exception as exc:
                return SkillEvolutionResult(
                    success=False,
                    action="unknown",
                    error=f"Invalid JSON proposal: {exc}",
                )
        else:
            proposal_dict = proposal

        action = proposal_dict.get("action", "")

        if action in ("no_action", "NO_ACTION"):
            await self._record_impact({"name": "none", "action": "no_action"}, diff="")
            res = SkillEvolutionResult(success=True, action="no_action")
            self.latest_proposal = {"success": True, "action": "no_action"}
            return res

        skill_name = proposal_dict.get("name", "")
        if not skill_name or not (1 <= len(skill_name) <= 64):
            return SkillEvolutionResult(
                success=False,
                action=action,
                name=skill_name,
                error="name must be non-empty and 1-64 characters",
            )
        if not NAME_REGEX.match(skill_name):
            return SkillEvolutionResult(
                success=False,
                action=action,
                name=skill_name,
                error=f"name {skill_name!r} must match ^[a-z0-9]+(-[a-z0-9]+)*$",
            )

        diff = ""
        applied_path: Path | None = None
        applied_scope: str = "agent"
        skill_dir: Path | None = None

        if action == "create":
            skill_md = proposal_dict.get("skill_md", "")
            purpose_md = proposal_dict.get("purpose_md", "")
            if not skill_md or not purpose_md:
                return SkillEvolutionResult(
                    success=False,
                    action=action,
                    name=skill_name,
                    error="create requires both skill_md and purpose_md",
                )

            target_scope = str(proposal_dict.get("scope", "")).lower()
            if (
                target_scope == "project" or not target_scope
            ) and self.project_skills_dir:
                target_parent = self.project_skills_dir
                applied_scope = "project"
            else:
                target_parent = self.target_skills_dir
                applied_scope = "agent"

            diff = f"--- /dev/null\n+++ {skill_name}/SKILL.md\n" + "\n".join(
                f"+{line}" for line in skill_md.splitlines()
            )

            if self.auto_apply and target_parent:
                skill_dir = target_parent / skill_name
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
                (skill_dir / "PURPOSE.md").write_text(purpose_md, encoding="utf-8")
                applied_path = skill_dir

        elif action == "patch":
            edits = proposal_dict.get("edits", [])
            if not edits:
                return SkillEvolutionResult(
                    success=False,
                    action=action,
                    name=skill_name,
                    error="patch requires at least one edit operation",
                )

            manifest = self.available_skills.get(skill_name)
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
            if (
                origin_dir
                and origin_scope
                and str(origin_scope).lower() == "user"
                and fork_to_project
                and self.project_skills_dir
            ):
                skill_dir = self.project_skills_dir / skill_name
                if not skill_dir.exists() and origin_dir.exists():
                    shutil.copytree(origin_dir, skill_dir, dirs_exist_ok=True)
                applied_scope = "project"
            elif origin_dir and (origin_dir / "SKILL.md").exists():
                skill_dir = origin_dir
                applied_scope = str(origin_scope).lower() if origin_scope else "unknown"
            elif (
                self.project_skills_dir
                and (self.project_skills_dir / skill_name / "SKILL.md").exists()
            ):
                skill_dir = self.project_skills_dir / skill_name
                applied_scope = "project"
            elif (
                self.target_skills_dir
                and (self.target_skills_dir / skill_name / "SKILL.md").exists()
            ):
                skill_dir = self.target_skills_dir / skill_name
                applied_scope = "agent"

            if not skill_dir or not (skill_dir / "SKILL.md").exists():
                return SkillEvolutionResult(
                    success=False,
                    action=action,
                    name=skill_name,
                    error=f"Skill {skill_name!r} not found for patching",
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
                        return SkillEvolutionResult(
                            success=False,
                            action=action,
                            name=skill_name,
                            error=f"replace target not found: {tgt!r}",
                        )
                    patched_text = patched_text.replace(tgt, content, 1)
                elif op == "insert_after":
                    if tgt is None or tgt not in patched_text:
                        return SkillEvolutionResult(
                            success=False,
                            action=action,
                            name=skill_name,
                            error=f"insert_after target not found: {tgt!r}",
                        )
                    idx = patched_text.index(tgt) + len(tgt)
                    patched_text = patched_text[:idx] + content + patched_text[idx:]
                else:
                    return SkillEvolutionResult(
                        success=False,
                        action=action,
                        name=skill_name,
                        error=f"Unknown patch op {op!r}",
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

            if self.auto_apply:
                sk_path.write_text(patched_text, encoding="utf-8")
                applied_path = skill_dir
        else:
            return SkillEvolutionResult(
                success=False,
                action=action,
                name=skill_name,
                error=f"Unknown proposal action {action!r}",
            )

        await self._record_impact(
            {"name": skill_name, "action": action, "scope": applied_scope}, diff=diff
        )

        outcome = SkillEvolutionResult(
            success=True,
            action=action,
            name=skill_name,
            scope=applied_scope,
            diff=diff,
            path=str(applied_path) if applied_path else None,
        )
        self.latest_proposal = {
            "success": True,
            "action": action,
            "name": skill_name,
            "scope": applied_scope,
            "diff": diff,
            "path": str(applied_path) if applied_path else None,
        }
        return outcome

    async def _record_impact(self, proposal: dict[str, Any], diff: str) -> None:
        self.evolution_dir.mkdir(parents=True, exist_ok=True)
        impact_file = self.evolution_dir / "skill-impact.md"
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
            impact_file.write_text(
                f"# Skill Impact Audit Trail\n{entry}", encoding="utf-8"
            )
