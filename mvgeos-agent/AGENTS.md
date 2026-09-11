# mvgeos-agent — Agent Instructions

This package implements the session-aware agent engine: the `Mvge` class, `MvgeLoop` (stateful wrapper around the core loop), `MvgeState` (mutable session state), `MvgeHarness` (lifecycle owner), `MvgeEnvironment` (Two-Layer Invariant Scaffolding & dynamic prompt rendering), and `FunctionSpell` (callable tool coercion & discovery). Loop vocabulary (invocations, spells, events, `run_loop`) is canonical in `mvgeos-core`.

## Package-Specific Conventions

- All code follows the red-green-refactor TDD cycle: write failing test first, then implement
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Mock sync methods with `MagicMock()`, async methods with `AsyncMock()` — mixing causes "coroutine never awaited" warnings

## Design Philosophy & Standards

- **Strict Standards Adherence**: 100% adherence to open protocols (`.agents`, `agentskills.io`, standard JSON Schema, MCP). Do not build polyfills or fallbacks for proprietary deviations (e.g. inject only `AGENTS.md`, never `CLAUDE.md`).
- **Zero Backward Compatibility Burden**: Keep the architecture greenfield and clean without legacy shims.

## Testing

```bash
# Run this package's tests
uv run python -m pytest mvgeos-agent/tests/

# Run with coverage
uv run python -m pytest mvgeos-agent/tests/ --cov
```

Test paths follow pattern: `mvgeos-agent/tests/unit/<module>.py` and `mvgeos-agent/tests/integration/<module>.py`

## Key Types

| Type | Purpose |
| --- | --- |
| `MvgeState` | Mutable agent state (prompt, model, spells, invocations, mana, events, queues) |
| `FunctionSpell` | Auto-coerced Python function spell (base `MvgeSpell` lives in core) |
| `Mvge` | Concrete agent with zero-config auto-discovery (`run()` → `_run_impl()`) |
| `MvgeLoop` | Stateful wrapper around core `run_loop`: owns runner, bus, tome; reduces events into `MvgeState` |
| `MvgeHarness` | Session-aware operational owner of the agent loop, compaction, and turns |
| `MvgeEnvironment` | Two-layer invariant scaffolding, layered config, and diagnostic introspection |
| `CompactionRunner` | Orchestrates transcript compaction and summary generation |
| `SpellDispatcher` | Executes tool call batches concurrently or sequentially |
| `MvgeTome` | Deep session manager over `TomeLedger`; open/create/fork/switch; emits session sigils |
| `RuneLifecycle` | Loads runes/skills into a RuneRunner and owns hot-reload watchers |

Core vocabulary (`MvgeEvent`, `MvgeSpell`, `MvgeInvocation`, `ContemplationLevel`,
`SpellDispatcher`, `run_loop`, ...) is documented in `mvgeos-core/AGENTS.md`.

## Spell Schema

- `generate_spell_schema()` in `mvgeos_core/spell_schema.py` — generates JSON schema from function signatures

## Dependencies

- `mvgeos-core` (loop vocabulary: abort, invocations, spells, events, loop)
- `mvgeos-provider` (Realm protocol, registries, OpenRouter realm)
- `mvgeos-tome` (TomeLedger persistence)
- `mvgeos-runes` (RuneRunner, RuneContext, SigilHook)

## Architecture

The core loop flows:
1. `BaseMvge.run(prompt)` → lazy `initialize()` → appends `SummonerRequest` to `state.invocations`
2. `BaseMvge.initialize()` creates `MvgeHarness` (wraps `MvgeLoop`, owns lifecycle)
3. `BaseMvge._run_impl()` delegates to `MvgeHarness.run()`
4. `MvgeHarness.run()` delegates to `MvgeLoop.run()` (nested outer/inner loops)
5. `MvgeLoop.run()` drives core `run_loop()` (nested outer/inner loops), channeling `RealmResponse`s from the Realm
6. On `StopReason.SPELL_USE`: fires `BEFORE_SPELL_CAST` sigil, executes spell, fires `AFTER_SPELL_RESULT`
7. On `STOP/LENGTH/ERROR`: appends response, emits `MESSAGE_END`, `TURN_END`, `AGENT_END`

Harness-owned lifecycle (via callbacks):
- `after_invocation` → compaction (`CompactionRunner.maybe_compact`)
- `should_stop_after_turn` → graceful stop after turn
- `prepare_next_turn` → modify context/model for next turn
- `get_steering_messages` / `get_follow_up_messages` → queue drainage
