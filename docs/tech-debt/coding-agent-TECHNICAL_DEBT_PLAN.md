# coding-mvge Technical Debt Remediation Plan

Based on `TECHNICAL_DEBT_BY_PACKAGE.md` (lines 124-134) and source code analysis.

---

## Issue Index

| ID | Title | Category | Priority | Effort |
|----|-------|----------|----------|--------|
| CODING-03 | Hardcoded `DEFAULT_SPELL_MAP` couples to spell implementations | Architecture Quirk | Medium | M |
| CODING-04 | No spell sandboxing | Gap | Medium | L |
| CODING-05 | No validation of rune-provided spells | Gap | Medium | S-M |



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
33: Direct imports from `coding_mvge.spells` couple `coding-mvge` to specific spell implementations. Cannot use custom spells or swap spell implementations without modifying this file.
34: 
35: ### Fix Steps
36: 1. **Create `SpellRegistry` protocol** in `mvgeos-agent` (new file):
37:    ```python
38:    # mvgeos_agent/spell_registry.py
39:    from typing import Protocol, Callable
40:    from mvgeos_agent.types import MvgeSpell
41: 
42: 
43:    class SpellRegistry(Protocol):
44:        def get_spell(self, name: str) -> MvgeSpell | None: ...
45:        def get_all_spells(self) -> list[MvgeSpell]: ...
46:    ```
47: 
48: 2. **Create `DefaultSpellRegistry` implementation** in `coding_mvge/spells` (new file):
49:    ```python
50:    # coding_mvge/spells/registry.py
51:    from mvgeos_agent.spell_registry import SpellRegistry
52:    from coding_mvge.spells import cast_bash, cast_read, ...
53: 
54:    class DefaultSpellRegistry(SpellRegistry):
55:        def __init__(self):
56:            self._spells = {
57:                "bash": MvgeSpell("bash", ..., parameters=generate_schema(cast_bash)),
58:                ...
59:            }
60:        def get_spell(self, name): return self._spells.get(name)
61:        def get_all_spells(self): return list(self._spells.values())
62:    ```
63: 
64: 3. **Update `CodingMvge.__init__`** to accept `spell_registry: SpellRegistry | None = None`:
65:    ```python
66:    def __init__(self, ..., spell_registry: SpellRegistry | None = None, ...):
67:        self._spell_registry = spell_registry or DefaultSpellRegistry()
68:    ```
69: 
70: 4. **Update `_build_base_spells()`** to use registry:
71:    ```python
72:    def _build_base_spells(self) -> list[MvgeSpell]:
73:        spells = []
74:        for name in self._spell_names:
75:            spell = self._spell_registry.get_spell(name)
76:            if spell:
77:                spells.append(spell)
78:        return spells
79:    ```
80: 
81: 5. **Default registry** provided by `coding-mvge`
82: 
83: ### Priority: Medium
84: ### Effort: Medium (~80 lines across 3 files + new protocol)
85: ### Dependencies: mvgeos-agent (protocol)
86: 
87: ---
88: 
89: ## CODING-04: No Spell Sandboxing
90: 
91: ### Root Cause
92: `CodingMvge` uses `DEFAULT_SPELL_MAP` which calls `coding_mvge.spells` functions directly. No path validation or sandbox boundaries. Spells execute with full process permissions.
93: 
94: ### Fix Steps
95: 1. **Implement sandboxing in `coding-mvge/spells`**:
96:    - `SpellSandbox` class with `allowed_roots`
97:    - `resolve_and_validate(path)` method
98:    - Module-level `set_sandbox(allowed_roots)`
99: 
100: 2. **Call sandbox setup in `CodingMvge.initialize()`**:
101:    ```python
102:    async def initialize(self):
103:        ...
104:        from coding_mvge.spells.sandbox import set_sandbox
105: 
106:        set_sandbox([str(Path.cwd())])  # or configurable
107:        ...
108:    ```
109: 
110: 3. **Make sandbox configurable** via `CodingMvge` constructor:
111:    ```python
112:    def __init__(self, ..., sandbox_roots: list[str] | None = None, ...):
113:        self._sandbox_roots = sandbox_roots or [str(Path.cwd())]
114:    ```
115: 
116: ### Priority: Medium
117: ### Effort: Large
118: ### Dependencies: None
119: 
120: ---
121: 
122: ## CODING-05: No Validation of Extension-Provided Spells
123: 
124: **File**: `coding_mvge/mvge.py:221-229`

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
1. **Add validation in `CodingMvge._build_spells()`** (or new method):
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
### Effort: Small-Medium (~40 lines in mvge.py)
### Dependencies: mvgeos-runes (SpellDefinition)

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| CODING-03 | mvgeos-agent (protocol) | — |
| CODING-04 | — | — |
| CODING-05 | mvgeos-runes | — |

---

## Recommended Implementation Order

1. **CODING-05** (Extension spell validation) — Small, improves robustness
2. **CODING-03** (Spell registry) — Decouples spell implementations
3. **CODING-04** (Sandboxing) — Adds execution boundaries to built-in spells

---

## Testing Requirements

- **CODING-03**: Test custom `SpellRegistry` injection; verify default registry works
- **CODING-05**: Test rune spell conflict warning; test invalid parameter rejection; test signature validation
- **CODING-04**: Test sandbox blocks access outside allowed roots; test backward compat (no sandbox = no restriction)

Run: `uv run pytest coding-mvge/tests/ --cov=coding_mvge`
