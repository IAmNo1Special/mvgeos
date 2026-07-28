# MvgeOS Handoff Document for Fresh Agent

## Project Status Summary

**Location**: `C:\Users\ivmno\Desktop\mvgeos\`

**State**: Scaffold complete, all quality checks passing, MvgeLoop implemented with TDD (5 tests passing).

## Quality Status

| Check | Status |
|-------|--------|
| `uv run pytest --import-mode=importlib --cov` | 21 passed, 88% coverage |
| `uv run mypy` | Clean (37 source files) |
| `uv run ruff check` | Clean |
| `uv run ruff format` | Clean |

## Architecture

```
src/mvgeos/                    # Root namespace package
├── mvgeos-agent/             # Core Mvge loop, state, types
│   ├── src/mvgeos_agent/
│   │   ├── loop.py           # MvgeLoop - IMPLEMENTED (5 tests)
│   │   ├── types.py          # All core types (MvgeState, MvgeSpell, etc.)
│   │   └── __init__.py
│   └── tests/
│       ├── test_loop.py      # 5 tests
│       └── test_types.py     # 5 tests
├── mvgeos-provider/          # Realm protocol + OpenRouter
│   ├── src/mvgeos_provider/
│   │   ├── base.py           # Realm protocol (abstract)
│   │   ├── openrouter.py     # OpenRouterRealm - STUB
│   │   ├── types.py          # Model, ChannelConfig, RealmResponse
│   │   └── __init__.py
│   └── tests/
│       ├── test_realm.py     # 2 tests
│       └── test_types.py     # 2 tests
├── mvgeos-tome/              # Session persistence
│   ├── src/mvgeos_tome/
│   │   ├── ledger.py         # TomeLedger - IMPLEMENTED
│   │   ├── locking.py        # FileLock - IMPLEMENTED
│   │   ├── index.py          # Index - IMPLEMENTED
│   │   ├── jsonl_store.py    # JsonlStore - IMPLEMENTED
│   │   ├── types.py          # TomeEntry, TomeMetadata, etc.
│   │   └── __init__.py
│   └── tests/
│       ├── test_ledger.py    # 2 tests
│       └── test_types.py     # 2 tests
├── mvgeos-spells/            # Spell implementations
│   ├── src/mvgeos_spells/
│   │   ├── casting.py        # cast_bash - IMPLEMENTED
│   │   ├── reading.py        # cast_read - IMPLEMENTED
│   │   ├── writing.py        # cast_write - IMPLEMENTED
│   │   ├── editing.py        # cast_edit - IMPLEMENTED
│   │   ├── finding.py        # cast_find - IMPLEMENTED
│   │   ├── listing.py        # cast_list - IMPLEMENTED
│   │   ├── grep.py           # cast_grep - IMPLEMENTED
│   │   ├── types.py          # SpellResult, SpellStatus
│   │   └── __init__.py       # EXPORTS MISSING
│   └── tests/
│       ├── test_casting.py   # 1 test
│       └── test_types.py     # 2 tests
├── mvgeos-runes/             # Extension system
│   ├── src/mvgeos_runes/
│   │   ├── loader.py         # RuneLoader - STUB
│   │   ├── manifest.py       # load_manifest - STUB
│   │   ├── sigils.py         # SigilRegistry - STUB
│   │   ├── types.py          # RuneManifest, SigilHook
│   │   └── __init__.py       # EXPORTS MISSING
│   └── tests/
│       └── (no tests yet)
├── mvgeos-cli/               # CLI entry point
│   ├── src/mvgeos/
│   │   ├── main.py           # main() - STUB
│   │   ├── commands/
│   │   │   ├── prompt.py     # EMPTY
│   │   │   ├── tome.py       # EMPTY
│   │   │   ├── config.py     # EMPTY
│   │   │   └── __init__.py   # EMPTY
│   │   └── __init__.py
│   └── tests/
│       └── (no tests yet)
└── __init__.py               # Root package
```

## What's Implemented

### mvgeos-agent (COMPLETE)
- `MvgeLoop` - Full agent loop with:
  - Streaming response handling
  - Spell/tool call execution
  - Event emission (MESSAGE_UPDATE, SPELL_CASTING_START/END, AGENT_START/END)
  - Mana budget enforcement
  - Error handling
- 5 tests covering: single turn, spell casting, mana exhaustion, error handling, empty invocations

### mvgeos-tome (COMPLETE)
- `TomeLedger` - JSONL session persistence with file locking
- `FileLock` - Cross-process file locking
- `Index` - Entry indexing with parent/child/leaf tracking
- `JsonlStore` - Append/read JSONL entries
- 4 tests covering ledger and types

### mvgeos-spells (PARTIAL)
- All 7 spell implementations done: bash, read, write, edit, find, list, grep
- Types: SpellResult, SpellStatus
- Tests: Only bash and types tested (3 tests total)
- `__init__.py` missing exports

### mvgeos-provider (STUB)
- `Realm` protocol defined
- `OpenRouterRealm` has skeleton with yield stub
- Tests only for types

### mvgeos-runes (STUB)
- Types defined
- Loader, manifest, sigils are stubs
- No tests

### mvgeos-cli (STUB)
- Main entry point prints help
- Command modules empty
- No tests

## Next Work (Priority Order)

### 1. Complete mvgeos-spells
```bash
# Add exports to __init__.py
# Add tests for reading.py, writing.py, editing.py, finding.py, listing.py, grep.py
```

### 2. Implement OpenRouterRealm (mvgeos-provider)
```python
# Real HTTP streaming to OpenRouter API
# Handle: tool calls, content streaming, error recovery
# Tests for streaming behavior
```

### 3. Implement mvgeos-runes
```python
# RuneLoader: discover, load, validate extensions
# Manifest: parse manifest.json
# SigilRegistry: hook registration/calling
# Tests for all three
```

### 4. Implement mvgeos-cli commands
```python
# prompt.py: prompt <incantation> - start agent loop
# tome.py: tome list|show|export - session management
# config.py: config show|set - configuration
# Tests for CLI integration
```

## Key Files to Read First

1. `src/mvgeos/mvgeos-agent/src/mvgeos_agent/types.py` - Core type definitions
2. `src/mvgeos/mvgeos-agent/src/mvgeos_agent/loop.py` - Implemented loop (reference)
3. `src/mvgeos/mvgeos-agent/tests/test_loop.py` - Test patterns
4. `src/mvgeos/mvgeos-provider/src/mvgeos_provider/types.py` - Provider types
5. `src/mvgeos/mvgeos-tome/src/mvgeos_tome/ledger.py` - Session persistence reference
5. `src/mvgeos/mvgeos-spells/src/mvgeos_spells/casting.py` - Spell pattern reference

## MvgeOS Terminology (Use consistently)

| Concept | Type/Term |
|---------|-----------|
| Agent | Mvge |
| Tool | Spell |
| Toolset | Grimoire |
| Token | Mana |
| Provider | Realm |
| Session | Tome |
| Prompt | Incantation |
| Response | Manifestation |
| Extension | Rune |
| Callback | Sigil |
| Credential | Relic |

## TDD Workflow

```bash
# 1. Write failing test in tests/test_<module>.py
# 2. Run: uv run pytest --import-mode=importlib src/mvgeos/<pkg>/tests/test_<module>.py -v
# 3. Implement in src/mvgeos/<pkg>/src/mvgeos_<pkg>/<module>.py
# 4. Run test again until green
# 5. Run all: uv run pytest --import-mode=importlib --cov
# 6. Check: uv run mypy && uv run ruff check && uv run ruff format --check
```

## Running Commands

```bash
cd C:\Users\ivmno\Desktop\mvgeos

