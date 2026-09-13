# ADR 0012: Deepened Mvge Turn-Driving Module

## Status

Accepted

## Date

2026-09-12

## Context

The `Mvge` class (~1059 lines) had become a shallow god module: ~40 public members (14 constructor params, ~19 property aliases, ~20 methods) that pass through to `MvgeHarness`, `MvgeEnvironment`, `RuneLifecycle`, and `TomeLedger` while leaking mutations across the seam (`MvgeState`, `RuneRunner`, `ConfigManager` privates). Two spell-resolution adapters (`_build_spells` in `Mvge` with validation vs `_resolve_spells` in `Harness` append-only) diverged, causing stale removals and unvalidated per-run adds. The `LoopCallbacks` fan-out duplicated fallback logic 9×. Model switching via `set_model_and_realm` existed but lacked the Pi-shaped configured-vs-captured split and emitted no config-change event. Tests poked private internals (`_runner`, `_state`, `_harness`) rather than asserting on the interface.

## Decision

Deepen `MvgeHarness` as the single turn-driving module behind a narrow seam. Shrink `Mvge` to a construction adapter that wires Realm/Tome/Rune/Environment adapters and forwards to Harness.

### 1. Seam owner
`MvgeHarness` owns the turn loop, spell dispatch, compaction, sigil dispatch, and emit fan-out. `Mvge` becomes a thin construction adapter (~100 lines) with no runtime depth.

### 2. Seam shape (Harness interface)
```python
class MvgeHarness:
    async def run(self, invocation: MvgeInvocation) -> list[MvgeInvocation]: ...
    async def steer(self, invocation: MvgeInvocation) -> list[MvgeInvocation]: ...
    def abort(self) -> None: ...
    def set_model_and_realm(self, model: str, realm: Realm) -> None: ...
    def with_model(self, model: str) -> ContextManager[None]: ...  # per-turn override
    @property
    def snapshot(self) -> ExecutionSnapshot: ...  # read-only observability
```

`ExecutionSnapshot`: `configured_model`, `captured_model`, `configured_realm`, `contemplation_budget`, `active_spell_count`.

### 3. State ownership
All `MvgeState` mutation moves behind the Harness seam. `MvgeState` becomes internal implementation; callers (CLI, GUI, tests) assert on `MvgeEvent` stream and returned `MvgeInvocation`s. Private-poking tests deleted (replace-don't-layer).

### 4. MvgeEnvironment
Remains a separate construction adapter (respects ADR-0009 two-layer split). `Mvge` calls `MvgeEnvironment.resolve()` at construction and passes the resolved prompt/config to Harness.

### 5. Spell resolution
- Construction-time validated resolution in `Mvge._build_spells()` (single source of validation, rename, filter).
- `Mvge.reload_spells()` re-runs `_build_spells()` and refreshes `state.spells` + index; called from Rune watcher reload and manual `load_runes()`.
- Harness receives `refresh_spells: Callable[[], list[MvgeSpell]]` at construction; each `run()` calls it instead of the append-only merge.
- Optional `spell_version` counter on `RuneRunner` to skip rebuilds when unchanged.

Preserves all dynamic Rune behavior (adds mid-Tome work; removals now work; validation divergence deleted).

### 6. Sigil dispatch
Single dispatch table inside Harness with one fallback rule: 9 `SigilHook` callbacks mapped to `LoopCallbacks`, optional, never-raising. Callers supply a Rune runner or nothing — no per-callback overrides.

### 7. Emit + Tome record
All four effects (State reduction, event bus, Sigil map, Tome record on `MESSAGE_END`) internal to Harness. Observable surface = `MvgeEvent` stream + returned `MvgeInvocation`s. `tome_service.ledger` reads happen before/after runs, never mid-turn.

### 8. Model switching
Pi-shaped: Harness holds `configured_model`/`configured_realm`; each `run()`/`turn` captures a snapshot for the provider call. `set_model_and_realm` updates configured + emits `CONFIG_CHANGE` event + Tome `model_switch` entry; never touches the in-flight Channeling stream. `with_model` provides per-turn override for router-style use.

### 9. Config change event
Any config setter (`set_model_and_realm`, future `set_contemplation`, `set_tools`) emits `MvgeEventType.CONFIG_CHANGE { model?, realm?, contemplation?, tools? }` alongside domain-specific events.

## Consequences

### Positive
- **Locality**: Spell veto bugs, compaction races, sigil ordering, model-switch in-flight guarantees concentrate in one module.
- **Leverage**: CLI (`repl.py`), GUI (`agent_service.py`), and tests share one narrow seam.
- **Testability**: Harness tests assert on `run/steer/abort` + Events + Invocations; hermetic `StreamFn` replaces private poking.
- **Deletion test passes**: Removing the old pass-throughs concentrates ~800 lines of real depth.
- **Pi parity**: Matches `AgentLane` configured-vs-captured split + `config_update`; exceeds on spell validation centralization and sigil table deduplication.
- **Dynamic Runes preserved**: Adds mid-Tome work; removals fixed; version guard avoids rebuild cost.

### Negative
- Migration effort: ~15 files touch the old seam (CLI, GUI, tests, installer, runes loader).
- `Mvge` callers must migrate from `agent._state.xxx` to `agent.harness.snapshot.xxx` or Event stream.
- `Mvge.reload_spells()` is a new public method; callers using Rune watcher must adopt it.

## Migration Plan (TDD)
1. Add `ExecutionSnapshot` + `config_change` event + `with_model` to Harness (tests first).
2. Implement `refresh_spells` hook + `spell_version` + `reload_spells()` in Mvge (tests first).
3. Collapse `_resolve_spells` → delegation; delete duplicate validation logic.
4. Move all `MvgeState` mutation behind Harness; make `MvgeState` internal.
5. Replace `Mvge` with construction adapter; delete aliases/properties.
6. Update CLI/GUI/tests to new seam; delete private-poking tests.
7. Verify coverage floor holds; run full suite.

## ADR References
- Respects ADR-0007 (single JSONL Tome), ADR-0008 (NiceGUI), ADR-0009 (two-layer scaffolding).
- Builds on ADR-0005 (TDD) — migration is test-first.