# Seeker of Skills — Skill Search (MvgeOS Seeker Protocol)

## Executive Summary

The **Seeker of Skills** enables MvgeOS to discover and load **skills** (markdown-based agent instructions) from skill directories using **Direct Corpus Interaction (DCI)**. Part of the **MvgeOS Seeker Protocol** (external global rune: `mvgeos-runes-seeker`). Skills are plain `.md` files — no embeddings, no index, no vector store. Drops when skill file appears, instantly findable.

Derived from DCI-Agent (2605.05242) skill prompting patterns and MCP-Zero (2506.01056) multi-agent discovery.

**Design Decision**: Search uses pure `rg` body search over file contents — no YAML frontmatter parsing. This eliminates YAML bomb vulnerabilities, UnicodeDecodeError crashes, `---` body-truncation bugs, and the runtime cost of frontmatter parsing, while achieving identical recall for content-based discovery. Metadata for display is derived from filename and first heading heuristics, not from a structured frontmatter schema.

---

## 1. Core Design Principles

| Principle | Source | MvgeOS Implementation |
|-----------|--------|----------------------|
| **Direct Corpus Interaction** | DCI | `rg` over skill `.md` files (body only, no frontmatter) |
| **Agent-Generated Request** | MCP-Zero | `<skill_request>` emitted by Mvge |
| **Hierarchical Matching** | DCI | Filename -> Body -> NLT selection |
| **Zero-Latency Hot Loading** | DCI | New `.md` file = immediately searchable |
| **No Structured Frontmatter** | DCI cost/benefit | `rg -ilF` over bodies achieves identical recall without YAML attack surface |

---

## 2. Architecture Overview

```
Mvge (agent)
  |
  |-- emits <skill_request> in response content
  |
  v
SkillSearchSpell (MvgeSpell subclass)
  |
  |-- Stage 1: DCI Body Matcher
  |     rg -ilF over skill .md file bodies
  |     (no separate filename stage — rg handles both in one pass)
  |
  |-- Stage 2: NLT Selector
  |     YES/NO grid over candidates (word-boundary aware)
  |
  v
Skill result returned as dict to calling MvgeLoop
```

**Important**: Per the actual `MvgeLoop._execute_spell()` flow (`loop.py:_execute_spell`), the loop owns all lifecycle events. Spells return `dict[str, Any]` and do not self-emit events. All `SPELL_CASTING_START`/`SPELL_CASTING_END` events are emitted by the loop, not the spell.

---

## 3. Skill File Format

Skills are plain markdown files (no required frontmatter):

```markdown
# bash-skill

Execute bash commands in the workspace.

## System Prompt Guidance

When the user asks about running commands, use the bash spell.
Always prefer `rg` over `grep`, `uv` over `pip`.

## Implementation

### Usage
- Always quote paths with spaces
- Prefer full cmdlet names in PowerShell

### Examples
rg "pattern" --include "*.py"
uv run pytest

### Caveats
- Timeout after 120s
- Cannot background processes

## Resources
- SKILL.md
```

Metadata is derived heuristically:
- **Name**: first `# heading` text or filename stem
- **Description**: first non-empty paragraph after the heading
- **Resources**: lines under a `## Resources` heading (if present)

---

## 4. Core Components

### 4.1 SkillSearchSpell

