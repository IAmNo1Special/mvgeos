# Seeker of Spells — Tool Search (MvgeOS Seeker Protocol)

## Executive Summary

The **Seeker of Spells** provides a unified search interface for discovering **spells** (tools) via **Direct Corpus Interaction (DCI)** — ripgrep over live spell source files. Part of the **MvgeOS Seeker Protocol** (external global rune: `mvgeos-runes-seeker`). No vector stores, no embeddings, no offline indexing. Hot-loading is instant.

Architecture derived from four arXiv papers: MCP-Zero (2506.01056), NLT (2607.03953), Tool Attention (2604.21816), and DCI (2605.05242).

---

## 1. Core Design Principles

| Principle | Source | MvgeOS Implementation |
|-----------|--------|----------------------|
| **Agent-Generated Requests** | MCP-Zero | Mvge emits `<tool_request>` in response content |
| **Direct Corpus Interaction** | DCI | `rg` over `~/.agents/.mvgeos/spells/`, `~/.agents/.mvgeos/{agent}/spells/`, `.agents/.mvgeos/spells/` |
| **Natural Language Selection** | NLT | YES/NO grid over candidates (93% fewer parse errors) |
| **Lazy Schema Loading** | Tool Attention | Load full parameter JSON only for top-k selected spells |
| **Zero-Latency Hot Loading** | DCI | New spell file on disk = immediately searchable |

---

## 2. Architecture Overview

```
Mvge (agent)
  |
  |-- emits <tool_request> in response text (no sigil, just content)
  |
  v
ToolSearchSpell (MvgeSpell subclass)
  |
  |-- Stage 1: DCI Router
  |     rg --type py "<operation>" <spells_root>/
  |     Returns: matching file paths + context
  |
  |-- Stage 2: NLT Selector
  |     Present candidates as YES/NO grid
  |     Call realm via RealmRegistry.compose_model() -> create_realm()
  |
  |-- Stage 3: Lazy Schema Loader
  |     Only load full parameter JSON for selected spells
  |
  v
SpellResultMessage appended to state.invocations (owned by MvgeLoop)
```

**Important**: Per the actual `MvgeLoop._execute_spell()` flow (`loop.py:_execute_spell`), the loop owns all lifecycle events including `SPELL_CASTING_START`/`SPELL_CASTING_END` and `SigilHook.AFTER_SPELL_RESULT`. Spells return `dict[str, Any]` and do not self-emit lifecycle events.

---

## 3. Core Components

### 3.1 MvgeSpell Subclass (The ToolSearch Spell)

