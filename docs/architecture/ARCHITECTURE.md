# MvgeOS Architecture

## High-Level Structure

```text
mvgeos/
├── mvgeos-agent/         # Core Mvge loop, invocations, state, spell execution
├── mvgeos-provider/      # Realm protocol + repository of realms
├── mvgeos-tome/          # JSONL session persistence with locking + index
├── mvgeos-runes/         # Extension manifest, loader, sigil hooks
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
authentication resolution, non-channeled completion, and response delivery.

**Entry point**: `Realm.stream(model, invocations, config)`
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
and hooks. `load_runes_from_paths` discovers and loads runes from
configured scopes. `SigilHook` defines lifecycle
points where runes can register Sigil callbacks.

**Entry point**: `load_runes_from_paths()` → discovers manifests
→ registers sigils → emits MvgeEvents on hooks

**Dependencies**: importlib.util, watchdog

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

**Dependencies**: mvgeos-agent, mvgeos-provider, mvgeos-tome,
mvgeos-runes, rich, typer, prompt_toolkit

### mvgeos-gui

Native desktop graphical user interface matching the 1:1 Google Antigravity IDE
design. Connects directly to `CodingMvge` and `MvgeHarness` in-process with a live
event bus. Provides a three-column layout with project navigation, interactive chat
viewport with step cards, floating autocomplete input dock (`@` mentions, `/` commands),
git diff viewer, and slide-over artifact markdown inspector.

**Entry point**: `mvgeos-gui` command → `mvgeos_gui.main:main`

**Dependencies**: nicegui, pywebview, pathspec, coding-mvge, mvgeos-agent,
mvgeos-cli, mvgeos-provider, mvgeos-runes, mvgeos-tome

### coding-mvge

Pre-configured coding agent package providing `root_mvge = Mvge(name="coding_mvge")`.
Decomposes built-in development spells (`bash`, `read`, `write`, `edit`, `find`,
`list_files`, `grep`) into modular files within `coding_mvge/spells/` and colocates
`SYSTEM.md`, `GUIDELINES.md`, and authoring guides (`AGENTS.md`) for autonomous
self-modification and zero-boilerplate instantiation.

**Entry point**: `from coding_mvge import root_mvge` → `root_mvge.run(prompt)`

**Dependencies**: mvgeos-agent, mvgeos-provider, mvgeos-tome, mvgeos-runes

## Data Flow

### Invocation Flow

1. User provides input via CLI or TUI
2. CLI creates `BaseMvge`/`CodingMvge` instance with configured realms
3. `BaseMvge.run(prompt)` → normalizes input to `SummonerRequest`
4. `BaseMvge.initialize()` creates `MvgeHarness` (wraps `MvgeLoop`, owns lifecycle and compaction)
5. `BaseMvge._run_impl()` delegates to `MvgeHarness.run()`
6. `MvgeHarness.run()` delegates to `MvgeLoop.run()` (nested outer/inner loops)
7. Loop calls `Realm.stream(model, invocations, config)` on configured realm
8. Provider channels `RealmResponse` events (text deltas, tool calls, etc.)
9. `MvgeLoop` processes events → updates `MvgeState` → emits `MvgeEvent` to subscribers
10. Tool calls detected → `SpellDispatcher.execute_spells()` → `Spell.execute()` → results appended to invocations
11. Loop continues until no more tool calls and no steering/follow-up invocations
12. `MvgeHarness` handles compaction (after each invocation), `should_stop_after_turn`,
    `prepare_next_turn`, steering/follow-up queue drainage
13. Final `MvgeResponse` emitted with `done` event

### Tome Persistence Flow

1. `MvgeLoop` emits `turn_end` event
2. `TomeLedger` writes each new entry to JSONL file (one JSON object per line)
3. In-memory index is updated with each new entry
4. On session resume, `TomeLedger` reads JSONL, rebuilds index, restores MvgeState
5. All writes are file-locked using `filelock` for cross-platform concurrency safety

### Extension Rune Flow

1. `load_runes_from_paths()` scans rune discovery paths
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

- **Python**: >= 3.14
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
