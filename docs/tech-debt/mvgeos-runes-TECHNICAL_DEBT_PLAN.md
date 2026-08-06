# mvgeos-runes Technical Debt Remediation Plan

Based on `TECHNICAL_DEBT_BY_PACKAGE.md` (lines 91-106) and source code analysis.

---

## Issue Index

| ID | Title | Category | Priority | Effort |
|----|-------|----------|----------|--------|
| RUNE-01 | `SigilRegistry.emit()` warns on coroutine but continues | Anti-Pattern/Bug | High | S |
| RUNE-02 | Error isolation swallows all exceptions | Anti-Pattern/Bug | High | S |
| RUNE-03 | `load_factory_from_manifest` uses dynamic import without signature validation | Anti-Pattern/Bug | High | M |
| RUNE-04 | Watcher debounce uses fixed 0.5s (not configurable) | Anti-Pattern/Bug | Medium | S |
| RUNE-05 | Watchdog observer runs in separate thread (async conflict risk) | Performance/Scale | Medium | M |
| RUNE-06 | First-registration-wins for spells/commands/providers (silent ignore) | Architecture Quirk | Medium | S |
| RUNE-07 | Sigil hooks use `StrEnum` but handlers receive raw `dict` (no typed payloads) | Architecture Quirk | Medium | M |
| RUNE-08 | `RuneContext` is mutable dataclass shared across runners (race risk) | Architecture Quirk | Medium | M |

---

## RUNE-01: `SigilRegistry.emit()` Warns on Coroutine but Continues

**File**: `mvgeos_runes/sigils.py:21-30`

### Root Cause
`SigilRegistry.emit()` is a synchronous method that iterates handlers and calls them. If a handler returns an `Awaitable` (async function), it:
1. Logs a `RuntimeWarning` (line 25-30)
2. **Does not await** the coroutine — the coroutine is created but never scheduled
3. Continues to next handler

This means async handlers silently fail to execute while emitting a warning that may go unnoticed.

### Fix Steps
1. **Option A (Recommended)**: Remove `emit()` entirely; force callers to use `emit_async()`, `emit_chain()`, `emit_first()`, or `emit_block()` from `RuneRunner` which properly await.
   - Delete `SigilRegistry.emit()` (lines 21-30)
   - Update `RuneRunner.emit()` (line 129-130) to raise `RuntimeError` directing to async variants
   - Update tests: `test_rune_runner.py:456-467` expects warning; change to expect exception

2. **Option B (Backward-compat)**: Auto-schedule coroutine via `asyncio.create_task()` but this introduces fire-and-forget semantics.

### Priority: High
### Effort: S (Small)
### Dependencies: None (internal to mvgeos-runes)

---

## RUNE-02: Error Isolation Swallows All Exceptions

**File**: `mvgeos_runes/rune_runner.py:37-49` (`_safe_call_handler_async`)

### Root Cause
```python
async def _safe_call_handler_async(handler, hook, data):
    async def wrapper():
        try:
            return await _call_handler_async(handler, hook, data)
        except Exception:  # CATCHES EVERYTHING
            logger.exception(...)
            return None

    return wrapper()
```

Problems:
- Catches `Exception` (includes `KeyboardInterrupt`, `SystemExit`, `asyncio.CancelledError`)
- Returns `None` silently — callers (`emit_async`, `emit_chain`, `emit_first`, `emit_block`) cannot distinguish "handler returned None" from "handler crashed"
- No metrics/metrics export for handler failure rates
- No circuit-breaker or retry logic

### Fix Steps
1. **Narrow exception catch**: Change `except Exception` to `except Exception as e` where `e` is not `CancelledError`, `KeyboardInterrupt`, `SystemExit`
2. **Return structured result**: Return a `HandlerResult` dataclass with `success: bool`, `result: Any`, `error: Exception | None`
3. **Add metrics hook**: Optional callback on failure for metrics emission
4. **Update callers** (`emit_async`, `emit_chain`, `emit_first`, `emit_block` at lines 132-156) to handle `HandlerResult`

