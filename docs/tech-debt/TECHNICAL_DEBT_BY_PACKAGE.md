# Technical Debt, Risks & Quirks — Grouped by Package

---

## mvgeos-agent

### Anti-Patterns & Bugs
- ~~**Duplicate initialization logic**: `BaseMvge.initialize()` (171 lines) and `CodingAgent.initialize()` (189 lines) are nearly identical — violates DRY~~ ✅ **RESOLVED** — Refactored to Template Method pattern; `CodingAgent` inherits `BaseMvge` and only overrides 3 hooks
- **Bare `except Exception` / `contextlib.suppress(Exception)`** in `loop.py:33, 42, 86, 99, 106, 112, 124, 144, 178, 424, 439` and `event_bus.py:33` — silently swallows all hook errors
- **Magic strings for tool call types**: `loop.py:346, 351` uses `"tool_use"` and `"text"` string literals without constants
- **`Any` type abuse**: `base_mvge.py:67, 148, 278, 279` — `_realm: Any`, `signal: Any`, `on_update: Any` loses type safety
- **Mutable shared dict mutation**: `loop.py:228-231` — `state.model["headers"].update(provider_headers)` mutates shared dict across turns
- **Session resume silent fallback**: `base_mvge.py:172-185` catches `ValueError, FileNotFoundError`, logs warning, continues with new session — no user notification
- ~~**Duplicate `_build_spells()`** in `coding_mvge/mvge.py:248` and `367` — second shadows first (dead code)~~ ✅ **RESOLVED** — See `coding-mvge` section (duplicate removed during refactoring)

### Performance & Scale
- ~~**Linear spell lookup**: `loop.py:362` — `next((s for s in spells if s.name == name), None)` is O(n) per spell cast~~ ✅ **RESOLVED** — Added `_spell_index` dict in `MvgeState.__post_init__`
- ~~**`MvgeState.events` list grows unbounded** — no cleanup/rotation mechanism (`types.py:123`)~~ ✅ **RESOLVED** — Added `max_events=1000` with rotation in `_emit_event()`
- ~~**`SpellExecutionMode.PARALLEL` defined but unused**~~ ✅ **RESOLVED** — `SpellDispatcher` executes parallel tool calls concurrently via `asyncio.gather()` with fallback sequential execution
- ~~**No spell timeout** — individual spells have no global timeout (only bash spell had 30s hardcoded in `coding_mvge/spells/bash.py`)~~ ✅ **RESOLVED** — Added `spell_timeout_ms=30000` to `MvgeState`, wrapped `spell.execute()` in `asyncio.wait_for()`

### Gaps in Logic
- ~~**No mana budget enforcement** — `mana_budget` stored in state but never decremented/checked in loop~~ ✅ **RESOLVED** — Tracks `mana_used`, enforces when `mana_budget` set (opt-in, default=None matches Pi)
- ~~**No max turn limit** — `_process_turns()` loops infinitely on steer/followup queues (`loop.py:264-272`)~~ ✅ **RESOLVED** — Added `max_turns=50` to `MvgeState`, enforced in `CodingAgent._run_impl()`
- ~~**No spell parameter schema validation**~~ ✅ **RESOLVED** — Implemented schema generation and validation via `mvgeos_agent.spell_schema`
- **Incomplete session recovery** — resume doesn't validate model compatibility or spell availability

### Architecture Quirks
- **Mixed terminology** — code uses both "spell" and "tool" interchangeably (e.g., `tool_call` in messages vs `spell_cast_id`)
- **Session versioning without migration** — `CURRENT_SESSION_VERSION = 3` in `session.py:11` but no migration logic for older versions

---

## mvgeos-provider

### Anti-Patterns & Bugs
- **No connection pooling** — `OpenRouterRealm` creates new `httpx.AsyncClient` per instance (`openrouter.py:60-67`), no reuse across requests
- ~~**No rate limiting / backoff**~~ ✅ **RESOLVED** — Implemented layered retry logic in `retry.py` (`retry_realm_request`, `retry_invocation`) with exponential backoff and jitter
- ~~**Model registry loads all models eagerly**~~ ✅ **RESOLVED** — `ModelRegistry` implements lazy loading on demand with disk caching
- **Hardcoded model lists** — `FREE_MODELS` and `PAID_MODELS` in `models.py:3-50` require code changes to update
- **Streaming tightly coupled to OpenRouter SSE format** — `_invocations_to_messages()` assumes specific delta structure (`openrouter.py:13-51`)

### Performance & Scale
- **24h cache TTL** — `CACHE_TTL_SECONDS = 86400` (`model_registry.py:17`) may serve stale model data
- **No HTTP/2 or connection pooling** — each request opens new connection

### Architecture Quirks
- ~~**`max_output_mana` in `ChannelConfig` ignored by OpenRouter** — passed but not enforced by provider (`types.py:27`)~~ ✅ **RESOLVED** — Caps `max_tokens` via `min()` in `openrouter.py`
- ~~**Contemplation levels passed but unused** — `ContemplationLevel` in `ChannelConfig` but OpenRouter ignores (`types.py:24`)~~ ✅ **RESOLVED** — Wired through to OpenRouter `reasoning: { effort: <level> }` payload

---

## mvgeos-tome

### Anti-Patterns & Bugs
- **Synchronous file I/O in async context** — `JsonlStore.append()` uses blocking `open().write()` (`jsonl_store.py:18-20`), blocks event loop
- **`JsonlStore.read_all()` loads entire file** — O(n) memory for large sessions (`jsonl_store.py:22-26`)
- **FileLock has no recovery** — if process crashes while holding lock, no automatic recovery mechanism (`locking.py:8-41`)
- **`TomeLedger._index` holds ALL entries for ALL tomes in memory** — unbounded growth, no eviction (`ledger.py:17`)

