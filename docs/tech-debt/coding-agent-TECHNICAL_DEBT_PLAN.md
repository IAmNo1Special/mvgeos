# coding-mvge Technical Debt Remediation Plan

Based on `TECHNICAL_DEBT_BY_PACKAGE.md` (lines 124-134) and source code analysis.

---

## Issue Index

| ID | Title | Category | Priority | Effort |
|----|-------|----------|----------|--------|
| CODING-03 | Hardcoded `DEFAULT_SPELL_MAP` couples to spell implementations | Architecture Quirk | Medium | M |
| CODING-04 | No spell sandboxing (inherited from mvgeos-spells) | Gap | Medium | L |
| CODING-05 | No validation of extension-provided spells | Gap | Medium | S-M |



## CODING-03: Hardcoded `DEFAULT_SPELL_MAP`

**File**: `coding_mvge/mvge.py:44-52`

### Root Cause
```python
DEFAULT_SPELL_MAP: dict[str, Any] = {
    "bash": cast_bash,
    "read": cast_read,
    "write": cast_write,
    "edit": cast_edit,
    "find": cast_find,
    "list": cast_list,
    "grep": cast_grep,
}
```
Direct imports from `mvgeos_spells` couple `coding-mvge` to specific spell implementations. Cannot use custom spells or swap spell implementations without modifying this file.

### Fix Steps
1. **Create `SpellRegistry` protocol** in `mvgeos-agent` (new file):
   ```python
   # mvgeos_agent/spell_registry.py
   from typing import Protocol, Callable
   from mvgeos_agent.types import MvgeSpell


   class SpellRegistry(Protocol):
       def get_spell(self, name: str) -> MvgeSpell | None: ...
       def get_all_spells(self) -> list[MvgeSpell]: ...
   ```

2. **Create `DefaultSpellRegistry` implementation** in `mvgeos-spells` (new file):
   ```python
   # mvgeos_spells/registry.py
   from mvgeos_agent.spell_registry import SpellRegistry
   from mvgeos_spells import cast_bash, cast_read, ...

   class DefaultSpellRegistry(SpellRegistry):
       def __init__(self):
           self._spells = {
               "bash": MvgeSpell("bash", ..., parameters=generate_schema(cast_bash)),
               ...
           }
       def get_spell(self, name): return self._spells.get(name)
       def get_all_spells(self): return list(self._spells.values())
   ```

3. **Update `CodingAgent.__init__`** to accept `spell_registry: SpellRegistry | None = None`:
   ```python
   def __init__(self, ..., spell_registry: SpellRegistry | None = None, ...):
       self._spell_registry = spell_registry or DefaultSpellRegistry()
   ```

4. **Update `_build_base_spells()`** to use registry:
   ```python
   def _build_base_spells(self) -> list[MvgeSpell]:
       spells = []
       for name in self._spell_names:
           spell = self._spell_registry.get_spell(name)
           if spell:
               spells.append(spell)
       return spells
   ```

5. **Default registry** provided by `mvgeos-spells` (no circular deps)

### Priority: Medium
### Effort: Medium (~80 lines across 3 files + new protocol)
### Dependencies: mvgeos-agent (protocol), mvgeos-spells (default registry + schema generation)

---

## CODING-04: No Spell Sandboxing

**Note**: This is primarily a `mvgeos-spells` issue (SP-3). Listed here as coding-mvge inherits the gap.

### Root Cause
`CodingAgent` uses `DEFAULT_SPELL_MAP` which calls `mvgeos_spells` functions directly. No path validation or sandbox boundaries. Spells execute with full process permissions.

### Fix Steps
1. **Implement sandboxing in `mvgeos-spells`** (see SP-3 plan):
   - `SpellSandbox` class with `allowed_roots`
   - `resolve_and_validate(path)` method
   - Module-level `set_sandbox(allowed_roots)`

2. **Call sandbox setup in `CodingAgent.initialize()`**:
   ```python
   async def initialize(self):
       ...
       from mvgeos_spells import set_sandbox

       set_sandbox([str(Path.cwd())])  # or configurable
       ...
   ```

3. **Make sandbox configurable** via `CodingAgent` constructor:
   ```python
   def __init__(self, ..., sandbox_roots: list[str] | None = None, ...):
       self._sandbox_roots = sandbox_roots or [str(Path.cwd())]
   ```

### Priority: Medium
### Effort: Large (mostly in mvgeos-spells, see SP-3)
### Dependencies: mvgeos-spells (SP-3 implementation)

---

## CODING-05: No Validation of Extension-Provided Spells

**File**: `coding_agent/agent.py:221-229`

### Root Cause
```python
if self._runner is not None:
    for rs in self._runner.get_all_registered_spells():
        spells.append(
            MvgeSpell(
                name=rs.name, description=rs.description, parameters=rs.parameters
            )
        )
```
Rune-provided spells added without:
- Parameter schema validation
- Checking for name conflicts with base spells
- Verifying `SpellDefinition.execute()` signature

### Fix Steps
1. **Add validation in `CodingAgent._build_all_spells()`** (or new method):
   ```python
   def _merge_rune_spells(self, base_spells: list[MvgeSpell]) -> list[MvgeSpell]:
       if self._runner is None:
           return base_spells

       existing_names = {s.name for s in base_spells}
       for rs in self._runner.get_all_registered_spells():
           if rs.name in existing_names:
               logger.warning(
                   "Rune spell '%s' conflicts with base spell; skipping", rs.name
               )
               continue
           # Validate parameters schema
           if not isinstance(rs.parameters, dict):
               logger.warning("Rune spell '%s' has invalid parameters; skipping", rs.name)
               continue
           # Validate execute signature
           if not self._validate_spell_signature(rs):
               continue
           base_spells.append(MvgeSpell(...))
       return base_spells
   ```

2. **Add `_validate_spell_signature()`**:
   ```python
   def _validate_spell_signature(self, spell_def: SpellDefinition) -> bool:
       import inspect

       sig = inspect.signature(spell_def.execute)
       params = list(sig.parameters.values())
       # Must have: spell_cast_id, params, signal?, on_update?
       if len(params) < 2:
           return False
       return True
   ```

3. **Add warning log** for conflicts (user visibility)

### Priority: Medium
### Effort: Small-Medium (~40 lines in agent.py)
### Dependencies: mvgeos-runes (SpellDefinition), mvgeos-spells (schema validation)

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| CODING-03 | mvgeos-agent (protocol), mvgeos-spells (registry) | — |
| CODING-04 | mvgeos-spells (SP-3) | — |
| CODING-05 | mvgeos-runes, mvgeos-spells (schema) | — |

---

## Recommended Implementation Order

1. **CODING-05** (Extension spell validation) — Small, improves robustness
2. **CODING-03** (Spell registry) — Decouples from mvgeos-spells
3. **CODING-04** (Sandboxing) — Depends on mvgeos-spells SP-3

---

## Testing Requirements

- **CODING-03**: Test custom `SpellRegistry` injection; verify default registry works
- **CODING-05**: Test rune spell conflict warning; test invalid parameter rejection; test signature validation
- **CODING-04**: Test sandbox blocks access outside allowed roots; test backward compat (no sandbox = no restriction)

Run: `uv run pytest coding-mvge/tests_coding_agent/ --cov=coding_agent`