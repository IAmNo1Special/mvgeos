# MvgeOS Specification (SPEC.md)

## Overview

MvgeOS is a Python-based AI coding agent inspired by the pi project, built with clean-room implementation using Mvge-specific terminology. It follows TDD strictly and targets Python 3.14+ with `uv` for dependency management.

## Architecture

### Monorepo Structure (uv workspaces)

```
src/mvgeos/                    # Root namespace package
├── mvgeos-agent/             # Core agent loop, state, types
├── mvgeos-provider/          # Realm protocol + OpenRouter provider
├── mvgeos-tome/              # JSONL session persistence with file locking
├── mvgeos-spells/            # Spell implementations (tools)
├── mvgeos-runes/             # Extension system (manifest, loader, sigils)
├── mvgeos-cli/               # CLI entry point
└── __init__.py               # Root package
```

### Package Details

| Package | Module | Purpose |
|---------|--------|---------|
| mvgeos-agent | `types.py` | MvgeState, MvgeSpell, MvgeInvocation, MvgeEvent, enums |
| mvgeos-agent | `loop.py` | MvgeLoop - main agent loop with streaming |
| mvgeos-provider | `base.py` | Realm protocol (abstract base) |
| mvgeos-provider | `openrouter.py` | OpenRouterRealm implementation |
| mvgeos-provider | `types.py` | Model, ChannelConfig, RealmResponse |
| mvgeos-tome | `ledger.py` | TomeLedger - session management |
| mvgeos-tome | `locking.py` | FileLock - cross-process locking |
| mvgeos-tome | `index.py` | Index - entry indexing |
| mvgeos-tome | `jsonl_store.py` | JsonlStore - JSONL append/read |
| mvgeos-tome | `types.py` | TomeEntry, TomeMetadata, TomeEntryType |
| mvgeos-spells | `casting.py` | cast_bash |
| mvgeos-spells | `reading.py` | cast_read |
| mvgeos-spells | `writing.py` | cast_write |
| mvgeos-spells | `editing.py` | cast_edit |
| mvgeos-spells | `finding.py` | cast_find |
| mvgeos-spells | `listing.py` | cast_list |
| mvgeos-spells | `grep.py` | cast_grep |
| mvgeos-spells | `types.py` | SpellResult, SpellStatus |
| mvgeos-runes | `loader.py` | RuneLoader |
| mvgeos-runes | `manifest.py` | load_manifest |
| mvgeos-runes | `sigils.py` | SigilRegistry |
| mvgeos-runes | `types.py` | RuneManifest, SigilHook |
| mvgeos-cli | `main.py` | CLI entry point |
| mvgeos-cli | `commands/prompt.py` | `mvgeos prompt` command |
| mvgeos-cli | `commands/tome.py` | `mvgeos tome` command |
| mvgeos-cli | `commands/config.py` | `mvgeos config` command |

## Core Types

### mvgeos-agent/types.py

