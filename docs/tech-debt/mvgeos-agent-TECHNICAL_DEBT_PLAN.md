# mvgeos-agent Technical Debt Remediation Plan

Based on `TECHNICAL_DEBT_BY_PACKAGE.md` and source code analysis.

---

## Issue Index

| ID | Title | Category | Priority | Status |
|----|-------|----------|----------|--------|
| AGENT-07 | Linear spell lookup $O(n)$ in `dispatcher.py` | Performance | Medium | [RESOLVED] Implemented via `LoopContext.get_spell` |
| AGENT-14 | Incomplete session recovery (no model/spell validation) | Gap | Medium | Open |
| AGENT-15 | Mixed "spell"/"tool" terminology | Architecture | Low | [RESOLVED] Internal abstractions aligned; external wire boundaries isolated |
| AGENT-16 | Session versioning without migration (in tome) | Architecture | Medium | [RESOLVED] Canonical schema reset to v1 alongside TOME-008 |

---

## AGENT-07: Linear Spell Lookup $O(n)$ [RESOLVED]

**File**: `mvgeos_core/dispatcher.py` (canonical implementation in `mvgeos-core`)

### Resolution
Resolved via `LoopContext._spell_index` and `LoopContext.get_spell(name)` in `mvgeos-core/src/mvgeos_core/loop.py`, providing $O(1)$ spell lookup in `SpellDispatcher`.

### Historical Root Cause
```python
spell = next((s for s in context.spells if s.name == spell_name), None)
```
$O(n)$ lookup per spell cast in `SpellDispatcher`. With many spells in a session context, this adds unnecessary lookup overhead.

### Fix Steps
1. **Add `_spell_index: dict[str, MvgeSpell]` to `LoopContext`**:
   ```python
   @dataclass(frozen=True)
   class LoopContext:
       ...
       spells: list[MvgeSpell] = field(default_factory=list)
       _spell_index: dict[str, MvgeSpell] = field(default_factory=dict, init=False)

       def get_spell(self, name: str) -> MvgeSpell | None:
           return self._spell_index.get(name)
   ```

2. **Update lookup in `SpellDispatcher`**:
   Replace `next((s for s in context.spells if s.name == spell_name), None)` with `context.get_spell(spell_name)` (or dictionary lookup).

### Priority: Medium
### Effort: Small (~15 lines)
### Dependencies: None

---

## AGENT-14: Incomplete Session Recovery

**File**: `mvgeos_agent/agent_session.py:30-48`

### Root Cause
Session resume verifies existence and reads the header but does not validate:
- Model compatibility (resumed session's model vs current active model)
- Spell availability (resumed session's spells vs current active spells)
- Contemplation level compatibility

### Fix Steps
1. **Add validation in `MvgeTome.open()`**:
   - Compare `metadata.model` against target model
   - Check available spell definitions
   - Log warnings or offer configuration fallback

2. **Add migration / fork option** for incompatible sessions.

### Priority: Medium
### Effort: Medium (~40 lines)
### Dependencies: mvgeos-tome

---

## AGENT-15: Mixed "Spell"/"Tool" Terminology [RESOLVED]

**Files**: Throughout agent, core, CLI, and provider message structures

### Resolution
Per the Protocol Boundary Pattern ("Standard at the Boundary, Persona Inside"):
1. **Core & Agent Internal Terminology**:
   - `ContentType.SPELL_CAST = "spell_cast"` is canonical (no `ContentType.TOOL_CALL`).
   - `dispatcher.py` operates strictly on `spell_cast` blocks and emits `spell_casting_start`/`spell_casting_end`.
   - `SpellResultMessage` defaults to `role="spellResult"`.
   - `ChannelConfig` in `mvgeos_core.channel` provides `spells: list[dict[str, Any]]` synchronized with `tools` for wire payloads.
   - `ExperienceHarvester` in `coding_mvge` inspects `invocation.content` for `spell_cast` blocks.
   - `StreamRenderer` in `mvgeos_cli` uses `_write_spell_cast_line`, `on_spell_start`, and `on_spell_end`.
2. **External Wire Protocol Isolation**:
   - External OpenAI / OpenRouter HTTP API boundaries in `mvgeos-provider` (`openrouter.py`) strictly encapsulate `"tools"`, `"tool_calls"`, and `"role": "tool"`, translating them to/from internal `spell_cast` representations without leaking foreign nomenclature into core domain models.

---

## AGENT-16: Session Versioning Without Migration [RESOLVED]

**Note**: Tracked alongside `mvgeos-tome` issue TOME-008.

### Resolution
Resolved alongside TOME-008. Per MvgeOS Design Philosophy ("Zero Backward Compatibility Burden"), `CURRENT_SESSION_VERSION = 1` resets version tracking to a single canonical schema. No legacy version migrations are required. Incompatible versions are cleanly ignored during lookup/open without runtime crashes.

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| AGENT-07 | — | — |
| AGENT-14 | mvgeos-tome | — |
| AGENT-15 | mvgeos-provider, mvgeos-tome | — |
| AGENT-16 | mvgeos-tome | — |

---

## Recommended Implementation Order

1. **AGENT-07** (Spell index in dispatcher) — Performance optimization
2. **AGENT-14** (Session recovery validation) — UX and error prevention
3. **AGENT-15** (Terminology alignment) — Codebase consistency
4. **AGENT-16** (Session version migration) — Coordinated with tome

---

## Testing Requirements

- Unit tests for `LoopContext` indexed lookup
- Session recovery validation tests with mismatched models/spells
- Run: `uv run python -m pytest mvgeos-agent/tests/ --cov`

