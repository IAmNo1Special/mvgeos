# MvgeOS Specification (SPEC.md)

## Overview

MvgeOS is a Python-based AI coding agent inspired by the pi project, built with clean-room implementation using Mvge-specific terminology. It follows TDD strictly and targets Python 3.14+ with `uv` for dependency management.

## Architecture

### Monorepo Structure (uv workspaces)

```text
mvgeos/
├── mvgeos-agent/             # Core agent loop, state, types
├── mvgeos-provider/          # Realm protocol + OpenRouter provider
├── mvgeos-tome/              # JSONL session persistence with file locking
├── mvgeos-spells/            # Spell implementations (tools)
├── mvgeos-runes/             # Extension system (manifest, loader, sigils)
├── mvgeos-cli/               # CLI entry point
└── pyproject.toml            # Root workspace config
```

### Package Details

| Package | Module | Purpose |
| --------- | --------- | --------- |
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

Session persistence:

- `create_tome(metadata)` - Create new session
- `open_tome(tome_id)` - Open existing session
- `append(tome_id, entry)` - Append entry to session
- `get_entries(tome_id, entry_type, limit)` - Retrieve entries
- `get_leaf_id(tome_id)` - Get current leaf for branching
- Uses `FileLock` for cross-process safety
- JSONL storage with index

All 7 spells implemented:

- `cast_bash` - Shell command execution with timeout
- `cast_read` - File reading
- `cast_write` - File writing with parent dir creation
- `cast_edit` - String replacement in files
- `cast_find` - Glob pattern file finding
- `cast_list` - Directory listing (recursive/non-recursive)
- `cast_grep` - Regex pattern matching in files

## Remaining Work (Priority Order)

### 1. Implement zerocontext Rune (planned)

**ADR**: `docs/adr/0007-zerocontext-as-rune.md`

Port the zerocontext skill system as an mvgeos-runes extension:

- `mvgeos-runes`: loader, manifest, sigils (prereq) ✅
- `zerocontext` rune package structure
  - `zerocontext_registry.py` — port with frozen-skill fix (ADR #6)
  - `zerocontext_toolset.py` — port with `execute_capability` rename (ADR #2)
  - `zerocontext_tool.py` — fix phantom `execute_capability` reference
  - `tools.py` — `CapabilityExecutor`, `ActivateSkillTool`, `RunSkillScriptTool`
  - `batch_executor.py` — `ExecuteCapabilityTool` (renamed), input copy fix (ADR #8)
  - `wrappers.py` — **remove** `BudgetEnforcingSpellWrapper` (ADR #5, #10)
  - `__init__.py` — exports
- `ZEROCONTEXT_DISCOVERY_INSTRUCTION` rewrite (ADR #3)
- `prune_ephemeral_schemas` key fix (ADR #1)
- `zerocontext` rune manifest + entry point
- Integration tests: rune load → toolset → harness
- Wire into MvgeLoop via rune loader (not hardcoded)

### Open Decisions (from ADR)

- Capability threshold config (`rune_config.capability_threshold`)
- DCI-style `grep`/`read` tools for skill drilling (ADR #4)
- Keyword scoring → dual-match embeddings (ADR #3)

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
| --------------- | ------------- |
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