```python
@dataclass
class HandlerResult:
    success: bool
    result: Any = None
    error: Exception | None = None
```

### Priority: High
### Effort: S (Small)
### Dependencies: None (internal)

---

## RUNE-03: `load_factory_from_manifest` Uses Dynamic Import Without Signature Validation

**File**: `mvgeos_runes/loader.py:31-53`

### Root Cause
```python
def load_factory_from_manifest(manifest, rune_dir):
    # ...
    spec = importlib.util.spec_from_file_location(...)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # Can raise ANY exception
    factory = getattr(mod, "rune_factory", None)  # No signature check
    return cast(RuneFactory, factory)  # Unsafe cast
```

Problems:
- `exec_module()` can raise `SyntaxError`, `ImportError`, `AttributeError`, etc. — all caught and return `None` silently (line 48-49)
- No validation that `factory` matches `RuneFactory = Callable[[RuneAPI], None | Awaitable[None]]`
- Bad entry point crashes loader silently; rune simply doesn't load
- No version compatibility check between rune manifest and runner API

### Fix Steps
1. **Define `RuneFactory` protocol** with explicit signature in `types.py` or `rune_api.py`:
   ```python
   from typing import Protocol


   class RuneFactory(Protocol):
       def __call__(self, api: RuneAPI) -> None | Awaitable[None]: ...
   ```

2. **Add signature validation** using `inspect.signature()` after loading:
   ```python
   import inspect

   sig = inspect.signature(factory)
   params = list(sig.parameters.values())
   if len(params) != 1 or params[0].annotation not in (
       RuneAPI,
       Any,
       inspect.Parameter.empty,
   ):
       raise TypeError(f"rune_factory must accept single RuneAPI parameter, got {sig}")
   ```

3. **Raise specific exceptions** instead of returning `None`:
   - `RuneLoadError` (custom exception) with `cause` preserving original
   - Distinguish: `ManifestNotFound`, `EntryPointMissing`, `FactoryNotFound`, `FactorySignatureMismatch`, `FactoryLoadError`

4. **Add `RuneLoader.load_all()` error collection** — return `(manifests, errors)` tuple or use `Result` type

5. **Update tests** to verify error cases raise appropriate exceptions

### Priority: High
### Effort: M (Medium)
### Dependencies: None (internal), but affects `mvgeos-cli` rune loading

---

## RUNE-04: Watcher Debounce Uses Fixed 0.5s (Not Configurable)

**File**: `mvgeos_runes/watcher.py:30-31`

### Root Cause
```python
async def _debounced() -> None:
    await asyncio.sleep(0.5)  # HARDCODED
    ...
```

- Hardcoded constant prevents tuning for different filesystem latencies (network mounts, slow disks)
- No way to disable debounce for tests (causes flaky tests with real fs events)
- Debounce logic tied to handler instance; not reusable

### Fix Steps
1. Add `debounce_seconds: float = 0.5` parameter to `_RuneReloadHandler.__init__()`
2. Add `debounce_seconds` parameter to `RuneWatcher.__init__()` and pass through
3. Add `RuneWatcherConfig` dataclass in `types.py` or `watcher.py` for future extensibility
4. Update tests to use `debounce_seconds=0.01` for fast execution

### Priority: Medium
### Effort: S (Small)
### Dependencies: None

---

## RUNE-05: Watchdog Observer Runs in Separate Thread (Async Conflict Risk)

**File**: `mvgeos_runes/watcher.py:114-118`

### Root Cause
```python
self._observer = Observer()
self._observer.schedule(self._handler, str(self._extensions_dir), recursive=True)
self._observer.start()  # STARTS BACKGROUND THREAD
```

