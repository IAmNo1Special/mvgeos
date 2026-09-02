# coding-mvge Technical Debt Remediation Plan

Based on `TECHNICAL_DEBT_BY_PACKAGE.md` and source code analysis.

---

## Issue Index

| ID | Title | Category | Priority | Effort |
|----|-------|----------|----------|--------|
| CODING-03 | Hardcoded `DEFAULT_SPELL_MAP` couples to spell implementations | Architecture Quirk | Medium | M |
| CODING-05 | [RESOLVED] No validation of rune-provided spells | Gap | Medium | S-M |

---

## Detailed Remediation Plans

---

## CODING-03: Hardcoded `DEFAULT_SPELL_MAP`

**File**: `coding_mvge/mvge.py:16-17`

### Root Cause
```python
DEFAULT_SPELL_MAP = {
    "bash": cast_bash,
    "read": cast_read,
    "write": cast_write,
    "edit": cast_edit,
    "find": cast_find,
    "list": cast_list,
    "grep": cast_grep,
}
```
Direct imports from `coding_mvge.spells` couple `coding-mvge` to specific builtin spell implementations rather than accepting a dynamic `SpellRegistry`.

### Fix Steps
1. **Define `SpellRegistry` protocol** in `mvgeos-agent` or `coding-mvge`:
   ```python
   class SpellRegistry(Protocol):
       def get_spell(self, name: str) -> MvgeSpell | None: ...
       def get_all_spells(self) -> list[MvgeSpell]: ...
   ```
2. **Implement `DefaultSpellRegistry`** in `coding_mvge/spells/`.
3. Accept optional `spell_registry` in `CodingMvge.__init__` with fallback to `DefaultSpellRegistry()`.

### Priority: Medium
### Effort: Medium (~50 lines)
### Dependencies: mvgeos-agent

---

## [RESOLVED] CODING-05: No Validation of Rune-Provided Spells

**Status**: Resolved in `Mvge._build_spells()` (`mvge.py`, Issue #126)

### Root Cause
```python
if self._runner is not None:
    for rs in self._runner.get_all_registered_spells():
        spells.append(
            MvgeSpell(
                name=rs.name,
                description=rs.description,
                parameters=rs.parameters,
                handler=rs.execute,
            )
        )
```
Rune-provided spells are appended without:
- Checking parameter schema shape
- Verifying execute handler signature
- Checking for name conflicts against base spells

### Fix Steps
1. Validate `rs.parameters` schema type before creating `MvgeSpell`.
2. Inspect `rs.execute` signature via `inspect.signature`.
3. Check for naming collisions against registered base spells and log collisions.

### Priority: Medium
### Effort: Small-Medium (~30 lines)
### Dependencies: mvgeos-runes

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| CODING-03 | mvgeos-agent (protocol) | — |
| CODING-05 | mvgeos-runes | — |

---

## Recommended Implementation Order

1. **CODING-05** (Rune spell validation) — Small, robustness
2. **CODING-03** (Spell registry) — Decoupling

---

## Testing Requirements

- Unit test for custom `SpellRegistry` injection
- Unit test for rune spell conflict logging and parameter rejection
- Run: `uv run python -m pytest coding-mvge/tests/ --cov`

