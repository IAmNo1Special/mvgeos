from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coding_mvge.runes.skill_evolution.models import (
    ConsolidationLogEntry,
    SkillEvolutionMetadata,
)


class SkillEvolutionStore:
    """Pure-markdown skill evolution store per paper §3.1.

    Layout under evolution_dir
    (agent scoped `~/.agents/.mvgeos/{agent}/skill_evolution`):
      index.md
      logs.md
      skill-impact.md
      patterns/<pattern-name>.md
      .gating.json
    """

    def __init__(self, evolution_dir: Path):
        self.evolution_dir = Path(evolution_dir).expanduser().resolve()
        self.evolution_dir.mkdir(parents=True, exist_ok=True)
        self.patterns_dir = self.evolution_dir / "patterns"
        self.patterns_dir.mkdir(exist_ok=True)
        self.index_path = self.evolution_dir / "index.md"
        self.logs_path = self.evolution_dir / "logs.md"
        self.skill_impact_path = self.evolution_dir / "skill-impact.md"
        self.gating_path = self.evolution_dir / ".gating.json"
        self.raw_experience_dir: Path | None = None
        self._ensure_skeleton()

    def bind_raw_experience(self, raw_dir: Path) -> None:
        self.raw_experience_dir = Path(raw_dir).expanduser().resolve()
        self.raw_experience_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_skeleton(self) -> None:
        if not self.index_path.exists():
            self.index_path.write_text(
                "# Skill Evolution Index\n\nCatalog of learned patterns:\n",
                encoding="utf-8",
            )
        if not self.logs_path.exists():
            self.logs_path.write_text("# Evolution Logs\n\n", encoding="utf-8")
        if not self.skill_impact_path.exists():
            self.skill_impact_path.write_text(
                "# Skill Impact Audit Trail\n\n", encoding="utf-8"
            )
        if not self.gating_path.exists():
            self.gating_path.write_text(
                json.dumps(
                    {
                        "R_best": 0.0,
                        "last_turn": 0,
                        "created_at": datetime.now(UTC).isoformat(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    def get_metadata(self) -> SkillEvolutionMetadata:
        try:
            data = json.loads(self.gating_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        patterns = list(self.patterns_dir.glob("*.md"))
        return SkillEvolutionMetadata(
            created_at=datetime.now(UTC),
            last_consolidation_turn=int(data.get("last_turn", 0)),
            total_entries=len(patterns),
            total_consolidations=int(data.get("consolidations", 0)),
            schema_version=1,
        )

    def _update_gating(
        self,
        last_turn: int | None = None,
        inc_consolidations: bool = False,
        r_best: float | None = None,
    ) -> None:
        try:
            data = json.loads(self.gating_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if last_turn is not None:
            data["last_turn"] = max(int(data.get("last_turn", 0)), last_turn)
        if inc_consolidations:
            data["consolidations"] = int(data.get("consolidations", 0)) + 1
        if r_best is not None:
            data["R_best"] = r_best
        data["updated_at"] = datetime.now(UTC).isoformat()
        self.gating_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    async def add_pattern(self, name: str, content: str, turn: int) -> None:
        target = self.patterns_dir / name
        target.write_text(content.strip() + "\n", encoding="utf-8")
        self._update_gating(last_turn=turn)

    async def patch_pattern(self, name: str, edits: list[dict[str, Any]]) -> bool:
        target = self.patterns_dir / name
        if not target.exists():
            return False
        text = target.read_text(encoding="utf-8")
        for edit in edits:
            op = edit.get("op")
            content = edit.get("content", "")
            tgt = edit.get("target")
            if op == "append":
                text += content
            elif op == "replace":
                if tgt is None or tgt not in text:
                    return False
                text = text.replace(tgt, content, 1)
            elif op == "insert_after":
                if tgt is None or tgt not in text:
                    return False
                idx = text.index(tgt) + len(tgt)
                text = text[:idx] + content + text[idx:]
            else:
                return False
        target.write_text(text, encoding="utf-8")
        return True

    async def update_index(self, content: str) -> None:
        self.index_path.write_text(content, encoding="utf-8")

    async def append_log(self, line: str) -> None:
        with self.logs_path.open("a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")

    async def append_skill_impact(
        self, proposal: dict[str, Any], r_val: float, accepted: bool, diff: str
    ) -> None:
        p_name = proposal.get("name", "unknown")
        p_act = proposal.get("action", "?")
        status = "Accepted" if accepted else "Rejected"
        entry = (
            f"\n## {p_name} ({p_act}) — {status}\n"
            f"- Turn: {proposal.get('turn', '?')}\n"
            f"- Action: {p_act}\n"
            f"- Validation: {r_val}\n"
            f"- Outcome: {status}\n" + (f"```diff\n{diff}\n```\n" if diff else "")
        )
        with self.skill_impact_path.open("a", encoding="utf-8") as f:
            f.write(entry)

    async def list_patterns(self) -> list[Path]:
        return sorted(self.patterns_dir.glob("*.md"))

    async def read_index(self) -> str:
        return (
            self.index_path.read_text(encoding="utf-8")
            if self.index_path.exists()
            else ""
        )

    async def read_logs(self) -> str:
        return (
            self.logs_path.read_text(encoding="utf-8")
            if self.logs_path.exists()
            else ""
        )

    async def read_skill_impact(self) -> str:
        return (
            self.skill_impact_path.read_text(encoding="utf-8")
            if self.skill_impact_path.exists()
            else ""
        )

    async def search(self, query: str, limit: int = 10) -> list[Path]:
        q = query.lower()
        hits: list[tuple[int, Path]] = []
        for p in self.patterns_dir.glob("*.md"):
            txt = p.read_text(encoding="utf-8").lower()
            if q in txt:
                hits.append((txt.count(q), p))
        hits.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in hits[:limit]]

    async def get_recent(
        self, limit: int = 50, since_turn: int | None = None
    ) -> list[Path]:
        files = sorted(
            self.patterns_dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return files[:limit]

    async def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def add_entry(self, entry: Any) -> None:
        name = f"{entry.summary.replace(' ', '-').lower()[:40]}.md"
        await self.add_pattern(
            name,
            entry.to_markdown()
            if hasattr(entry, "to_markdown")
            else entry.content or entry.summary,
            entry.turn,
        )

    async def log_consolidation(self, log_entry: ConsolidationLogEntry) -> None:
        await self.append_log(log_entry.to_markdown())
        self._update_gating(last_turn=log_entry.turn, inc_consolidations=True)

    async def render_index(self) -> str:
        return await self.read_index()

    async def render_logs(self) -> str:
        return await self.read_logs()

    async def render_skill_impact(self, history: Any = None) -> str:
        return await self.read_skill_impact()
