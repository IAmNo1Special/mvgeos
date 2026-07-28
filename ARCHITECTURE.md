# MvgeOS Architecture

## High-Level Structure

```text
mvgeos/
├── src/mvgeos/
│   ├── mvgeos-agent/     # Core Mvge loop, invocations, state, spell execution
│   ├── mvgeos-provider/  # Realm protocol + repository of realms
│   ├── mvgeos-tome/      # JSONL session persistence with locking + index
│   ├── mvgeos-spells/    # Spell implementations (bash, read, edit, write, grep, find, ls)
│   ├── mvgeos-runes/     # Extension manifest, loader, sigil hooks
│   └── mvgeos-cli/       # CLI entry point (mvgeos command)
├── .agents/mvgeos/       # dotagents protocol compliance
│   ├── extensions/       # Extension runes
│   ├── sessions/         # Tome JSONL files
│   └── auth/             # Relics
└── adr/                  # Architecture Decision Records
```

## Component Map

### mvgeos-agent

The heartbeat of MvgeOS. Contains the `Mvge` class (the agent), `MvgeLoop` (the event loop), `MvgeState` (mutable state), `MvgeSpell` (tool definition), `MvgeEvent` (lifecycle events), `EventBus` (event propagation), and `Sigil` (hook/callback system).

**Entry point**: `Mvge.prompt(incantation)` → `MvgeLoop.run()` → invoke `StreamFunction` → process events → return `MvgeResponse`

**Dependencies**: mvgeos-provider, mvgeos-tome, mvgeos-spells, mvgeos-runes

### mvgeos-provider

Manages the connection to LLM providers. Defines the `Realm` protocol (the provider interface) and implements `OpenRouterRealm` (the OpenRouter provider). The provider handles incantation streaming, authentication resolution (relay of Arcane Keys), and response streaming.

**Entry point**: `Realm.stream(model, context, config)` → returns `Channel` (stream of MvgeResponse events)

**Dependencies**: httpx, filelock

### mvgeos-tome

Manages session persistence. `TomeLedger` (session manager) creates, opens, and manages tomes. `JsonlStore` handles JSONL file I/O with file locking. An in-memory index (`Index`) accelerates session queries.

**Entry point**: `TomeLedger.create(cwd)` → `Tome.append_entry(entry)` → persists to JSONL

**Dependencies**: filelock

### mvgeos-spells

Implements the spell system. Each spell is a `MvgeSpell` with `name`, `description`, `parameters`, and `execute()`. Spells include:

- `cast_bash` → execute shell commands
- `cast_read` → read files
- `cast_edit` → edit files using diff-based replacement
- `cast_write` → write files
- `cast_grep` → search file contents
- `cast_find` → find files by glob
- `cast_list` → list directory contents

**Entry point**: `MvgeSpellsRegistry.register(spell)` → `spell.execute(params)`

**Dependencies**: aiofiles, filelock

### mvgeos-runes

Extension system. `RuneManifest` describes extension metadata and hooks. `RuneLoader` discovers and loads runes from `.agents/mvgeos/extensions/`. `Sigil` hooks define lifecycle points where runes can inject behavior.

**Entry point**: `RuneLoader.load_all()` → discovers manifests → registers sigils → emits MvgeEvents on hooks

**Dependencies**: importlib_metadata

### mvgeos-cli

CLI entry point. Parses arguments and dispatches to commands, orchestrating the other packages.

**Commands**:

- `mvgeos prompt <incantation>` → Run a one-shot incantation
- `mvgeos tome <command>` → Manage tomes (list, create, resume)
- `mvgeos config <command>` → Manage configuration

**Dependencies**: mvgeos-agent, mvgeos-provider, mvgeos-tome, mvgeos-spells, mvgeos-runes, rich

## Data Flow

### Incantation Flow (MvgePrompt)

1. User provides incantation via CLI or TUI
2. CLI creates `Mvge` instance with configured realms and grimoire
3. `Mvge.prompt(incantation)` → normalizes input to `SummonerRequest`
4. `MvgeLoop.run()` adds incantation to `MvgeState.messages`
5. Loop calls `Realm.stream(model, context, config)` on configured realm
6. Provider streams `MvgeResponse` events (start, text_delta, thinking_delta, toolcall_start, etc.)
7. `MvgeLoop` processes events → updates `MvgeState` → emits `MvgeEvent` to subscribers
8. Tool calls detected → `MvgeSpell.execute()` → results appended to context
9. Loop continues until no more tool calls and no steering/follow-up invocations
10. Final `MvgeResponse` emitted with `done` event

### Tome Persistence Flow

1. `MvgeLoop` emits `turn_end` event
2. `TomeLedger` writes each new entry to JSONL file (one JSON object per line)
3. In-memory index is updated with each new entry
4. On session resume, `TomeLedger` reads JSONL, rebuilds index, restores MvgeState
5. All writes are file-locked using `filelock` for cross-platform concurrency safety

### Extension Rune Flow

1. `RuneLoader.load_all()` scans `.agents/mvgeos/extensions/` for `manifest.json` files
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

Discriminated union of lifecycle events: agent_start, turn_start, message_start, message_update, message_end, spell_casting_start/update/end, turn_end, agent_end.

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
- **Config compliance**: dotagents protocol at `.agents/mvgeos/`