- `watchdog.Observer` runs a native thread that calls `_RuneReloadHandler` methods
- Handler methods (`on_modified`, `on_created`, `on_deleted`) call `asyncio.create_task()` from **non-async thread**
- This works only if event loop is running in main thread; breaks in:
  - Tests with `asyncio.new_event_loop()`
  - Subprocess workers
  - When multiple event loops exist

### Fix Steps
**Option A: Use `watchdog.observers.asyncio.AsyncObserver` (requires watchdog 3.0+)**
```python
from watchdog.observers.asyncio import AsyncObserver

self._observer = AsyncObserver()
await self._observer.start()  # async start
```

**Option B: Thread-safe bridge** (if watchdog < 3.0)
- Use `asyncio.run_coroutine_threadsafe()` from handler thread to schedule on main loop
- Store reference to main event loop at `RuneWatcher` creation

**Recommended**: Option A — cleaner, native async support. Check `pyproject.toml` for watchdog version.

### Priority: Medium
### Effort: M (Medium)
### Dependencies: `watchdog` version upgrade may be needed

---

## RUNE-06: First-Registration-Wins for Spells/Commands/Providers (Silent Ignore)

**File**: `mvgeos_runes/rune_runner.py:74-76` (and similar at 78-80, 82-84, 86-88)

### Root Cause
```python
def register_spell(self, spell: SpellDefinition) -> None:
    if spell.name not in self._spells:  # SILENT IGNORE
        self._spells[spell.name] = spell
```

- No warning, no error, no override option
- Rune load order determines winner (non-deterministic across filesystem walks)
- Makes debugging "why isn't my spell registering?" extremely difficult
- Same pattern for `register_command`, `register_shortcut`, `register_provider`

### Fix Steps
1. **Add `override: bool = False` parameter** to all four register methods
2. **Log warning** when duplicate detected and `override=False`:
   ```python
   logger.warning(
       "Spell '%s' already registered; use override=True to replace", spell.name
   )
   ```
3. **Return bool** indicating whether registration succeeded (new) or was skipped/replaced
4. **Add `register_spell_force()`** or similar for explicit override intent
5. **Update tests**: `test_rune_runner.py:31-39` expects first-wins; update to test new behavior

### Priority: Medium
### Effort: S (Small)
### Dependencies: `mvgeos-agent` (spell registration), `mvgeos-cli` (command registration)

---

## RUNE-07: Sigil Hooks Use `StrEnum` but Handlers Receive Raw `dict` (No Typed Payloads)

**File**: `mvgeos_runes/types.py:8-26` (`SigilHook`), `mvgeos_runes/sigils.py:9` (`Handler = Callable[..., Any]`)

### Root Cause
- `SigilHook` defines 18 hook points as string enum values
- Handler type is `Callable[..., Any | None | Awaitable[Any | None]]` — completely untyped
- Each hook expects different payload structure (e.g., `BEFORE_SPELL_CAST` expects spell name + params; `AFTER_PROVIDER_RESPONSE` expects response object)
- No documentation or enforcement of payload shapes
- IDE support nonexistent; runtime errors only

### Fix Steps
1. **Define typed payload classes** in `types.py` (or new `payloads.py`):
   ```python
   @dataclass
   class BeforeInvocationPayload:
       model: str
       messages: list[dict]
       mana_budget: int | None


   @dataclass
   class BeforeSpellCastPayload:
       spell_name: str
       params: dict[str, Any]
       spell_cast_id: str


   # ... one per SigilHook
   ```

2. **Create `SigilPayload` union** and map `SigilHook -> payload type`:
   ```python
   SIGIL_PAYLOADS: dict[SigilHook, type] = {
       SigilHook.BEFORE_INVOCATION: BeforeInvocationPayload,
       ...
   }
   ```

3. **Update `SigilRegistry.register()`** to accept typed handler:
   ```python
   def register[T](self, hook: SigilHook, handler: Callable[[SIGIL_PAYLOADS[hook]], Any | Awaitable[Any]]) -> None:
   ```

4. **Update `RuneRunner` emit methods** to construct typed payloads before calling handlers

