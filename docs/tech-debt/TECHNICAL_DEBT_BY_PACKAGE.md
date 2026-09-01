# Technical Debt, Risks & Quirks — Grouped by Package

---

## mvgeos-agent

### Performance & Scale
- **Linear spell lookup**: `SpellDispatcher` in `dispatcher.py:74, 191` uses `next((s for s in context.spells if s.name == spell_name), None)` ($O(n)$ per spell cast).

### Gaps in Logic
- **Incomplete session recovery**: `MvgeTome.open` does not validate model compatibility or spell availability against current configuration.

### Architecture Quirks
- **Mixed terminology**: Code uses both "spell" and "tool" interchangeably (`ContentType.TOOL_CALL`, `tool_call` dicts in `dispatcher.py`, `role="tool"` in `agent_session.py`).
- **Session versioning without migration**: `CURRENT_SESSION_VERSION = 3` in `ledger.py`, but no migration logic exists for older session schemas.

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
- **Full file loading in `_read_tome_entries_from_disk`**: `ledger.py:399-401` uses `f.readlines()` to load all JSONL entries into memory rather than an async streaming line generator.

### Reliability & Resilience
- **`FileLock` has no recovery**: `locking.py:9-45` wraps `filelock.FileLock` without PID/timestamp metadata inspection or dead-process lock cleanup on crash.
- **No session file integrity check**: No per-line CRC32 checksums or session header SHA256 hashes are calculated or validated on JSONL reads.

### Architecture Quirks
- **Session version migration**: `TomeLedger._load_tome_metadata()` reads session metadata but has no migration pipeline for previous schema versions (v1/v2 -> v3).

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
- **No validation of rune-provided spells**: `CodingMvge._build_spells()` in `mvge.py:108-114` appends registered rune spells without verifying their parameter schema compatibility or signature constraints.

---

## Cross-Package Summary

| Category | Count | Highest Impact |
|----------|-------|----------------|
| Missing validation | 2 | Resumed session compatibility (`mvgeos-agent`), Rune spell schema validation (`coding-mvge`) |
| Architecture decoupling | 3 | Streaming abstraction (`mvgeos-provider`), Agent interface decoupling (`mvgeos-cli`), Spell registry (`coding-mvge`) |
| Resilience & Integrity | 2 | Stale lock cleanup (`mvgeos-tome`), Session file integrity checks (`mvgeos-tome`) |
| Version migration | 2 | Session schema migration (`mvgeos-tome`, `mvgeos-agent`) |
| Performance & Scale | 2 | Linear spell lookup (`mvgeos-agent`), JSONL streaming reads (`mvgeos-tome`) |
| Configuration & Mutability | 3 | Static cache TTL (`mvgeos-provider`), Mutable RuneContext (`mvgeos-runes`), Registration override (`mvgeos-runes`) |
| Terminology alignment | 1 | Spell vs tool naming alignment (`mvgeos-agent`) |