```python
class ContemplationLevel(StrEnum):
    OFF, MINIMAL, LOW, MEDIUM, HIGH, XHIGH, MAX


class SpellExecutionMode(StrEnum):
    SEQUENTIAL, PARALLEL


class MvgeEventType(StrEnum):
    (
        AGENT_START,
        AGENT_END,
        TURN_START,
        TURN_END,
        MESSAGE_START,
        MESSAGE_UPDATE,
        MESSAGE_END,
        SPELL_CASTING_START,
        SPELL_CASTING_UPDATE,
        SPELL_CASTING_END,
    )


class StopReason(StrEnum):
    PENDING, STOP, LENGTH, SPELL_USE, ERROR, ABORTED


@dataclass
class SummonerRequest:
    role: str = "user"
    content: str | list[dict[str, Any]] | None = None
    timestamp: float = 0.0


@dataclass
class MvgeResponse:
    role: str = "assistant"
    content: list[dict[str, Any]] = field(default_factory=list)
    realm: str = ""
    model: str = ""
    mana_usage: dict[str, float] = field(default_factory=dict)
    stop_reason: StopReason = StopReason.PENDING
    error_message: str | None = None
    timestamp: float = 0.0


@dataclass
class SpellResultMessage:
    role: str = "spellResult"
    spell_cast_id: str = ""
    spell_name: str = ""
    content: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] | None = None
    is_error: bool = False
    timestamp: float = 0.0


MvgeInvocation = SummonerRequest | MvgeResponse | SpellResultMessage


@dataclass
class MvgeSpell:
    name: str
    description: str
    parameters: dict[str, Any]
    execution_mode: SpellExecutionMode = SpellExecutionMode.PARALLEL

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> dict[str, Any]: ...


@dataclass
class MvgeState:
    system_prompt: str = ""
    model: dict[str, Any] | None = None
    contemplation_level: ContemplationLevel = ContemplationLevel.OFF
    spells: list[MvgeSpell] = field(default_factory=list)
    invocations: list[MvgeInvocation] = field(default_factory=list)
    is_streaming: bool = False
    streaming_manifestation: MvgeInvocation | None = None
    pending_spell_casts: set[str] = field(default_factory=set)
    error_message: str | None = None
    mana_budget: int | None = None
    max_tokens: int | None = None
    temperature: float | None = None


@dataclass
class MvgeEvent:
    type: MvgeEventType
    data: dict[str, Any] = field(default_factory=dict)
```

### mvgeos-provider/types.py

```python
@dataclass
class Model:
    id: str
    name: str
    realm: str
    provider: str
    base_url: str
    api_key: str
    mana_limit: int = 0
    context_window: int = 128000
    max_tokens: int = 4096
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ChannelConfig:
    model: Model
    temperature: float = 0.7
    max_tokens: int = 4096
    mana_limit: int | None = None
    timeout_ms: int = 60000
    max_retries: int = 3
    meta_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RealmResponse:
    model: Model
    invocation: MvgeResponse | None = None
    mana_used: int = 0
    stop_reason: str = "stop"
    error_message: str | None = None
```

### mvgeos-tome/types.py

```python
class TomeEntryType(StrEnum):
    (
        INVOCATION,
        SPELL_RESULT,
        MODEL_CHANGE,
        CONTEMPLATION_LEVEL_CHANGE,
        TOOL_CALLS_CHANGE,
        LABEL,
        BRANCH_SUMMARY,
        COMPACTION,
        CUSTOM,
        CUSTOM_MESSAGE,
        LEAF,
        SESSION_INFO,
    )


@dataclass
class TomeEntry:
    id: str
    parent_id: str | None
    type: TomeEntryType
    timestamp: float
    payload: dict[str, Any]


@dataclass
class TomeMetadata:
    id: str
    created_at: str
    cwd: str
    parent_tome_id: str | None = None
    active_leaf_id: str | None = None
    schema_version: str = "1.0"
```

### mvgeos-spells/types.py

```python
class SpellStatus(StrEnum):
    SUCCESS, ERROR, PARTIAL


@dataclass
class SpellResult:
    spell_name: str
    status: SpellStatus = SpellStatus.SUCCESS
    content: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
```

### mvgeos-runes/types.py

```python
class SigilHook(StrEnum):
    (
        BEFORE_INVOCATION,
        AFTER_INVOCATION,
    )
    (
        BEFORE_SPELL_CAST,
        AFTER_SPELL_RESULT,
    )
    (
        BEFORE_PROVIDER_REQUEST,
        AFTER_PROVIDER_RESPONSE,
    )
    (BEFORE_PROVIDER_HEADERS,)
    (
        TURN_START,
        TURN_END,
    )
    (
        SESSION_START,
        SESSION_SHUTDOWN,
    )
    (
        SESSION_BEFORE_SWITCH,
        SESSION_BEFORE_FORK,
    )
    CONTEXT_TRANSFORM


@dataclass
class RuneManifest:
    name: str
    version: str
    description: str
    hooks: list[SigilHook] = field(default_factory=list)
    entry_point: str = ""
```