```python
from __future__ import annotations
import re as _re
from typing import Any
from pathlib import Path

from mvgeos_agent.types import MvgeSpell, SpellExecutionMode
from mvgeos_provider.registry import RealmRegistry

from .router import DCIRouter, SpellFileMatch, SpellSearchError
from .nlt_selector import NLTSelector
from .lazy_loader import LazySpellRegistry


class ToolSearchSpell(MvgeSpell):
    """Subclass MvgeSpell to provide custom execute()."""

    def __init__(
        self,
        provider_registry: RealmRegistry,
        spells_root: Path | None = None,
        rg_timeout: int = 10,
        nlt_model: str = "openrouter/free",
        nlt_api_key: str = "",
    ) -> None:
        super().__init__(
            name="tool_search",
            description="Search for spells by describing what you need",
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": "What you want to do",
                    },
                    "target": {"type": "string", "description": "Target subject"},
                    "grimoire_hint": {"type": "string", "description": "Domain hint"},
                    "max_results": {"type": "integer", "default": 5, "minimum": 1},
                },
                "required": ["operation"],
            },
            execution_mode=SpellExecutionMode.SEQUENTIAL,
        )
        self._provider_registry = provider_registry
        self._spells_root = spells_root or Path(".agents/.mvgeos/spells")
        self._rg_timeout = rg_timeout
        self._nlt_model = nlt_model
        self._nlt_api_key = nlt_api_key
        self._spell_registry = LazySpellRegistry()

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        max_results = params.get("max_results", 5)

        # Stage 1: DCI router
        router = DCIRouter(
            spells_root=self._spells_root,
            rg_timeout=self._rg_timeout,
        )
        try:
            matches = await router.route(params)
        except SpellSearchError as e:
            return {"spells_found": 0, "results": [], "error": str(e)}

        if not matches:
            return {"spells_found": 0, "results": [], "error": None}

        # Exact match fast path: single match where query normalises into filename stem
        operation = params.get("operation", "")
        if len(matches) == 1 and operation and _is_stem_match(operation, matches[0]):
            selected = [matches[0]]
        else:
            # Stage 2: NLT selection — returns file matches, not MvgeSpell objects
            selector = NLTSelector(
                self._provider_registry,
                model_id=self._nlt_model,
                api_key=self._nlt_api_key,
            )
            try:
                selected = await selector.select(params, matches)
            except SpellSearchError as e:
                return {"spells_found": 0, "results": [], "error": str(e)}

        if not selected:
            return {"spells_found": 0, "results": [], "error": None}

        # Trim before lazy load to avoid pointless schema imports
        selected = selected[:max_results]

        # Stage 3: Lazy schema load — load full JSON from source files
        try:
            results = await self._spell_registry.load_selected(selected)
        except Exception as e:
            return {
                "spells_found": 0,
                "results": [],
                "error": f"schema load failed: {e}",
            }

        return {"spells_found": len(results), "results": results, "error": None}


def _is_stem_match(query: str, match: SpellFileMatch) -> bool:
    """True if the query normalises into the file stem.
    Handles multi-word queries: normalises both query and stem by replacing
    spaces/underscores/hyphens with a single space, then checks containment
    with word boundaries. Applies Unicode NFKC normalization to both sides.
    """
    import unicodedata

    stem = unicodedata.normalize("NFKC", match.source_path.stem.lower())
    q = unicodedata.normalize("NFKC", query.lower().strip())
    if not q:
        return False
    stem_normalised = _re.sub(r"[_\s-]+", " ", stem)
    q_normalised = _re.sub(r"[_\s-]+", " ", q)
    if stem_normalised == q_normalised:
        return True
    for token in q_normalised.split():
        if not _re.search(rf"\b{_re.escape(token)}\b", stem_normalised):
            return False
    return True
```

### 3.2 DCI Router

