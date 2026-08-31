# mvgeos-Agent — Agent Instructions

This package implements the core BaseMvge: the `BaseMvge` class (agent), `MvgeLoop` (turn loop), `MvgeState` (mutable state), `MvgeEvent` (lifecycle events), `EventBus` (pub/sub), and `Sigil` (hook protocol).

## Package-Specific Conventions

- All code follows the red-green-refactor TDD cycle: write failing test first, then implement
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Mock sync methods with `MagicMock()`, async methods with `AsyncMock()` — mixing causes "coroutine never awaited" warnings

## Testing

```bash
# Run this package's tests
uv run pytest mvgeos-agent/tests/

# Run with coverage
uv run pytest mvgeos-agent/tests/ --cov
```

Test paths follow pattern: `mvgeos-agent/tests/unit/<module>.py` and `mvgeos-agent/tests/integration/<module>.py`

## Key Types

| Type | Purpose |
| --- | --- |
| `MvgeState` | Mutable agent state (prompt, model, spells, invocations, mana, events, queues) |
| `MvgeEvent` / `MvgeEventType` | Lifecycle event (type + data dict) |
| `MvgeSpell` | Tool base class; JSON-schema → Pydantic arg validation, abstract `execute()` |
| `SpellResult` | Result of a spell execution (status, content, details, error) |
| `SpellStatus` | Enum (SUCCESS, ERROR, PARTIAL) |
| `SpellResultMessage` | Transcript message for spell results (role="spellResult") |
| `MvgeInvocation` | Union alias: `SummonerRequest \| MvgeResponse \| SpellResultMessage` |
| `ContemplationLevel` | Reasoning-effort enum (maps to OpenRouter `reasoning.effort`) |
| `BaseMvge` | Template-Method agent skeleton (`run()` → `_run_impl()`) |
| `MvgeLoop` | The turn loop: channels realm responses, executes spells, emits events/sigils |
| `MvgeHarness` | Session-aware operational owner of the agent loop, compaction, and turns |
| `MvgeEnvironment` | Layered config loading, prompt resolution, and diagnostic introspection |
| `CompactionRunner` | Orchestrates transcript compaction and summary generation |
| `SpellDispatcher` | Executes tool call batches concurrently or sequentially |
| `MvgeTome` | Deep session manager over `TomeLedger`; open/create/fork/switch; emits session sigils |
| `RuneLifecycle` | Loads runes/skills into a RuneRunner and owns hot-reload watchers |

## Spell Schema

- `generate_spell_schema()` in `mvgeos_agent/spell_schema.py` — generates JSON schema from function signatures
- `validate_spell_args()` in `mvgeos_agent/spell_schema.py` — validates args against a schema

## Dependencies

- `mvgeos-provider` (Realm protocol, Model, ChannelConfig, RealmResponse)
- `mvgeos-runes` (RuneRunner, RuneContext, SigilHook)

## Architecture

The core loop flows:
1. `BaseMvge.run(prompt)` → lazy `initialize()` → appends `SummonerRequest` to `state.invocations`
2. `BaseMvge.initialize()` creates `MvgeHarness` (wraps `MvgeLoop`, owns lifecycle)
3. `BaseMvge._run_impl()` delegates to `MvgeHarness.run()`
4. `MvgeHarness.run()` delegates to `MvgeLoop.run()` (nested outer/inner loops)
5. `MvgeLoop.run()` channels `RealmResponse`s from the Realm
6. On `StopReason.SPELL_USE`: fires `BEFORE_SPELL_CAST` sigil, executes spell, fires `AFTER_SPELL_RESULT`
7. On `STOP/LENGTH/ERROR`: appends response, emits `MESSAGE_END`, `TURN_END`, `AGENT_END`

Harness-owned lifecycle (via callbacks):
- `after_invocation` → compaction (`CompactionRunner.maybe_compact`)
- `should_stop_after_turn` → graceful stop after turn
- `prepare_next_turn` → modify context/model for next turn
- `get_steering_messages` / `get_follow_up_messages` → queue drainage