## Implemented Components

### MvgeLoop (mvgeos-agent/loop.py)

Main agent loop with:
- Streaming response handling via async iterator
- Spell/tool call execution with event emission
- Mana budget enforcement
- Event emission: AGENT_START, MESSAGE_UPDATE, SPELL_CASTING_START/END, AGENT_END
- Error handling with proper cleanup

### TomeLedger (mvgeos-tome/ledger.py)

Session persistence:
- `create_tome(metadata)` - Create new session
- `open_tome(tome_id)` - Open existing session
- `append(tome_id, entry)` - Append entry to session
- `get_entries(tome_id, entry_type, limit)` - Retrieve entries
- `get_leaf_id(tome_id)` - Get current leaf for branching
- Uses `FileLock` for cross-process safety
- JSONL storage with index

### Spell Implementations (mvgeos-spells/)

All 7 spells implemented:
- `cast_bash` - Shell command execution with timeout
- `cast_read` - File reading
- `cast_write` - File writing with parent dir creation
- `cast_edit` - String replacement in files
- `cast_find` - Glob pattern file finding
- `cast_list` - Directory listing (recursive/non-recursive)
- `cast_grep` - Regex pattern matching in files

## Remaining Work (Priority Order)

### 1. Complete mvgeos-spells ✅

**File**: `src/mvgeos/mvgeos-spells/src/mvgeos_spells/__init__.py`

Add exports:
```python
from mvgeos_spells.casting import cast_bash
from mvgeos_spells.reading import cast_read
from mvgeos_spells.writing import cast_write
from mvgeos_spells.editing import cast_edit
from mvgeos_spells.finding import cast_find
from mvgeos_spells.listing import cast_list
from mvgeos_spells.grep import cast_grep

__all__ = [
    "cast_bash",
    "cast_read",
    "cast_write",
    "cast_edit",
    "cast_find",
    "cast_list",
    "cast_grep",
]
```

**Tests needed** (each in `tests/test_<spell>.py`):
- test_cast_read: read existing, read non-existent, encoding
- test_cast_write: write new, overwrite, create dirs
- test_cast_edit: exact match, no match, multiple occurrences
- test_cast_find: pattern match, no match, recursive
- test_cast_list: non-recursive, recursive, non-existent
- test_cast_grep: content match, line numbers, output modes

### 2. Implement OpenRouterRealm (mvgeos-provider/openrouter.py) ✅

**Requirements**:
- Real HTTP streaming to OpenRouter API (`https://openrouter.ai/api/v1/chat/completions`)
- Handle: tool calls (function calling), content streaming, stop reasons
- Map MvgeInvocation history to OpenAI-compatible messages
- Proper error handling: retries, timeouts, rate limits
- Mana tracking from response headers
- Async iteration yielding `RealmResponse` objects

**Key methods**:
```python
async def stream(
    self,
    model: Model,
    invocations: list[MvgeInvocation],
    config: ChannelConfig,
) -> AsyncIterator[RealmResponse]:
    # Build messages from invocations
    # POST to /chat/completions with stream=True
    # Parse SSE stream
    # Yield RealmResponse for each chunk
```

**Tests needed**:
- Mock HTTP responses, test tool call parsing, content streaming, error handling

### 3. Implement mvgeos-runes ✅

**Files to implement**:
- `src/mvgeos/mvgeos-runes/src/mvgeos_runes/loader.py` - `RuneLoader`
  - `discover_runes(paths: list[Path]) -> list[RuneManifest]`
  - `load_rune(manifest: RuneManifest) -> ModuleType`
  - Validate entry points, hooks

- `src/mvgeos/mvgeos-runes/src/mvgeos_runes/manifest.py` - `load_manifest(path: Path) -> RuneManifest`
  - Parse JSON manifest, validate schema

