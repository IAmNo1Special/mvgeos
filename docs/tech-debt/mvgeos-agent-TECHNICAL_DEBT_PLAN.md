# mvgeos-agent Technical Debt Remediation Plan

Based on `TECHNICAL_DEBT_BY_PACKAGE.md` (lines 5-31) and source code analysis.

---

## Issue Index

| ID | Title | Category | Priority | Effort |
|----|-------|----------|----------|--------|
| AGENT-02 | Silent exception suppression in `loop.py` and `event_bus.py` | Anti-Pattern/Bug | High | M |
| AGENT-03 | Magic strings for tool call types in `loop.py` | Anti-Pattern | High | S |
| AGENT-04 | `Any` type abuse in `base_mvge.py` | Anti-Pattern | Medium | S |
| AGENT-05 | Mutable shared dict mutation in `loop.py:228-231` | Bug | High | S |
| AGENT-06 | Session resume silent fallback in `base_mvge.py:172-185` | Bug | Medium | S |
| AGENT-07 | Linear spell lookup O(n) in `loop.py:362` | Performance | Medium | S |
| AGENT-08 | `MvgeState.events` unbounded growth | Performance | Medium | S |
| AGENT-09 | `SpellExecutionMode.PARALLEL` defined but unused | Architecture | Medium | M |
| AGENT-10 | No spell timeout (global) | Performance/Gap | High | M |
| AGENT-11 | No mana budget enforcement | Gap | High | M |
| AGENT-12 | No max turn limit in `_process_turns()` | Gap | Medium | S |
| AGENT-13 | No spell parameter schema validation | Gap | High | M |
| AGENT-14 | Incomplete session recovery (no model/spell validation) | Gap | Medium | M |
| AGENT-15 | Mixed "spell"/"tool" terminology | Architecture | Low | S |
| AGENT-16 | Session versioning without migration (in tome) | Architecture | Medium | M |



## AGENT-02: Silent Exception Suppression

**Files**: 
- `mvgeos_agent/loop.py:85, 99, 109, 124, 144, 278, 424, 439` — `_safe_emit*()` functions
- `mvgeos_agent/event_bus.py:33` — `EventBus.emit()`

### Root Cause
All `_safe_emit*()` functions use `contextlib.suppress(Exception)` or bare `except Exception:` which catches everything including `KeyboardInterrupt`, `SystemExit`, `asyncio.CancelledError`. Errors are logged but swallowed silently. `EventBus.emit()` does the same.

### Fix Steps
1. **Create `mvgeos_agent/errors.py`** with typed error handling:
   ```python
   class HookError(Exception):
       def __init__(self, hook: SigilHook, cause: Exception): ...


   def is_fatal_error(e: Exception) -> bool:
       return isinstance(e, (KeyboardInterrupt, SystemExit, asyncio.CancelledError))
   ```

2. **Update `_safe_emit()` functions** (`loop.py:78-112`):
   - Catch only non-fatal exceptions: `except Exception as e:` + `if not is_fatal_error(e):`
   - Return `Result` type instead of `None` to distinguish success/failure
   - Re-raise fatal errors immediately

3. **Update `EventBus.emit()`** (`event_bus.py:30-33`):
   - Same pattern: narrow exception catch, log non-fatal, re-raise fatal

4. **Add structured logging** with hook name, error type, and stack trace

### Priority: High
### Effort: Medium (~80 lines across 2 files + new error module)
### Dependencies: None

---

## AGENT-03: Magic Strings for Tool Call Types

**File**: `mvgeos_agent/loop.py:346, 351`

### Root Cause
String literals `"text"` and `"tool_call"` used directly in `_handle_realm_response()`:
```python
if item.get("type") == "text":  # line 346
elif item.get("type") == "tool_call":  # line 351
```

### Fix Steps
1. **Add constants** in `mvgeos_agent/types.py` or new `constants.py`:
   ```python
   class InvocationContentType(StrEnum):
       TEXT = "text"
       TOOL_CALL = "tool_call"
       TOOL_USE = "tool_use"  # from provider
   ```

2. **Replace literals** in `loop.py:346, 351`:
   ```python
   if item.get("type") == InvocationContentType.TEXT:
   elif item.get("type") == InvocationContentType.TOOL_CALL:
   ```