```python
from __future__ import annotations
from pathlib import Path
from typing import Any

from mvgeos_agent.types import MvgeSpell, SpellExecutionMode
from mvgeos_provider.registry import RealmRegistry

from .dci_matcher import DCI_SkillMatcher, SkillFile, _DEFAULT_SKILL_DIRS
from .nlt_selector import SkillNLTSelector


class SkillSearchSpell(MvgeSpell):
    """
    Subclass MvgeSpell to discover skill .md files by query.
    Uses DCI (rg) + NLT selection, no embeddings, no YAML frontmatter.
    """

    def __init__(
        self,
        provider_registry: RealmRegistry,
        skill_dirs: list[Path] | None = None,
        rg_timeout: int = 15,
        nlt_model: str = "openrouter/free",
        nlt_api_key: str = "",
    ) -> None:
        super().__init__(
            name="skill_search",
            description="Search for skills matching a task description",
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "What the user is trying to do",
                    },
                    "domain": {"type": "string", "description": "Domain hint"},
                    "max_results": {"type": "integer", "default": 3},
                },
                "required": ["task"],
            },
            execution_mode=SpellExecutionMode.SEQUENTIAL,
        )
        self._provider_registry = provider_registry
        self._skill_dirs = [p.resolve() for p in (skill_dirs or _DEFAULT_SKILL_DIRS)]
        self._rg_timeout = rg_timeout
        self._nlt_model = nlt_model
        self._nlt_api_key = nlt_api_key

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        task = params.get("task", "")
        if not task:
            return {"skills_found": 0, "skills": [], "error": "empty task query"}
        try:
            max_results = max(1, int(params.get("max_results", 3)))
        except ValueError, TypeError:
            max_results = 3

        matcher = DCI_SkillMatcher(
            skill_dirs=self._skill_dirs,
            rg_timeout=self._rg_timeout,
        )
        skill_dirs_available = matcher.discover_skill_dirs()

        try:
            candidates = await matcher.match_all(skill_dirs_available, task)
        except SkillSearchError as e:
            return {"skills_found": 0, "skills": [], "error": str(e)}

        if not candidates:
            return {"skills_found": 0, "skills": [], "error": None}

        selector = SkillNLTSelector(
            registry=self._provider_registry,
            model_id=self._nlt_model,
            api_key=self._nlt_api_key,
        )
        try:
            selected = await selector.select(task, candidates, max_results)
        except SkillSearchError as e:
            return {"skills_found": 0, "skills": [], "error": str(e)}

        return {
            "skills_found": len(selected),
            "skills": [s.to_dict() for s in selected],
            "error": None,
        }
```

### 4.2 DCI Skill Matcher (rg-only, no YAML)