- `src/mvgeos/mvgeos-runes/src/mvgeos_runes/sigils.py` - `SigilRegistry`
  - `register(hook: SigilHook, handler: Callable) -> None`
  - `emit(hook: SigilHook, data: Any) -> None`
  - Handle async/sync handlers

**Tests needed**: Discovery, loading, hook registration/emission, error cases

### 4. Implement mvgeos-cli Commands ✅

**Files to implement**:
- `src/mvgeos/mvgeos-cli/src/mvgeos/commands/prompt.py` - `prompt` command
  - `async def prompt(incantation: str, config: Config) -> None`
  - Create MvgeState, load spells, create Realm, run MvgeLoop
  - Handle streaming output to console

- `src/mvgeos/mvgeos-cli/src/mvgeos/commands/tome.py` - `tome` command
  - `tome list` - List all sessions
  - `tome show <id>` - Show session details
  - `tome export <id> <format>` - Export to JSON/Markdown

- `src/mvgeos/mvgeos-cli/src/mvgeos/commands/config.py` - `config` command
  - `config show` - Display current config
  - `config set <key> <value>` - Set config value
  - Config file at `.agents/mvgeos/config.json`

**Main entry**: `src/mvgeos/mvgeos-cli/src/mvgeos/main.py`
```python
def main() -> None:
    app = typer.Typer()
    app.add_typer(prompt_app, name="prompt")
    app.add_typer(tome_app, name="tome")
    app.add_typer(config_app, name="config")
    app()
```

## Configuration

### dotagents Protocol

Config at `.agents/mvgeos/`:
- `config.json` - Main config (model, mana_budget, spells_enabled, etc.)
- `sessions/` - Tome directories (managed by TomeLedger)
- `extensions/manifest.json` - Extension manifest

### Config Schema

```json
{
  "model": "openrouter/anthropic/claude-3.5-sonnet",
  "mana_budget": 10000,
  "max_tokens": 4096,
  "temperature": 0.7,
  "contemplation_level": "medium",
  "spells_enabled": ["bash", "read", "write", "edit", "find", "list", "grep"],
  "runes_paths": [".agents/mvgeos/extensions"]
}
```

## Quality Gates

```bash
# All must pass before committing
uv run pytest --import-mode=importlib --cov
uv run mypy -p mvgeos_agent -p mvgeos_provider -p mvgeos_tome -p mvgeos_spells -p mvgeos_runes -p mvgeos
uv run ruff check
uv run ruff format --check
```

Coverage target: **90%+** (CI enforced)

## TDD Rules

1. **Write failing test first** - Red
2. **Implement minimal code** - Green
3. **Refactor** - Clean up, ensure types pass
4. **Run all quality gates** - Verify

Test naming: `test_<function>_<scenario>`
- `test_loop_single_turn_no_spells`
- `test_loop_with_spell_cast`
- `test_loop_mana_exhaustion`
- `test_cast_bash_success`
- `test_cast_bash_timeout`

## MvgeOS Terminology Reference

| Standard Term | MvgeOS Term |
|---------------|-------------|
| Agent | Mvge |
| Tool | Spell |
| Toolset | Grimoire |
| Token | Mana |
| Context Window | Mana Pool |
| Provider | Realm |
| Session | Tome |
| Prompt | Incantation |
| Response | Manifestation |
| Extension | Rune |
| Callback | Sigil |
| Credential | Relic |
| API Key | Arcane Key |
| OAuth | Covenant |

Use these terms consistently in code, docs, and comments.

## Git Workflow

- Branch per feature
- Conventional commits: `feat(mvgeos-agent): add spell execution`
- **Changelog**: git-cliff at `cliff.toml` — generates CHANGELOG.md from commits
- **Release**: `.github/workflows/release.yml` — push `v*` tag or manual dispatch to create release
- Pre-commit: ruff, mypy, pytest
- No direct commits to main without PR

## License

MIT - See `LICENSE` file.