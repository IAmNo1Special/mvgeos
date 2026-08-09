# coding-Mvge — Agent Instructions

This package implements the concrete coding agent: `CodingMvge` extends `BaseMvge` with coding-specific spells (bash, read, edit, write, grep, find, ls), system prompt configuration, and multi-turn loop with steering/followup queues.

## Package-Specific Conventions

- All code follows the red-green-refactor TDD cycle: write failing test first, then implement
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Mock sync methods with `MagicMock()`, async methods with `AsyncMock()` — mixing causes "coroutine never awaited" warnings

## Testing

```bash
# Run this package's tests
uv run pytest coding-mvge/tests_coding_mvge/

# Run with coverage
uv run pytest coding-mvge/tests_coding_mvge/ --cov
```

Test paths follow pattern: `coding-mvge/tests_coding_mvge/test_<module>.py`

## Key Types

| Type | Purpose |
| --- | --- |
| `CodingMvge(BaseMvge)` | Concrete coding agent with spell selection and system prompt |
| `DEFAULT_SPELL_MAP` | Name → `cast_*` function map |

## Built-in Spells

| Spell | Function | Purpose |
| --- | --- |
| `bash` | `cast_bash` | Execute shell commands |
| `read` | `cast_read` | Read files |
| `edit` | `cast_edit` | Edit files using diff-based replacement |
| `write` | `cast_write` | Write files |
| `grep` | `cast_grep` | Search file contents |
| `find` | `cast_find` | Find files by glob |
| `ls` | `cast_list` | List directory contents |

## Dependencies

- `mvgeos-agent` — core agent loop and types
- `mvgeos-provider` — Realm protocol and providers
- `mvgeos-tome` — Tome persistence
- `mvgeos-runes` — Rune system

## Architecture

- `CodingMvge._build_spells()` returns the list of enabled spells
- `_build_system_prompt()` loads `SYSTEM.md`/`GUIDELINES.md` from `~/.agents/.mvgeos/{name}/`
- `BaseMvge._run_impl()` delegates to `MvgeHarness.run()` which calls `MvgeLoop.run()` (nested outer/inner loops)
- Harness owns compaction, `should_stop_after_turn`, `prepare_next_turn`, steering/follow-up queues
- Spell schemas are generated from type hints via `generate_spell_schema()` (from `mvgeos_agent.spell_schema`)