5. **Provide migration path**: Keep `Any` fallback for existing runes; deprecate over time

### Priority: Medium
### Effort: M (Medium)
### Dependencies: `mvgeos-agent` (uses sigil hooks in loop), `mvgeos-provider` (provider hooks)

---

## RUNE-08: `RuneContext` is Mutable Dataclass Shared Across Runners (Race Risk)

**File**: `mvgeos_runes/types.py:43-47`

### Root Cause
```python
@dataclass
class RuneContext:
    cwd: str = ""
    mode: str = "cli"
    has_ui: bool = False
```

- `RuneRunner` holds single `_context` instance (line 59)
- `bind_context()` replaces reference (line 68-69) — not thread-safe
- Multiple `RuneRunner` instances can share same `RuneContext` if passed explicitly
- No immutability guarantees; fields mutable after creation

### Fix Steps
1. **Make `RuneContext` frozen**:
   ```python
   @dataclass(frozen=True)
   class RuneContext:
       cwd: str = ""
       mode: str = "cli"
       has_ui: bool = False
   ```

2. **Change `bind_context()` to return new `RuneRunner`** (builder pattern) or require context at construction:
   ```python
   def with_context(self, context: RuneContext) -> RuneRunner:
       new = RuneRunner()
       new._context = context
       # copy other state...
       return new
   ```

3. **Or**: Keep mutable but add `threading.Lock` for `bind_context` (less preferred)

4. **Update all callers** (`mvgeos-agent`, `mvgeos-cli`) to pass context at construction

### Priority: Medium
### Effort: M (Medium)
### Dependencies: `mvgeos-agent` (creates `RuneRunner`), `mvgeos-cli` (creates `RuneRunner`)

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| RUNE-01 | — | `mvgeos-agent` (uses `emit_async`) |
| RUNE-02 | — | `mvgeos-agent` (handler error handling) |
| RUNE-03 | — | `mvgeos-cli` (rune loading) |
| RUNE-04 | — | — |
| RUNE-05 | `watchdog` version | — |
| RUNE-06 | — | `mvgeos-agent`, `mvgeos-cli` (registration patterns) |
| RUNE-07 | — | `mvgeos-agent`, `mvgeos-provider` (hook payloads) |
| RUNE-08 | — | `mvgeos-agent`, `mvgeos-cli` (context passing) |

---

## Recommended Execution Order

1. **RUNE-01** (High, S) — Remove sync `emit()` footgun immediately
2. **RUNE-02** (High, S) — Fix error swallowing; improves debuggability
3. **RUNE-03** (High, M) — Secure rune loading; prevents silent failures
4. **RUNE-06** (Medium, S) — Make registration behavior explicit
5. **RUNE-04** (Medium, S) — Configurable debounce; easy win
6. **RUNE-05** (Medium, M) — Async watchdog; may need dependency upgrade
7. **RUNE-07** (Medium, M) — Typed payloads; requires coordinated changes in agent/provider
8. **RUNE-08** (Medium, M) — Frozen context; requires caller updates

---

## Test Strategy

For each fix:
1. **Write failing test first** (TDD per AGENTS.md)
2. **Run existing tests**: `uv run pytest mvgeos-runes/tests_runes/ -v`
3. **Run full suite**: `uv run pytest --cov` after each change
4. **Add integration test** for RUNE-03 (bad manifest), RUNE-05 (async watcher), RUNE-07 (typed payloads)

---

## Acceptance Criteria

- [ ] All 8 issues addressed with code changes
- [ ] All existing tests pass (`uv run pytest mvgeos-runes/tests_runes/`)
- [ ] Coverage maintained ≥90% (`uv run pytest --cov=mvgeos_runes`)
- [ ] No new `RuntimeWarning` in test runs
- [ ] Type checking passes (`uv run mypy mvgeos_runes --strict`)
- [ ] Linting passes (`uv run ruff check mvgeos_runes`)
