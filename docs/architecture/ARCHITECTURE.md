# MvgeOS Architecture

## High-Level Structure

```text
mvgeos/
├── mvgeos-agent/         # Core Mvge loop, invocations, state, spell execution
├── mvgeos-provider/      # Realm protocol + repository of realms
├── mvgeos-tome/          # JSONL session persistence with locking + index
├── mvgeos-runes/         # Extension manifest, loader, sigil hooks
├── mvgeos-cli/           # CLI entry point (mvgeos command)
├── coding-mvge/         # Coding agent package (BaseMvge subclass)
├── .agents/.mvgeos/      # dotagents protocol compliance (created at runtime)
│   ├── runes/              # Rune extensions
│   ├── tomes/            # Tome JSONL files
│   └── auth/             # API keys and credentials
└── docs/adr/             # Architecture Decision Records
```

## Component Map

### mvgeos-agent

The heartbeat of MvgeOS. Contains the `Mvge` class (the agent),
`MvgeLoop` (the event loop), `MvgeState` (mutable state),
`MvgeSpell` (tool definition), `MvgeEvent` (lifecycle events),
`EventBus` (event propagation), and `Sigil` (hook/callback system).

**Entry point**: `BaseMvge.run(prompt)` → `MvgeLoop.run()`
→ invoke `StreamFunction` → process events → return `MvgeResponse`

**Dependencies**: mvgeos-provider, mvgeos-tome, mvgeos-runes

### mvgeos-provider

Manages the connection to LLM providers (Realms). Defines the `Realm` protocol
(the provider interface) and implements `OpenRouterRealm`
(the OpenRouter provider). The provider handles channeling (streaming),
authentication resolution, and response delivery.

**Entry point**: `Realm.channel(model, invocations, config)`
→ returns async generator of `RealmResponse`

**Dependencies**: httpx, filelock

### mvgeos-tome

Manages session (tome) persistence. `TomeLedger` creates, opens, and manages tomes.
Each tome is stored as a single Pi-compatible JSONL file (`{tome_id}.jsonl`) with a
header line followed by entry lines. An in-memory index (`Index`) accelerates queries
and is rebuilt on startup from the JSONL files. File locking via `filelock` ensures
cross-platform concurrency safety.

**Entry point**: `TomeLedger(tome_dir)` → `create_tome(cwd)` → `append(tome_id, entry)`
→ persists to JSONL

**Dependencies**: filelock

### mvgeos-runes

Extension system. `RuneManifest` describes extension metadata
and hooks. `RuneLoader` discovers and loads runes from
`.agents/.mvgeos/runes/`. `SigilHook` defines lifecycle
points where runes can register Sigil callbacks.

**Entry point**: `RuneLoader.load_all()` → discovers manifests
→ registers sigils → emits MvgeEvents on hooks

**Dependencies**: importlib_metadata

### mvgeos-cli

CLI entry point. Parses arguments and dispatches to commands,
orchestrating the other packages.

**Commands**:

- `mvgeos <prompt>` → Run a one-shot prompt (or start REPL/TUI if omitted)
- `mvgeos tome <command>` → Manage tomes (list, create, resume)
- `mvgeos config <command>` → Manage configuration

**Dependencies**: mvgeos-agent, mvgeos-provider, mvgeos-tome,
mvgeos-runes, rich, typer

### coding-mvge

Coding agent package implementing `BaseMvge`. Provides `CodingMvge`
class with built-in spells (bash, read, write, edit, find, list, grep)
and system prompt configuration.

**Entry point**: `CodingMvge(api_key).run(prompt)`

**Dependencies**: mvgeos-agent, mvgeos-provider, mvgeos-tome,
mvgeos-runes

### mvgeos-harness