```python
from __future__ import annotations
import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# rg exit codes
_RG_OK = 0
_RG_NO_MATCH = 1
_RG_BAD_PATTERN = 2

# Sentinel for rg-not-found detection (avoids fragile string matching)
_RG_NOT_FOUND = "RG_NOT_FOUND"

# Default skill directories (defined once to avoid drift)
_DEFAULT_SKILL_DIRS: list[Path] = [
    Path.home() / ".claude/skills",
    Path(".agents/.mvgeos/skills"),
]

logger = logging.getLogger(__name__)


class SkillSearchError(Exception):
    """Non-recoverable skill search failure."""


@dataclass
class SkillFile:
    path: Path
    body_preview: str = ""
    _metadata: dict[str, Any] | None = None
    _raw_content: str | None = None

    @property
    def raw_content(self) -> str:
        """Read file content once and cache it."""
        if self._raw_content is None:
            try:
                self._raw_content = self.path.read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError, UnicodeDecodeError:
                self._raw_content = ""
        return self._raw_content

    @property
    def metadata(self) -> dict[str, Any]:
        """Lazy-load metadata from cached content."""
        if self._metadata is not None:
            return self._metadata
        content = self.raw_content
        name = self._extract_name(self.path, content)
        desc = self._extract_description(content)
        resources = self._extract_resources(content)
        self._metadata = {"name": name, "description": desc, "resources": resources}
        return self._metadata

    @staticmethod
    def _extract_name(path: Path, body: str) -> str:
        """Derive name from first # heading or filename stem. Strips trailing #."""
        m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        if m:
            return m.group(1).strip().rstrip("#").strip()
        return path.stem

    @staticmethod
    def _extract_description(body: str) -> str:
        """First non-empty paragraph after the first heading (skipping subheadings)."""
        lines = body.splitlines()
        in_body = False
        for line in lines:
            if line.startswith("# "):
                in_body = True
                continue
            if in_body and line.strip():
                if line.startswith("#"):
                    continue
                return line.strip()[:200]
        return ""

    @staticmethod
    def _extract_resources(body: str) -> dict[str, str]:
        """Resource names listed under a ## Resources heading.
        Only breaks on `##` (not `###`), allowing subheadings within Resources.
        """
        resources = {}
        in_resources = False
        for line in body.splitlines():
            stripped = line.strip()
            if re.match(r"^## Resources\s*$", stripped):
                in_resources = True
                continue
            if in_resources:
                if re.match(r"^## [^#]", stripped) or not stripped:
                    break
                res_name = stripped.lstrip("- ").strip()
                resources[res_name] = ""
        return resources

    def to_dict(self) -> dict[str, Any]:
        m = self.metadata
        return {
            "name": m["name"],
            "description": m["description"],
            "path": str(self.path.resolve()),
            "filename": self.path.name,
            "body_preview": self.body_preview[:500],
            "resources": list(m.get("resources", {}).keys()),
        }


class DCI_SkillMatcher:
    """
    rg-only skill matching. No YAML frontmatter parsing.
    Uses `rg -ilF` (fixed-string, case-insensitive) to avoid regex
    exit-code-2 failures. Falls back to Python-level search if rg is
    unavailable.
    """

    def __init__(
        self,
        skill_dirs: list[Path] | None = None,
        rg_timeout: int = 15,
    ) -> None:
        self._skill_dirs = skill_dirs or list(_DEFAULT_SKILL_DIRS)
        self._rg_timeout = rg_timeout

    def discover_skill_dirs(self) -> list[Path]:
        return [d for d in self._skill_dirs if d.exists()]

    async def _run_rg(self, args: list[str]) -> tuple[list[str], str | None]:
        """Run rg with fixed strings, timeout, and exit-code handling."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "rg",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._rg_timeout
                )
            except asyncio.TimeoutError:
                await _reap_process_skills(proc)
                return [], f"rg timed out after {self._rg_timeout}s"

            if proc.returncode == _RG_BAD_PATTERN:
                return [], (
                    f"rg error (exit 2). "
                    f"stderr: {stderr.decode(errors='replace')[:200]}"
                )
            if proc.returncode not in (_RG_OK, _RG_NO_MATCH):
                return [], (
                    f"rg failed (exit {proc.returncode}). "
                    f"stderr: {stderr.decode(errors='replace')[:200]}"
                )

            lines = [
                p.strip()
                for p in stdout.decode(errors="replace").splitlines()
                if p.strip()
            ]
            return lines, None

        except FileNotFoundError, OSError:
            return [], _RG_NOT_FOUND

    async def match_all(self, dirs: list[Path], query: str) -> list[SkillFile]:
        """Single rg pass over all .md files in skill directories.
        Uses -F (fixed string) + --glob "*.md" to let rg handle file discovery.
        Falls back to Python-level search if rg is unavailable.
        """
        if not dirs or not query:
            return []

        # Let rg handle its own file traversal with --glob
        args = ["-ilF", "--glob", "*.md", query]
        args.extend(str(d) for d in dirs)
        matched_paths_str, error = await self._run_rg(args)

        if error == _RG_NOT_FOUND:
            # rg not installed — fallback to Python-level search
            matched_paths = []
            for skill_dir in dirs:
                for f in skill_dir.rglob("*.md"):
                    try:
                        content = f.read_text(encoding="utf-8", errors="replace")
                        if query.lower() in content.lower():
                            matched_paths.append(f)
                    except OSError, UnicodeDecodeError:
                        continue
        elif error:
            raise SkillSearchError(error)
        else:
            matched_paths = [Path(p) for p in matched_paths_str]

        results = []
        for fpath in matched_paths:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                idx = content.lower().find(query.lower())
                if idx == -1:
                    preview = content[:200]
                else:
                    start = max(0, idx - 100)
                    end = min(len(content), idx + len(query) + 100)
                    preview = content[start:end]
            except OSError, UnicodeDecodeError:
                content = ""
                preview = f"<unreadable: {fpath.name}>"

            results.append(
                SkillFile(path=fpath, body_preview=preview, _raw_content=content)
            )

        return results


