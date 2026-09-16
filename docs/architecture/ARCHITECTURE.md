# MvgeOS Architecture

## High-Level Structure

```text
mvgeos/
├── mvgeos-core/            # Canonical loop vocabulary: abort, invocations, spells, events, pure turn loop (zero first-party deps)
├── mvgeos-agent/         # Mvge class, session lifecycle, harness, environment (depends on core + leafs)
├── mvgeos-provider/      # Realm protocol + repository of realms (depends on core)
├── mvgeos-tome/          # JSONL session persistence with locking + index (zero first-party deps)
├── mvgeos-runes/         # Extension manifest, loader, sigil hooks (depends on core)
├── mvgeos-cli/           # CLI entry point (mvgeos command)
├── mvgeos-gui/           # Desktop GUI application (NiceGUI + PyWebView)
├── coding-mvge/         # Coding agent package (BaseMvge subclass)
├── .agents/.mvgeos/      # dotagents protocol compliance (created at runtime)
│   ├── runes/              # Rune extensions
│   ├── tomes/            # Tome JSONL files
│   └── auth/             # API keys and credentials
└── docs/adr/             # Architecture Decision Records
```

## Component Map

### mvgeos-core

Zero-dependency canonical vocabulary. Owns abort primitives, invocation
transcript types, spell definitions, events, constants, errors, the
`SpellDispatcher`, the `EventBus`, and the pure turn loop (`run_loop` with
injected `StreamFn` and `emit` sink). Leaf packages and the agent depend on
core, never the reverse (enforced by `dependency_direction` guards).

**Entry point**: `run_loop(context, stream_fn, emit, callbacks)`
→ channels `RealmResponse`s → casts Spells → returns new Invocations

**Dependencies**: pydantic only

### mvgeos-agent

Session-aware agent engine. Contains the `Mvge` class (the agent),
`MvgeState` (mutable session state), `MvgeHarness` (deep operational owner
of turns, compaction, and lifecycle), `MvgeEnvironment`
(configuration and prompt scaffolding), and `FunctionSpell` (callable tool
coercion and discovery).

**Entry point**: `BaseMvge.run(prompt)` → `MvgeHarness.run()`
→ invoke `StreamFunction` → process events → return `MvgeResponse`

**Dependencies**: mvgeos-core, mvgeos-provider, mvgeos-tome, mvgeos-runes

### mvgeos-provider

Manages the connection to LLM providers (Realms). Defines the `Realm` protocol
(the provider interface) and implements `OpenRouterRealm`
(the OpenRouter provider). The provider handles channeling (streaming),
authentication resolution, non-channeled completion, and response delivery.
Channel vocabulary (`Model`, `ChannelConfig`, `RealmResponse`, `StopReason`,
abort primitives) is canonical in `mvgeos-core`.

**Entry point**: `Realm.stream(model, invocations, config)`
→ returns async generator of `RealmResponse`

**Dependencies**: mvgeos-core, httpx, filelock

### mvgeos-tome

Manages session (tome) persistence. `TomeLedger` creates, opens, and manages tomes.
Each tome is stored as a single JSONL file (`{tome_id}.jsonl`) — a Pi-inspired format that is not byte-compatible with Pi session files — with a
header line followed by entry lines. An in-memory index (`Index`) accelerates queries
and is rebuilt on startup from the JSONL files. File locking via `filelock` ensures
cross-platform concurrency safety.

**Entry point**: `TomeLedger(tome_dir)` → `create_tome(cwd)` → `append(tome_id, entry)`
→ persists to JSONL

**Dependencies**: filelock

### mvgeos-runes

Extension system. `RuneManifest` describes extension metadata
and hooks. `load_runes_from_paths` discovers and loads runes from
configured scopes. `SigilHook` defines lifecycle
points where runes can register Sigil callbacks.

**Entry point**: `load_runes_from_paths()` → discovers manifests
→ registers sigils → emits MvgeEvents on hooks

**Dependencies**: mvgeos-core (`ExecutionMode` is canonical there),
importlib.util, watchdog

### mvgeos-cli

CLI entry point. Parses arguments and dispatches to commands,
orchestrating the other packages.

**Commands**:

- `mvgeos [prompt]` → Run a prompt, start REPL, or start TUI (`--tui`)
- `mvgeos setup [check|install]` → Check and install missing dependencies
- `mvgeos info` → Display rich runtime snapshot
- `mvgeos build` → Serialise resolved runtime manifest
- `mvgeos tome <command>` → Manage tomes (list, show, export, create, fork)
- `mvgeos config <command>` → Manage configuration (show, set, get, reset, path)

**Dependencies**: mvgeos-agent, mvgeos-core, mvgeos-provider, mvgeos-tome,
mvgeos-runes, rich, typer, prompt_toolkit

### mvgeos-gui