### Gaps in Logic
- **No session file integrity check** — no CRC/checksum; `json.loads` on each line can raise mid-stream (`jsonl_store.py:26`)
- ~~**`build_entries_for_context()` has broken logic**~~ ✅ **RESOLVED** — `SessionManager` deleted; `TomeLedger` handles context filtering correctly
- ~~**Dead private methods**~~ ✅ **RESOLVED** — Removed legacy dead methods during session unification

### Architecture Quirks
- **Pi-compatible JSONL format** — header line + entries, but no version migration path
- **Leaf tracking via separate entry type** — `append_leaf()` creates `type="leaf"` entry pointing to message (`session.py:164-173`)

---

## mvgeos-runes

### Anti-Patterns & Bugs
- **`SigilRegistry.emit()` warns on coroutine but continues** — sync emit with async handler logs `RuntimeWarning` but doesn't await (`sigils.py:21-30`)
- **Error isolation swallows all exceptions** — `_safe_call_handler_async` catches `Exception` and logs but returns `None` (`rune_runner.py:37-49`)
- **`load_factory_from_manifest` uses `importlib.util` dynamically** — no validation of factory signature, can crash on bad entry point (`loader.py:31-53`)
- **Watcher debounce uses fixed 0.5s** — not configurable (`watcher.py:30`)

### Performance & Scale
- **Watchdog observer runs in separate thread** — `Observer()` starts thread, may conflict with async event loop (`watcher.py:116-119`)

### Architecture Quirks
- **First-registration-wins for spells/commands/providers** — `register_spell()` ignores duplicates silently (`rune_runner.py:74-76`)
- **Sigil hooks use `StrEnum` but handlers receive raw `dict`** — no typed payload contracts (`types.py:8-26`)
- **`RuneContext` is mutable dataclass** — shared across runners, potential race conditions (`types.py:43-47`)

---

## mvgeos-cli

### Anti-Patterns & Bugs
- **Two config systems** — `.agents/.mvgeos/config.json` (CLI) + `~/.agents/.mvgeos/{name}/SYSTEM.md` + `GUIDELINES.md` (agent) — confusing
- ~~**Duplicate `_default_config_dir()`** in `prompt_config.py:40` and `prompt_config.py:88`~~ ✅ **RESOLVED** — Consolidated into `ConfigManager` / `MvgeEnvironment`
- ~~**Default model mismatch**~~ ✅ **RESOLVED** — Standardized on `DEFAULT_MODEL` across CLI, REPL, and Agent

### Performance & Scale
- **Prompt-toolkit history file grows unbounded** — `FileHistory` at `~/.agents/.mvgeos/history` no rotation (`repl.py:88-91`)

### Architecture Quirks
- **`CodingMvge` imported in CLI commands** — circular-ish dependency: `cli → coding-mvge → agent → cli` via imports (`prompt.py:10`, `repl.py:13`)

---

## mvgeos-gui

### Architecture & Design
- **1:1 Antigravity layout**: Built natively in NiceGUI with PyWebView desktop windowing
- **In-process execution**: Connects `MvgeHarness` and `CodingMvge` directly through async event bus
- **Auto-completion**: Fuzzy matching for `@` mentions and `/` slash commands
- **Git diff inspection**: Multi-file diff viewer with staged/unstaged tracking

---

## coding-mvge

### Anti-Patterns & Bugs
- ~~**Duplicate `_build_spells()`** at lines 248-259 and 367-378 — second method dead code~~ ✅ **RESOLVED** — Dead code removed during refactoring
- ~~**Duplicate initialization logic** — mirrors `BaseMvge.initialize()` almost line-for-line (189 vs 171 lines)~~ ✅ **RESOLVED** — `CodingMvge` now inherits `BaseMvge` via Template Method pattern
- **Hardcoded `DEFAULT_SPELL_MAP`** — couples agent to specific spell implementations (`mvge.py:44-52`)
- **Blocking file I/O in built-in spells** — `read`, `write`, `edit`, `find`, `grep` use sync I/O in async paths (`coding_mvge/spells/*.py`)

### Gaps in Logic
- ~~**No spell sandboxing**~~ ✅ **RESOLVED** — Implemented `MvgeSandbox` in `mvgeos-agent` with process isolation and allowed modules
- **Only bash has timeout** — `bash.py` has 30s timeout, other spells have none
- **No validation of rune-provided spells** — `runner.get_all_registered_spells()` added without parameter check (`mvge.py:221-229`)

---

## Cross-Package Summary

| Category | Count | Highest Impact |
|----------|-------|----------------|
| Silent exception suppression | 15+ locations | `mvgeos-agent/loop.py`, `mvgeos-runes/sigils.py`, `mvgeos-runes/rune_runner.py` |
| Sync I/O in async code | 6+ locations | `mvgeos-tome/ledger.py`, `coding-mvge/spells/*.py` |
| No connection pooling | 1 | `mvgeos-provider/openrouter.py` |
| Unbounded memory growth | 1 | `mvgeos-tome/ledger.py` (event rotation & spell index added) |
| Missing validation | 1 | Spell resume compatibility (mana budget ✅, turn limits ✅, spell schema ✅) |
| Dead/duplicate code | 0 | Resolved across all packages |
| Hardcoded configuration | 1 | Spell map (model lists ✅, timeouts ✅) |