async def _reap_process_skills(proc: asyncio.subprocess.Process) -> None:
    """Attempt to kill and reap a stuck process with retry."""
    for _ in range(3):
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
            return
        except asyncio.TimeoutError:
            proc.kill()
    try:
        await proc.wait()
    except ProcessLookupError:
        pass
```

### 4.3 NLT Skill Selector (word-boundary aware)

```python
from __future__ import annotations
import logging
import re
from typing import Any

from mvgeos_agent.types import SummonerRequest
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import ChannelConfig

from .dci_matcher import SkillFile, SkillSearchError

logger = logging.getLogger(__name__)


class SkillNLTSelector:
    """YES/NO grid selection over skill candidates (bracketed-identifier matching)."""

    def __init__(
        self,
        registry: RealmRegistry,
        model_id: str = "openrouter/free",
        api_key: str = "",
    ) -> None:
        self._registry = registry
        self._model_id = model_id
        self._api_key = api_key

    async def select(
        self,
        task: str,
        candidates: list[SkillFile],
        max_results: int = 3,
    ) -> list[SkillFile]:
        if not candidates:
            return []

        model = self._registry.compose_model(
            model_id=self._model_id,
            api_key=self._api_key,
            provider_name=None,
        )
        if not model:
            logger.warning(
                "NLT model %s not available, returning first %d candidates",
                self._model_id,
                max_results,
            )
            return candidates[:max_results]

        realm = self._registry.create_realm(model, api_key=model.api_key)
        if not realm:
            return candidates[:max_results]
        config = ChannelConfig(model=model, temperature=0.1, max_tokens=512)

        prompt = self._build_prompt(task, candidates)
        invocations = [SummonerRequest(role="user", content=prompt)]
        response_text = ""

        try:
            async for resp in realm.stream(model, invocations, config):
                if resp.invocation and resp.invocation.content:
                    for item in resp.invocation.content:
                        if item.get("type") == "text":
                            response_text += item.get("text", "")
        except Exception as e:
            raise SkillSearchError(f"NLT selection failed: {e}") from e
        finally:
            await realm.close()

        selected_names = self._parse_yes_no_grid(response_text, candidates)
        return [c for c in candidates if c.path.stem in selected_names][:max_results]

    def _build_prompt(self, task: str, candidates: list[SkillFile]) -> str:
        """Use bracketed [stem-name] as the stable identifier."""
        lines = [
            "You are a skill selection specialist. Given a task and candidate skills,",
            "identify which skills are relevant. Output YES/NO for each.",
            "",
            f"Task: {task}",
            "",
            "Skills:",
        ]
        for i, c in enumerate(candidates):
            m = c.metadata
            lines.append(
                f"{i + 1}. [{c.path.stem}] {m.get('name', c.path.stem)}: "
                f"{m.get('description', '')[:200]}"
            )
        lines.append("")
        lines.append(
            "Output each number and bracketed name followed by -- YES or -- NO:"
        )
        return "\n".join(lines)

    def _parse_yes_no_grid(
        self, response: str, candidates: list[SkillFile]
    ) -> set[str]:
        """YES/NO parsing using bracketed [stem-name] identifiers only.
        The bracketed form [bash-skill] is unambiguous — no bare word-boundary
        fallback, preventing substring collisions like 'bash' matching 'bash-advanced'.
        Also supports index-based references (e.g., '1. <text> -- YES') as fallback.
        Two-pass approach: first all lines checked for NO (rejection),
        then all lines checked for YES (selection).
        """
        selected: set[str] = set()
        rejected: set[str] = set()
        lines = response.splitlines()
        for i, c in enumerate(candidates):
            name = c.path.stem
            escaped = re.escape(name)
            # Pass 1: check all lines for NO rejection
            for line in lines:
                if re.search(rf"\[{escaped}\][^[]*-+\s*NO", line, re.IGNORECASE):
                    rejected.add(name)
                    break
                if re.search(
                    rf"^{i + 1}\.\s[^,[]*-+\s*NO", line.strip(), re.IGNORECASE
                ):
                    rejected.add(name)
                    break
            # Pass 2: check all lines for YES selection
            for line in lines:
                if re.search(rf"\[{escaped}\][^[]*-+\s*YES", line, re.IGNORECASE):
                    selected.add(name)
                    break
                # Index-based fallback with proper anchor: "1. <text> -- YES"
                if re.search(
                    rf"^{i + 1}\.\s[^,[]*-+\s*YES", line.strip(), re.IGNORECASE
                ):
                    selected.add(name)
                    break
        return {n for n in selected if n not in rejected}
