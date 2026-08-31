# coding-Mvge — Agent Instructions

This package implements the concrete coding agent: `CodingMvge` extends `BaseMvge` with coding-specific spells (bash, read, edit, write, grep, find, list), system prompt configuration, and multi-turn loop with steering/followup queues.

## Package-Specific Conventions

- All code follows the red-green-refactor TDD cycle: write failing test first, then implement
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Mock sync methods with `MagicMock()`, async methods with `AsyncMock()` — mixing causes "coroutine never awaited" warnings

## Testing

```bash
# Run this package's tests
uv run python -m pytest coding-mvge/tests/

# Run with coverage
uv run python -m pytest coding-mvge/tests/ --cov
```

Test paths follow pattern: `coding-mvge/tests/unit/<module>.py` and `coding-mvge/tests/integration/<module>.py`

## Key Types

| Type | Purpose |
| --- | --- |
| `CodingMvge(BaseMvge)` | Concrete coding agent with spell selection and system prompt |
| `BUILTIN_SPELL_MAP` / `DEFAULT_SPELL_MAP` | Name → `cast_*` function map |

## Built-in Spells

| Spell | Function | Purpose |
| --- | --- | --- |
| `bash` | `cast_bash` | Execute shell commands |
| `read` | `cast_read` | Read files |
| `edit` | `cast_edit` | Edit files using diff-based replacement |
| `write` | `cast_write` | Write files |
| `grep` | `cast_grep` | Search file contents |
| `find` | `cast_find` | Find files by glob |
| `list` | `cast_list` | List directory contents |

## Dependencies

- `mvgeos-agent` — core agent loop and types
- `mvgeos-provider` — Realm protocol and providers
- `mvgeos-tome` — Tome persistence
- `mvgeos-runes` — Rune system

## Architecture

- `CodingMvge._build_spells()` returns the list of active rune spells and enabled built-in spells
- System prompt and guidelines resolution is handled via `MvgeEnvironment` (`PromptLoader` / `PromptSource`)
- `BaseMvge._run_impl()` delegates to `MvgeLoop.run()` (turn cycle with steering/follow-up handling)
- `MvgeHarness` owns session lifecycle, compaction, `should_stop_after_turn`, and `prepare_next_turn`
- Spell schemas are generated from type hints via `generate_spell_schema()` (from `mvgeos_agent.spell_schema`)