# Sync deps
uv sync --all-packages

# Run all tests
uv run pytest --import-mode=importlib --cov

# Run specific package tests
uv run pytest --import-mode=importlib src/mvgeos/mvgeos-agent/tests/

# Type check
uv run mypy -p mvgeos_agent -p mvgeos_provider -p mvgeos_tome -p mvgeos_spells -p mvgeos_runes -p mvgeos

# Lint/format
uv run ruff check
uv run ruff format --check

# Format
uv run ruff format
```

## Common Patterns

### Async Test Fixtures
```python
@pytest.fixture
def mock_spell() -> MvgeSpell:
    spell = MagicMock(spec=MvgeSpell)
    spell.name = "test_spell"
    spell.execute = AsyncMock(return_value={"result": "ok"})
    return spell
```

### Async Generator for Realm Streams
```python
def _make_stream(responses: list[RealmResponse]) -> AsyncIterator[RealmResponse]:
    async def gen() -> AsyncIterator[RealmResponse]:
        for r in responses:
            yield r

    return gen()
```

### Spell Implementation Pattern
```python
async def cast_bash(command: str, timeout_ms: int = 30000) -> SpellResult:
    try:
        proc = await asyncio.create_subprocess_shell(...)
        ...
    except Exception as exc:
        return SpellResult(
            spell_name="bash", status=SpellStatus.ERROR, error_message=str(exc)
        )
```

## CI Configuration

`.github/workflows/ci.yml` runs:
- `uv sync`
- `uv run pytest --import-mode=importlib --cov --cov-fail-under=90`
- `uv run ruff check`
- `uv run ruff format --check`
- `uv run mypy`

## Known Issues

1. **mvgeos-spells `__init__.py`** - Missing exports, need to add:
   ```python
   from mvgeos_spells.casting import cast_bash
   from mvgeos_spells.reading import cast_read

   # ... etc
   __all__ = ["cast_bash", "cast_read", ...]
   ```

2. **mvgeos-runes** - No tests, all modules are stubs

3. **mvgeos-cli** - Completely empty, needs full implementation

4. **Coverage** - Currently 88%, need 90%+ for CI (add more tests to reach target)

## AGENTS.md Location

Project-specific rules in `AGENTS.md` at repo root. Always reference it.

---

**Prompt for Fresh Agent**:

> Continue TDD implementation of MvgeOS MVP features. Start with completing mvgeos-spells (add exports and tests for remaining spells), then implement OpenRouterRealm streaming in mvgeos-provider, then mvgeos-runes extension system, then mvgeos-cli commands. All work must follow red-green-refactor TDD cycle. Quality gates: `uv run pytest --import-mode=importlib --cov`, `uv run mypy`, `uv run ruff check`, `uv run ruff format --check` must all pass.