```

---

## 5. Integration into MvgeOS

### 5.1 Registration

```python
# In agent initialization (base_mvge.py):
skill_search_spell = SkillSearchSpell(
    provider_registry=self._provider_registry,
    skill_dirs=_DEFAULT_SKILL_DIRS,
    rg_timeout=15,
    nlt_model="openrouter/free",
)
state.spells.append(skill_search_spell)
```

### 5.2 Lifecycle Ownership

Per the actual `MvgeLoop._execute_spell()` flow (`loop.py:_execute_spell`, lines 379-418):

1. Loop emits `SPELL_CASTING_START`
2. Loop calls `spell.execute()`, which returns `dict[str, Any]`
3. Loop invokes `_safe_emit_chain(runner, SigilHook.AFTER_SPELL_RESULT, ...)` -- the chain result can modify `result_content` (the mutated value goes into `SpellResultMessage`)
4. Loop appends `SpellResultMessage` to `state.invocations`
5. Loop emits `SPELL_CASTING_END`

The spell itself does not emit lifecycle events or sigil hooks.

---

## 6. Mana Cost

| Stage | Operation | Tokens |
|-------|-----------|--------|
| rg body search | `rg -ilF` over all .md files | ~30 |
| NLT Selection | LLM call with ~10 candidates | ~400 |
| **Total** | | **~430** |

YAML frontmatter removed: saves ~20 tokens per search, eliminates YAML bomb/UnicodeDecodeError/body-truncation attack surface.

---

## 7. Configuration

```json
{
  "skill_search": {
    "nlt_model": "openrouter/free",
    "max_results": 3,
    "rg_timeout": 15,
    "skill_dirs": ["~/.claude/skills", ".agents/.mvgeos/skills"],
    "nlt_api_key": "${OPENAI_API_KEY}"
  }
}
```

**Note**: Tilde in `"~/.claude/skills"` is expanded via `Path.expanduser()` at config load time. Config keys (`rg_timeout`, `skill_dirs`) align with constructor parameter names.

---

## 8. Evaluation

| Metric | Target | Source |
|--------|--------|--------|
| Skill discovery across 50 files | >95% | DCI filesystem (rg-only, no frontmatter) |
| NLT parse error rate | <1% | YES/NO grid (bracketed identifier) |
| Hot-load latency | <100ms | DCI filesystem |
| Frontmatter vulnerability surface | 0 | Removed (no YAML, no UnicodeDecodeError path) |
| rg exit-code-2 recovery | 100% | Fixed-string mode (-F) + sentinel-based fallback |
| Silent failure distinguishability | 100% | Error + log propagation in all paths |
| File reads per matched skill | 1 | `_raw_content` passed to constructor, cached |
| rg file discovery | rg-native | `--glob "*.md"` instead of Python `rglob` |
| NLT realm resource leak | None | `finally: await realm.close()` |
| Substring collision in YES/NO | 0% | Bracketed `[stem]` only with rejection pass |
| Invalid max_results param | Graceful | `try/except (ValueError, TypeError)` around `int()` |