3. **Update `_invocations_to_messages()`** in `mvgeos-provider/openrouter.py:21, 24` to use same constants

### Priority: High
### Effort: Small (~20 lines across 2-3 files)
### Dependencies: mvgeos-provider (for shared constants)

---

## AGENT-04: `Any` Type Abuse in BaseMvge

**File**: `mvgeos_agent/base_mvge.py:67, 148, 278, 279`

### Root Cause
- `_realm: Any = None` (line 67) — should be `Realm | None`
- `_realm` passed as `Any` in `_make_stream()` (line 278)
- `signal: Any | None`, `on_update: Any | None` in `MvgeSpell.execute()` (types.py:99-100)

### Fix Steps
1. **Import `Realm` from `mvgeos_provider.base`** in `base_mvge.py`
2. **Change type annotation** (line 67): `_realm: Realm | None = None`
3. **Update `_make_stream()` signature** (line 277): `realm: Realm`
4. **Define `SpellSignal` and `SpellUpdateCallback` protocols** in `mvgeos_agent/types.py` for `signal` and `on_update` parameters

### Priority: Medium
### Effort: Small (~15 lines)
### Dependencies: mvgeos-provider (for Realm import)

---

## AGENT-05: Mutable Shared Dict Mutation

**File**: `mvgeos_agent/loop.py:228-231`

### Root Cause
```python
if provider_headers:
    if "headers" not in self._state.model:
        self._state.model["headers"] = {}
    if isinstance(provider_headers, dict):
        self._state.model["headers"].update(provider_headers)
```
Mutates `state.model["headers"]` which is shared across turns. Headers accumulate from previous turns.

### Fix Steps
1. **Copy headers instead of mutating**:
   ```python
   if provider_headers and isinstance(provider_headers, dict):
       self._state.model = {
           **self._state.model,
           "headers": {**self._state.model.get("headers", {}), **provider_headers},
       }
   ```

2. **Or reset headers each turn** before applying new ones

### Priority: High
### Effort: Small (~10 lines)
### Dependencies: None

---

## AGENT-06: Session Resume Silent Fallback

**File**: `mvgeos_agent/base_mvge.py:172-185`

### Root Cause
Catches `ValueError, FileNotFoundError`, logs warning, continues with new session. User not notified; session ID changes silently.

### Fix Steps
1. **Raise custom exception** `SessionResumeError` with original cause
2. **Let caller handle** (CLI/repl can show error and ask user)
3. **Or add callback** `on_session_resume_failed` to notify UI

### Priority: Medium
### Effort: Small (~15 lines)
### Dependencies: mvgeos-cli (for UI handling)

---

## AGENT-07: Linear Spell Lookup O(n)

**File**: `mvgeos_agent/loop.py:362`

### Root Cause
```python
spell = next((s for s in self._state.spells if s.name == spell_name), None)
```
O(n) lookup per spell cast. With many spells, adds latency.

### Fix Steps
1. **Add spell index to `MvgeState`**:
   ```python
   @dataclass
   class MvgeState:
       spells: list[MvgeSpell] = field(default_factory=list)
       _spell_index: dict[str, MvgeSpell] = field(default_factory=dict, init=False)
       
       def __post_init__(self):
           self._spell_index = {s.name: s for s in self.spells}
   ```

2. **Update lookup** in `_execute_spell()`:
   ```python
   spell = self._state._spell_index.get(spell_name)
   ```

3. **Maintain index** when spells added/removed via `add_spell()` / `set_spells()`

### Priority: Medium
### Effort: Small (~20 lines)
### Dependencies: None

---

## AGENT-08: MvgeState.events Unbounded Growth

**File**: `mvgeos_agent/types.py:123`

### Root Cause
`events: list[MvgeEvent] = field(default_factory=list)` never cleared. Long sessions accumulate thousands of events.

### Fix Steps
1. **Add max_events config** to `MvgeState`:
   ```python
   max_events: int = 1000
   ```

2. **Rotate in `_emit_event()`** (`loop.py:327-332`):
   ```python
   if len(self._state.events) >= self._state.max_events:
       self._state.events = self._state.events[-self._state.max_events // 2 :]
   ```

3. **Or use `collections.deque(maxlen=...)`** for automatic rotation