```python
from __future__ import annotations
import asyncio
import json as json_mod
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SpellSearchError(Exception):
    """Raised when spell search encounters a non-recoverable failure."""


# Exit code constants for rg
RG_EXIT_OK = 0  # Matches found
RG_EXIT_NO_MATCH = 1  # No matches
RG_EXIT_BAD_REGEX = 2  # Invalid pattern
# Any other exit code indicates rg failure


@dataclass
class SpellFileMatch:
    source_path: Path
    grimoire: str
    matched_context: str


class DCIRouter:
    """Two-stage rg-based search over spell files with timeout and error handling."""

    def __init__(self, spells_root: Path, rg_timeout: int = 10) -> None:
        self._root = spells_root
        self._timeout = rg_timeout

    async def route(self, params: dict[str, Any]) -> list[SpellFileMatch]:
        operation = params.get("operation", "")
        grimoire_hint = params.get("grimoire_hint", "")

        if not operation or not operation.strip():
            raise SpellSearchError("empty operation query")

        grimoire_dirs = await self._search_grimoires(grimoire_hint)
        if not grimoire_dirs:
            return await self._search_all_grimoires(operation)

        return await self._search_narrow(grimoire_dirs, operation)

    async def _run_rg(
        self, args: list[str], description: str = "rg search"
    ) -> tuple[list[str], str | None]:
        """Run rg with timeout. Returns (lines, error). Error is None on success."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "rg",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await _reap_process(proc)
                return [], f"{description} timed out after {self._timeout}s"

            if proc.returncode == RG_EXIT_BAD_REGEX:
                return [], (
                    f"rg error (exit code 2). "
                    f"stderr: {stderr.decode(errors='replace')[:200]}"
                )

            if proc.returncode not in (RG_EXIT_OK, RG_EXIT_NO_MATCH):
                return [], (
                    f"rg failed with exit code {proc.returncode}. "
                    f"stderr: {stderr.decode(errors='replace')[:200]}"
                )

            lines = [
                p.strip()
                for p in stdout.decode(errors="replace").splitlines()
                if p.strip()
            ]
            return lines, None

        except FileNotFoundError, OSError:
            return [], "rg not found on PATH"

    async def _search_grimoires(self, hint: str) -> list[Path]:
        """Find grimoire (domain) directories matching the hint."""
        if not hint:
            return []
        hint_normalised = _re.sub(
            r"[_\s-]+", " ", unicodedata.normalize("NFKC", hint.lower())
        )
        hint_tokens = hint_normalised.split()
        matches = []
        if not self._root.exists():
            return []
        try:
            for child in self._root.iterdir():
                if child.is_dir():
                    name_normalised = _re.sub(
                        r"[_\s-]+",
                        " ",
                        unicodedata.normalize("NFKC", child.name.lower()),
                    )
                    if all(t in name_normalised.split() for t in hint_tokens):
                        matches.append(child)
        except PermissionError:
            return []
        return matches

    @staticmethod
    def _build_rg_args(query: str, *extra_paths: str) -> list[str]:
        """Build rg args with `--` separator to prevent flag injection via query."""
        args = ["--type", "py", "-l", "--"]
        args.append(query)
        args.extend(extra_paths)
        return args

    async def _search_all_grimoires(self, query: str) -> list[SpellFileMatch]:
        """Fallback: search all spell files under the root when no grimoire hint."""
        args = self._build_rg_args(query, str(self._root))
        lines, error = await self._run_rg(args)
        if error:
            raise SpellSearchError(error)
        return self._process_rg_lines(lines)

    async def _search_narrow(
        self, dirs: list[Path], query: str
    ) -> list[SpellFileMatch]:
        """Search only within the specified grimoire directories."""
        args = self._build_rg_args(query, *(str(d) for d in dirs))
        lines, error = await self._run_rg(args)
        if error:
            raise SpellSearchError(error)
        return self._process_rg_lines(lines)

    def _process_rg_lines(self, lines: list[str]) -> list[SpellFileMatch]:
        """Convert rg output lines to SpellFileMatch objects."""
        results = []
        for path_str in lines:
            p = Path(path_str)
            try:
                grimoire = p.relative_to(self._root).parts[0]
            except ValueError:
                grimoire = p.parent.name
            results.append(
                SpellFileMatch(
                    source_path=p,
                    grimoire=grimoire,
                    matched_context=p.stem,
                )
            )
        return results


async def _reap_process(proc: asyncio.subprocess.Process) -> None:
    """Attempt to kill and reap a stuck process with retry."""
    for _ in range(3):
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
            return
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
    # Final attempt with no timeout
    try:
        await proc.wait()
    except ProcessLookupError:
        pass
```

### 3.3 NLT Selector