Native desktop graphical user interface matching the 1:1 Google Antigravity IDE
design. Connects directly to `CodingMvge` and `MvgeHarness` in-process with a live
event bus. Provides a three-column layout with project navigation, interactive chat
viewport with step cards, floating autocomplete input dock (`@` mentions, `/` commands),
git diff viewer, and slide-over artifact markdown inspector.

**Entry point**: `mvgeos-gui` command → `mvgeos_gui.main:main`

**Dependencies**: nicegui, pywebview, pathspec, coding-mvge, mvgeos-agent,
mvgeos-core, mvgeos-provider, mvgeos-runes, mvgeos-tome

### coding-mvge

Pre-configured coding agent package providing `root_mvge = Mvge(name="coding_mvge")`.
Decomposes built-in development spells (`bash`, `read`, `write`, `edit`, `find`,
`list_files`, `grep`) into modular files within `coding_mvge/spells/` and colocates
`SYSTEM.md`, `GUIDELINES.md`, and authoring guides (`AGENTS.md`) for autonomous
self-modification and zero-boilerplate instantiation.

**Entry point**: `from coding_mvge import root_mvge` → `root_mvge.run(prompt)`

**Dependencies**: mvgeos-agent, mvgeos-core, mvgeos-provider, mvgeos-runes

## Data Flow

### Invocation Flow

1. User provides input via CLI or TUI
2. CLI creates `BaseMvge`/`CodingMvge` instance with configured realms
3. `BaseMvge.run(prompt)` → normalizes input to `SummonerRequest`
4. `BaseMvge.initialize()` creates `MvgeHarness` (owns lifecycle, compaction, and turn driving)
5. `BaseMvge._run_impl()` delegates to `MvgeHarness.run()`
6. `MvgeHarness.run()` drives core `run_loop()`, channeling `RealmResponse`s from the Realm
7. Loop calls `Realm.stream(model, invocations, config)` on configured realm
8. Provider channels `RealmResponse` events (text deltas, tool calls, etc.)
9. `MvgeHarness` processes events → updates `MvgeState` → emits `MvgeEvent` to subscribers
10. Tool calls detected → `SpellDispatcher.execute_spells()` → `Spell.execute()` → results appended to invocations
11. Loop continues until no more tool calls and no steering/follow-up invocations
12. `MvgeHarness` handles compaction (pre-turn and after each invocation), `should_stop_after_turn`,
    `prepare_next_turn`, steering/follow-up queue drainage
13. Final `MvgeResponse` emitted with `done` event

### Tome Persistence Flow

1. `MvgeHarness` emits `turn_end` / `message_end` event
2. `TomeLedger` writes each new entry to JSONL file (one JSON object per line)
3. In-memory index is updated with each new entry
4. On session resume, `TomeLedger` reads JSONL, rebuilds index, restores MvgeState
5. All writes are file-locked using `filelock` for cross-platform concurrency safety

### Extension Rune Flow

1. `load_runes_from_paths()` scans rune discovery paths
   for `manifest.json` files
2. Each manifest registers sigils (lifecycle hooks) with the `Sigil` system
3. During `MvgeHarness`, appropriate events are emitted to registered sigils
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
    execute(spell_cast_id, params, signal, on_update) -> SpellResult | str
    execution_mode: SpellExecutionMode  # sequential | parallel
}
```

### MvgeState (AgentState equivalent)

```typescript
interface MvgeState {
    system_prompt: str
    prompt_source: PromptSource
    model: dict | None
    contemplation_level: ContemplationLevel
    spells: list[MvgeSpell]
    invocations: list[MvgeInvocation]
    is_streaming: bool
    streaming_manifestation: MvgeInvocation | None
    pending_spell_casts: set[str]
    error_message: str | None
    mana_used: int
}
```

### MvgeEvent (AgentEvent equivalent)

Discriminated union of lifecycle events: agent_start, turn_start,
message_start, message_update, message_end, spell_casting_start/update/end,
turn_end, agent_end, compaction_start/end, queue_update.

## Technology Stack

- **Python**: >= 3.13
- **Package manager**: uv exclusively
- **Build system**: hatchling
- **Testing**: pytest with pytest-asyncio
- **Linting/formatting**: ruff
- **Type checking**: mypy (strict)
- **File locking**: filelock (cross-platform)
- **HTTP client**: httpx (provider realm)
- **CLI**: typer, rich (console rendering), prompt_toolkit (TUI)
- **Desktop GUI**: nicegui, pywebview (OS-native windowing)
- **Pre-commit**: pre-commit framework (ruff + mypy + pytest checks)
- **Config compliance**: dotagents protocol at `.agents/.mvgeos/`
- **Changelog**: git-cliff at `cliff.toml` — conventional commits
  → CHANGELOG.md
- **Releases**: `.github/workflows/release.yml` — tags `v*`
  trigger changelog + GitHub release