Harness package wrapping `MvgeLoop` and owning the session lifecycle
(matching Pi's `AgentHarness`). Owns compaction, steering/follow-up
queues, and turn callbacks (`should_stop_after_turn`,
`prepare_next_turn`). Delegates to `MvgeLoop.run()` for the nested
outer/inner loop structure.

**Entry point**: `MvgeHarness(loop, compaction, callbacks).run(...)`

**Dependencies**: mvgeos-agent, mvgeos-provider

## Data Flow

### Invocation Flow

1. User provides input via CLI or TUI
2. CLI creates `BaseMvge`/`CodingMvge` instance with configured realms
3. `BaseMvge.run(prompt)` → normalizes input to `SummonerRequest`
4. `BaseMvge.initialize()` creates `MvgeHarness` (wraps `MvgeLoop`, owns lifecycle)
5. `MvgeHarness.run()` delegates to `MvgeLoop.run()` (nested outer/inner loops)
6. Loop calls `Realm.channel(model, invocations, config)` on configured realm
7. Provider channels `RealmResponse` events (text deltas, tool calls, etc.)
8. `MvgeLoop` processes events → updates `MvgeState` → emits `MvgeEvent` to subscribers
9. Tool calls detected → `Spell.execute()` → results appended to invocations
10. Loop continues until no more tool calls and no steering/follow-up invocations
11. `MvgeHarness` handles compaction (after each invocation), `should_stop_after_turn`,
    `prepare_next_turn`, steering/follow-up queue drainage
12. Final `MvgeResponse` emitted with `done` event

### Tome Persistence Flow

1. `MvgeLoop` emits `turn_end` event
2. `TomeLedger` writes each new entry to JSONL file (one JSON object per line)
3. In-memory index is updated with each new entry
4. On session resume, `TomeLedger` reads JSONL, rebuilds index, restores MvgeState
5. All writes are file-locked using `filelock` for cross-platform concurrency safety

### Extension Rune Flow

1. `RuneLoader.load_all()` scans `.agents/.mvgeos/runes/`
   for `manifest.json` files
2. Each manifest registers sigils (lifecycle hooks) with the `Sigil` system
3. During `MvgeLoop`, appropriate events are emitted to registered sigils
4. Sigils intercept, modify, or supplement the mvge's behavior

## Key Abstractions

### MvgeInvocation (AgentMessage equivalent)

```typescript
type MvgeInvocation = SummonerRequest | MvgeResponse | SpellResultMessage
```

### MvgeSpell (AgentTool equivalent)

```typescript
interface MvgeSpell {
    name: str
    description: str
    parameters: dict
    execute(params, signal, on_update) -> SpellResult
    execution_mode: SpellExecutionMode  # sequential | parallel
}
```

### MvgeState (AgentState equivalent)

```typescript
interface MvgeState {
    system_prompt: str
    model: Model
    contemplation_level: ContemplationLevel
    spells: list[MvgeSpell]
    invocations: list[MvgeInvocation]
    is_streaming: bool
    streaming_manifestation: MvgeInvocation | None
    pending_spell_casts: set[str]
    error_message: str | None
}
```

### MvgeEvent (AgentEvent equivalent)

Discriminated union of lifecycle events: agent_start, turn_start,
message_start, message_update, message_end, spell_casting_start/update/end,
turn_end, agent_end.

## Technology Stack

- **Python**: >= 3.14
- **Package manager**: uv exclusively
- **Build system**: hatchling
- **Testing**: pytest with pytest-asyncio
- **Linting/formatting**: ruff
- **Type checking**: mypy (strict)
- **File locking**: filelock (cross-platform)
- **HTTP client**: httpx (provider realm)
- **CLI**: rich (future TUI), argparse (CLI commands)
- **Pre-commit**: pre-commit framework (ruff + mypy + pytest checks)
- **Config compliance**: dotagents protocol at `.agents/.mvgeos/`
- **Changelog**: git-cliff at `cliff.toml` — conventional commits
  → CHANGELOG.md
- **Releases**: `.github/workflows/release.yml` — tags `v*`
  trigger changelog + GitHub release