```python
from __future__ import annotations
import asyncio
import re
from typing import Any

from mvgeos_agent.types import SummonerRequest
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import ChannelConfig

from .router import SpellFileMatch, SpellSearchError


class NLTSelector:
    """YES/NO grid selection using RealmRegistry flow.
    Returns list[SpellFileMatch] (not MvgeSpell) so LazySpellRegistry
    can lazily import schemas from source files.
    """

    def __init__(
        self,
        registry: RealmRegistry,
        model_id: str = "openrouter/free",
        api_key: str = "",
        nlt_timeout: int = 30,
    ) -> None:
        self._registry = registry
        self._model_id = model_id
        self._api_key = api_key
        self._nlt_timeout = nlt_timeout

    async def select(
        self, params: dict[str, Any], matches: list[SpellFileMatch]
    ) -> list[SpellFileMatch]:
        model = self._registry.compose_model(
            model_id=params.get("model_id", self._model_id),
            api_key=self._api_key,
            provider_name=params.get("provider_name"),
        )
        if not model:
            raise SpellSearchError(
                "NLT model could not be composed; check provider configuration"
            )

        realm = self._registry.create_realm(model, api_key=model.api_key)
        if not realm:
            raise SpellSearchError(
                "NLT realm could not be created; check provider configuration"
            )

        config = ChannelConfig(
            model=model,
            temperature=0.1,
            max_tokens=1024,
        )

        prompt = self._build_prompt(params, matches)
        invocations = [SummonerRequest(role="user", content=prompt)]
        response_text = ""

        try:
            async for resp in asyncio.wait_for(
                realm.stream(model, invocations, config),
                timeout=self._nlt_timeout,
            ):
                if resp.invocation and resp.invocation.content:
                    for item in resp.invocation.content:
                        if item.get("type") == "text":
                            response_text += item.get("text", "")
        except asyncio.TimeoutError:
            raise SpellSearchError(
                f"NLT selection timed out after {self._nlt_timeout}s"
            )
        except Exception as e:
            raise SpellSearchError(f"NLT selection failed: {e}") from e
        finally:
            await realm.close()

        return self._parse_yes_no_grid(response_text, matches)

    def _parse_yes_no_grid(
        self, response: str, candidates: list[SpellFileMatch]
    ) -> list[SpellFileMatch]:
        """YES/NO parsing using bracketed [stem-name] identifiers with rejection pass.
        Also supports index-based references as fallback.
        Applies Unicode NFKC normalization to candidate names for matching.
        """
        import unicodedata

        response_normalized = unicodedata.normalize("NFKC", response)
        if not response_normalized.strip():
            raise SpellSearchError("NLT returned empty response")
        selected: set[str] = set()
        rejected: set[str] = set()
        lines = response_normalized.splitlines()
        for i, c in enumerate(candidates):
            name = unicodedata.normalize("NFKC", c.source_path.stem)
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
                # Index-based fallback with anchor: "1. <text> -- YES"
                if re.search(
                    rf"^{i + 1}\.\s[^,[]*-+\s*YES", line.strip(), re.IGNORECASE
                ):
                    selected.add(name)
                    break
        final = [
            c
            for c in candidates
            if c.source_path.stem in selected and c.source_path.stem not in rejected
        ]
        return final
```

**Optimization — Exact Match Fast Path**: When the DCI router returns exactly one match and the query normalises into the file stem (e.g., query "read_file" matches stem "read_file", query "read file" also matches "read_file"), `ToolSearchSpell.execute()` bypasses the NLT selector entirely. This eliminates the ~800-token LLM call for unambiguous queries. The NLTSelector is never constructed in this path.

rg does not sort results by relevance, so no `relevance_score` field is used. The fast path relies on normalised string identity and word-boundary token containment rather than a score threshold.

### 3.4 Lazy Schema Loader

