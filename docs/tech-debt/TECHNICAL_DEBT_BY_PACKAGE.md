# Technical Debt, Risks & Quirks — Grouped by Package

---

## mvgeos-agent

### Performance & Scale
- [RESOLVED] **Linear spell lookup**: Resolved via `LoopContext.get_spell()` dictionary index in `mvgeos-core/src/mvgeos_core/loop.py` ($O(1)$ lookup in `dispatcher.py`).

### Gaps in Logic
- **Incomplete session recovery**: `MvgeTome.open` does not validate model compatibility or spell availability against current configuration.

### Architecture Quirks
- **Mixed terminology**: Code uses both "spell" and "tool" interchangeably (`ContentType.TOOL_CALL`, `tool_call` dicts in `dispatcher.py`, `role="tool"` in `agent_session.py`).
- [RESOLVED] **Session versioning without migration**: Canonical schema reset to v1 (`CURRENT_SESSION_VERSION = 1`) per zero-backward-compatibility invariant.

---

## mvgeos-provider

### Architecture Quirks
- **Streaming tightly coupled to OpenRouter SSE format**: `_invocations_to_messages()` and `OpenRouterRealm.stream()` handle SSE delta payloads directly (`openrouter.py:99-143, 183-266`). `Realm` base class in `base.py` lacks a generic streaming parser abstraction.
- [RESOLVED] **Dynamic provider fallback**: Resolved via pluggable `RealmFactory` protocol in `RealmRegistry` (`registry.py`, Issue #121).

### Performance & Scale
- **24h cache TTL**: `CACHE_TTL_SECONDS = 86400` in `model_registry.py:17` is static and not configurable per registry instance.

---

## mvgeos-tome

### Performance & Scale
- [RESOLVED] **Full file loading in `_read_tome_entries_from_disk`**: Resolved via streaming line generators `iter_tome_entries()` and `iter_tome_entries_async()` in `ledger.py` for bounded memory usage.

### Reliability & Resilience
- [RESOLVED] **`FileLock` has no recovery**: Resolved via `FileLock.force_release_stale()`, PID/hostname metadata files (`.lock.meta`), and dead-process inspection in `locking.py` and `TomeLedger._cleanup_stale_locks()`.
- [RESOLVED] **No session file integrity check**: Resolved via `verify_integrity()` and `verify_integrity_async()` in `ledger.py`, with structured `TomeIntegrityReport` and `TomeIntegrityIssue` reporting.

### Architecture Quirks
- [RESOLVED] **Session version migration**: Canonical schema reset to v1 (`CURRENT_SESSION_VERSION = 1`); incompatible schemas ignored per zero-backward-compatibility invariant.

---

## mvgeos-runes

### Architecture Quirks
- **First-registration-wins without override**: `register_spell`, `register_command`, `register_shortcut`, and `register_provider` in `rune_runner.py:148-178` log duplicate warnings but lack an `override: bool = False` parameter for intentional replacement.
- **`RuneContext` is mutable dataclass**: `RuneContext` in `types.py:407-413` is an unfrozen dataclass mutable after instantiation.

---

## mvgeos-cli

### Architecture Quirks
- **`CodingMvge` imported in CLI commands**: Direct dependency on `CodingMvge` in `main.py:11` and `repl.py:20` rather than operating against a generic `MvgeAgent` protocol.

---

## mvgeos-gui

### Architecture & Design
- **1:1 Antigravity layout**: Built natively in NiceGUI with PyWebView desktop windowing
- **In-process execution**: Connects `MvgeHarness` and `CodingMvge` directly through async event bus
- **Auto-completion**: Fuzzy matching for `@` mentions and `/` slash commands
- **Git diff inspection**: Multi-file diff viewer with staged/unstaged tracking

---

## coding-mvge

### Architecture Quirks
- **Hardcoded `DEFAULT_SPELL_MAP`**: `mvge.py:16-17` couples the agent to specific spell implementations rather than accepting a dynamic `SpellRegistry`.

### Gaps in Logic
- [RESOLVED] **No validation of rune-provided spells**: Resolved via parameter schema validation, signature verification, and collision renaming in `Mvge._build_spells()` (`mvge.py`, Issue #126).

---

## Cross-Package Summary

| Category | Open Issues | Resolved Items | Primary Focus Area |
|----------|-------------|----------------|--------------------|
| Missing validation | 1 | 1 | Resumed session compatibility (`mvgeos-agent`) |
| Architecture decoupling | 3 | 1 | Streaming abstraction (`mvgeos-provider`), Agent interface decoupling (`mvgeos-cli`) |
| Resilience & Integrity | 0 | 2 | Stale lock cleanup & Session file integrity (`mvgeos-tome`) [RESOLVED] |
| Version migration | 2 | 0 | Session schema migration (`mvgeos-tome`, `mvgeos-agent`) |
| Performance & Scale | 0 | 2 | Linear spell lookup (`mvgeos-core`) & JSONL streaming reads (`mvgeos-tome`) [RESOLVED] |
| Configuration & Mutability | 3 | 0 | Static cache TTL (`mvgeos-provider`), Mutable RuneContext (`mvgeos-runes`), Registration override (`mvgeos-runes`) |
| Terminology alignment | 1 | 0 | Spell vs tool naming alignment (`mvgeos-agent`) |