### Priority: Medium
### Effort: Small (~15 lines)
### Dependencies: None

---

## AGENT-09: SpellExecutionMode.PARALLEL Unused

**Files**: `mvgeos_agent/types.py:18-20`, `mvgeos_agent/loop.py:354-438`

### Root Cause
`SpellExecutionMode.PARALLEL` enum exists but `_execute_spell()` always runs sequentially. No parallel execution logic.

### Fix Steps
1. **Add parallel execution in `_execute_spell()`**:
   - Collect all tool_calls for current turn
   - Group by `execution_mode`
   - Use `asyncio.gather()` for PARALLEL spells
   - Keep SEQUENTIAL spells running one-by-one

2. **Update `MvgeSpell`** to include `execution_mode` (already in dataclass)

3. **Handle result ordering** — maintain invocation order for sequential, collect parallel results

### Priority: Medium
### Effort: Medium (~60 lines)
### Dependencies: None

---

## AGENT-10: No Global Spell Timeout

**Files**: `mvgeos_agent/loop.py:387-391`, `mvgeos_spells/casting.py:8`

### Root Cause
Only `cast_bash()` has timeout (30s). Other spells have no timeout. `MvgeSpell.execute()` signature has no timeout parameter.

### Fix Steps
1. **Add `timeout_ms` to `MvgeSpell.execute()`** (`types.py:96-103`):
   ```python
   async def execute(
       self,
       spell_cast_id: str,
       params: dict[str, Any],
       signal: Any | None = None,
       on_update: Any | None = None,
       timeout_ms: int = 30000,  # NEW
   ) -> dict[str, Any]: ...
   ```

2. **Wrap spell execution in `loop.py:387-391`**:
   ```python
   try:
       result = await asyncio.wait_for(
           spell.execute(tool_call["id"], tool_call.get("arguments", {})),
           timeout=spell_timeout_ms / 1000,
       )
   except TimeoutError:
       raise SpellTimeoutError(spell_name, spell_timeout_ms)
   ```

3. **Configure default timeout** in `MvgeState` or per-spell

### Priority: High
### Effort: Medium (~40 lines across 2 packages)
### Dependencies: mvgeos-spells (update spell signatures)

---

## AGENT-11: No Mana Budget Enforcement

**Files**: `mvgeos_agent/types.py:117`, `mvgeos_agent/base_mvge.py:248-254`, `mvgeos_provider/openrouter.py:85-86`

### Root Cause
`mana_budget` stored in `MvgeState` and passed to `ChannelConfig.mana_limit` but only used to cap `max_tokens`. No cumulative tracking or enforcement across turns.

### Fix Steps
1. **Track cumulative mana in `MvgeState`**:
   ```python
   mana_used: int = 0
   ```

2. **Update in `_execute_spell()` and after each turn** from `RealmResponse.mana_used`

3. **Check before each turn** in `_process_turns()`:
   ```python
   if self._state.mana_used >= self._state.mana_budget:
       raise ManaExhaustedError()
   ```

4. **Add `stop_reason="mana_exhausted"`** handling in loop (see PROV-08)

### Priority: High
### Effort: Medium (~50 lines across 2 packages)
### Dependencies: mvgeos-provider (mana tracking in RealmResponse)

---

## AGENT-12: No Max Turn Limit

**File**: `mvgeos_agent/base_mvge.py:242-274` (`_process_turns()`)

### Root Cause
While loop continues indefinitely on `steer_queue` or `followup_queue`. No limit on total turns.

### Fix Steps
1. **Add `max_turns` to `MvgeState`** (default 50)
2. **Track turn count** in `_process_turns()`
3. **Break with error** if exceeded:
   ```python
   if turn_count >= self._state.max_turns:
       raise MaxTurnsExceededError(max_turns)
   ```

### Priority: Medium
### Effort: Small (~15 lines)
### Dependencies: None

---

## AGENT-13: No Spell Parameter Schema Validation

**Files**: `mvgeos_agent/types.py:93-94` (`prepare_arguments`), `mvgeos_agent/loop.py:388-391`

### Root Cause
`MvgeSpell.prepare_arguments()` is no-op. `parameters={}` passed to LLM. No validation before `spell.execute()`.