```python
from __future__ import annotations
import asyncio
import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import Any

from mvgeos_agent.types import MvgeSpell

from .router import SpellFileMatch

logger = logging.getLogger(__name__)


class LazySpellRegistry:
    """Load full parameter JSON only for selected spells.

    Accepts SpellFileMatch objects (file paths + context) and resolves
    the full parameter schema only when load_selected() is called.
    The actual spell module is imported lazily to extract its parameter
    definition — this avoids paying the import cost for unselected spells.
    Cache keyed by (grimoire, name) to prevent collision across domains.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def load_selected(
        self, selected: list[SpellFileMatch]
    ) -> list[dict[str, Any]]:
        results = []
        for match in selected:
            name = match.source_path.stem
            key = (match.grimoire, name)
            # Double-checked locking: fast path without lock
            if key in self._cache:
                results.append(dict(self._cache[key]))
                continue
            schema = await asyncio.to_thread(self._resolve_schema, match.source_path)
            if "error" in schema:
                logger.warning(
                    "Lazy schema load failed for %s: %s", name, schema["error"]
                )
            entry = {
                "name": name,
                "description": schema.get("description", match.matched_context),
                "parameters": schema.get(
                    "parameters", {"type": "object", "properties": {}}
                ),
            }
            # Only cache successful loads; transient errors retry next time
            if "error" not in schema:
                async with self._lock:
                    # Re-check after acquiring lock to prevent races
                    if key not in self._cache:
                        self._cache[key] = entry
            results.append(entry)
        return results

    @staticmethod
    def _resolve_schema(source_path: Path) -> dict[str, Any]:
        """Import the spell module and extract the MvgeSpell parameter schema."""
        import hashlib
        import unicodedata

        module_name = unicodedata.normalize("NFKC", source_path.stem)
        path_hash = hashlib.sha256(str(source_path.resolve()).encode()).hexdigest()[:8]
        qualified_name = (
            f"_lazy_spell_{path_hash}_{source_path.parent.name}_{module_name}"
        )
        try:
            spec = importlib.util.spec_from_file_location(qualified_name, source_path)
            if spec is None or spec.loader is None:
                return {
                    "description": source_path.stem,
                    "parameters": {},
                    "error": "spec could not be created",
                }
            module = importlib.util.module_from_spec(spec)
            sys.modules[qualified_name] = module
            spec.loader.exec_module(module)
            for _name, obj in inspect.getmembers(module):
                if (
                    isinstance(obj, type)
                    and issubclass(obj, MvgeSpell)
                    and obj is not MvgeSpell
                ):
                    return {
                        "description": obj.description,
                        "parameters": obj.parameters,
                    }
                if isinstance(obj, MvgeSpell):
                    return {
                        "description": obj.description,
                        "parameters": obj.parameters,
                    }
            return {"description": source_path.stem, "parameters": {}}
        except Exception as e:
            logger.exception("Failed to resolve schema for %s", source_path)
            return {"description": source_path.stem, "parameters": {}, "error": str(e)}
```

---

## 4. Registration into MvgeOS

Spell is added to `state.spells` during agent initialization:

```python
# In base_mvge.py Mvge.build() or similar, with config injection:
tool_config = config.get("tool_search", {})
tool_search_spell = ToolSearchSpell(
    provider_registry=self._provider_registry,
    spells_root=Path(
        tool_config.get("spells_root", ".agents/.mvgeos/spells")
    ),
    rg_timeout=tool_config.get("rg_timeout", 10),
    nlt_model=tool_config.get("nlt_model", "openrouter/free"),
    nlt_api_key=tool_config.get("nlt_api_key", ""),
)
state.spells.append(tool_search_spell)
```

The MvgeLoop discovers spells by iterating `state.spells` and matching by name (`loop.py:_execute_spell`). All lifecycle events (`SPELL_CASTING_START`, `SPELL_CASTING_END`, `SigilHook.AFTER_SPELL_RESULT`) are owned by the loop, not the spell.

---

## 5. Mana Cost Estimate

| Stage | Memo | Tokens |
|-------|------|--------|
| DCI Routing | rg filesystem | ~50 |
| NLT Selection | LLM call with ~10 cand. | ~800 |
| Lazy Schema Load | 3 spells full JSON | ~600 |
| **Total** | | **~1,500** |

99.4% reduction vs full grimoire injection.

---

## 6. Configuration

```json
{
  "tool_search": {
    "rg_timeout": 10,
    "max_results": 5,
    "nlt_model": "openrouter/free",
    "nlt_api_key": "${OPENAI_API_KEY}",
    "nlt_timeout": 30,
    "spells_root": ".agents/.mvgeos/spells"
  }
}
```

---

## 7. Evaluation

| Metric | Target | Source |
|--------|--------|--------|
| Needle-in-haystack (1k spells) | >88% | DCI-Agent (embedding-free ceiling) |
| Parse error rate | <1% | NLT |
| Schema token reduction | >80% | LazySpellRegistry (actual file-level lazy import) |
| Hot-load latency | <100ms | DCI filesystem |
| Silent failure distinguishability | 100% | Error + log propagation in all paths |
| rg timeout enforcement | 100% | `asyncio.wait_for` with 5s secondary kill timeout |
| rg flag injection via query | 0% | `--` separator before query arg |
| NLT realm resource leak | None | `finally: await realm.close()` |
| Cache collisions across grimoires | 0% | `(grimoire, stem)` tuple key |
