# mvgeos-runes Technical Debt Remediation Plan

Based on `TECHNICAL_DEBT_BY_PACKAGE.md` and source code analysis.

---

## Issue Index

| ID | Title | Category | Priority | Effort |
|----|-------|----------|----------|--------|
| RUNE-06 | First-registration-wins for spells/commands/providers (lack of override flag) | Architecture Quirk | Medium | S |
| RUNE-08 | `RuneContext` is mutable dataclass shared across runners | Architecture Quirk | Medium | S |

---

## Detailed Remediation Plans

---

## RUNE-06: First-Registration-Wins Without Override Option

**File**: `mvgeos_runes/rune_runner.py:148-178`

### Root Cause
```python
def register_spell(self, spell: SpellDefinition) -> None:
    if spell.name in self._spells:
        logger.warning("Duplicate spell registration skipped: %s", spell.name)
        return
    self._spells[spell.name] = spell
```
Duplicate registrations are logged with warnings, but there is no explicit `override: bool = False` parameter to allow intentional replacement of a spell, command, shortcut, or provider.

### Fix Steps
1. **Add `override: bool = False` parameter** to `register_spell`, `register_command`, `register_shortcut`, `register_provider`.
2. If `override=True`, allow overwriting existing entry and log at debug level instead of warning.
3. Return `bool` indicating whether registration resulted in an insert/update.

### Priority: Medium
### Effort: Small (~15 lines)
### Dependencies: None

---

## RUNE-08: `RuneContext` is Mutable Dataclass

**File**: `mvgeos_runes/types.py:407-413`

### Root Cause
```python
@dataclass
class RuneContext:
    cwd: str = ""
    mode: str = "cli"
    has_ui: bool = False
```
`RuneContext` is unfrozen and mutable after creation. Multiple runners or concurrent tasks sharing a context reference could mutate state across executions.

### Fix Steps
1. **Make `RuneContext` frozen**:
   ```python
   @dataclass(frozen=True)
   class RuneContext:
       cwd: str = ""
       mode: str = "cli"
       has_ui: bool = False
   ```
2. Update callers to instantiate fresh contexts rather than mutating fields.

### Priority: Medium
### Effort: Small (~10 lines)
### Dependencies: None

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| RUNE-06 | — | — |
| RUNE-08 | — | — |

---

## Recommended Execution Order

1. **RUNE-06** (Registration override flag) — Configurable rune registration
2. **RUNE-08** (Frozen context) — Immutability and safety

---

## Test Strategy

- Unit tests in `mvgeos-runes/tests/`
- Test `override=True` vs `override=False` behavior for duplicate registrations
- Run: `uv run python -m pytest mvgeos-runes/tests/ --cov`