### Fix Steps
1. **Implement `prepare_arguments()`** in `MvgeSpell` to validate against schema:
   ```python
   def prepare_arguments(self, args: dict[str, Any]) -> dict[str, Any]:
       return validate_parameters(self.parameters, args)  # from mvgeos-spells
   ```

2. **Call in `_execute_spell()`** before `spell.execute()`:
   ```python
   validated_args = spell.prepare_arguments(tool_call.get("arguments", {}))
   result = await spell.execute(..., validated_args)
   ```

3. **Integrate with mvgeos-spells schema validation** (SP-8)

### Priority: High
### Effort: Medium (~40 lines)
### Dependencies: mvgeos-spells (SP-1, SP-8)

---

## AGENT-14: Incomplete Session Recovery

**File**: `mvgeos_agent/base_mvge.py:172-195`

### Root Cause
Session resume only catches file errors. Doesn't validate:
- Model compatibility (resumed session's model vs current)
- Spell availability (resumed session's spells vs current)
- Contemplation level match

### Fix Steps
1. **Add validation in `AgentSession.start(reason="resume")`** (`agent_session.py:39-50`):
   - Check `session_header.model` matches current model
   - Check spell names match
   - Raise `SessionIncompatibleError` with details

2. **Add migration path** for incompatible sessions (fork instead of resume)

### Priority: Medium
### Effort: Medium (~50 lines)
### Dependencies: mvgeos-tome (session header access)

---

## AGENT-15: Mixed "Spell"/"Tool" Terminology

**Files**: Throughout codebase

### Root Cause
Inconsistent naming:
- `MvgeSpell` class, `spells` list, `spell_cast_id`
- But `tool_call` in messages, `tool_use` in provider, `StopReason.SPELL_USE`

### Fix Steps
1. **Pick one term** — recommend "spell" (MvgeOS terminology)
2. **Rename constants**: `StopReason.SPELL_USE` (already correct)
3. **Update provider message format** to use `spell_call` instead of `tool_call`
4. **Add migration aliases** for backward compat

### Priority: Low
### Effort: Small-Medium (many files, but mechanical)
### Dependencies: mvgeos-provider, mvgeos-spells

---

## AGENT-16: Session Versioning Without Migration

**Note**: This is actually a `mvgeos-tome` issue (TOME-008). Listed here due to agent's session resume logic.

### Fix Steps
- See `MVGEOS_TOME_TECHNICAL_DEBT_PLAN.md` TOME-008
- Agent needs to handle migrated sessions in resume flow

### Priority: Medium
### Effort: Medium
### Dependencies: mvgeos-tome

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| AGENT-02 | — | — |
| AGENT-03 | mvgeos-provider | — |
| AGENT-04 | mvgeos-provider | — |
| AGENT-09 | — | — |
| AGENT-10 | mvgeos-spells | — |
| AGENT-11 | mvgeos-provider | — |
| AGENT-13 | mvgeos-spells | — |
| AGENT-14 | mvgeos-tome | — |

---

## Recommended Implementation Order

1. **AGENT-02** (Silent exceptions) — Critical for debuggability
2. **AGENT-05** (Mutable dict) — Bug fix, quick win
3. **AGENT-03** (Magic strings) — Type safety
4. **AGENT-04** (Any types) — Type safety
5. **AGENT-07** (Spell index) — Performance
6. **AGENT-08** (Event rotation) — Memory
7. **AGENT-12** (Max turns) — Safety
8. **AGENT-10** (Spell timeout) — Reliability
9. **AGENT-11** (Mana budget) — Budget control
10. **AGENT-13** (Param validation) — Correctness
11. **AGENT-09** (Parallel spells) — Performance
12. **AGENT-14** (Session recovery) — UX
13. **AGENT-06** (Resume fallback) — UX
14. **AGENT-15** (Terminology) — Polish
15. **AGENT-16** (Session migration) — Depends on tome

---

## Testing Requirements

- Unit tests for each fix in `mvgeos-agent/tests/`
- Integration test: full agent loop with all fixes
- Regression test: ensure silent exceptions no longer swallowed
- Memory test: verify `events` list rotation works
- Load test: spell lookup performance with 50+ spells

Run: `uv run pytest mvgeos-agent/tests_agent/ --cov=mvgeos_agent`