# mvgeos-CLI — Agent Instructions

This package implements the CLI entry point (`mvgeos` command): one-shot prompt execution, REPL, TUI, Tome management, and configuration management.

## Package-Specific Conventions

- All code follows the red-green-refactor TDD cycle: write failing test first, then implement
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Mock sync methods with `MagicMock()`, async methods with `AsyncMock()` — mixing causes "coroutine never awaited" warnings

## Testing

```bash
# Run this package's tests
uv run pytest mvgeos-cli/tests_cli/

# Run with coverage
uv run pytest mvgeos-cli/tests_cli/ --cov
```

Test paths follow pattern: `mvgeos-cli/tests_cli/test_<module>.py`

## Key Types

| Type | Purpose |
| --- | --- |
| `app` | Typer entry point (`mvgeos` command) |
| `run_repl` | Streaming REPL with `StreamRenderer` |
| `run_tui` | Full-screen prompt_toolkit TUI |
| `StreamRenderer` | Renders channeled tokens to console |
| `ConsoleSink` / `Sink` | Output sinks for streaming |
| `SlashCompleter` | Tab completion for slash commands |
| `tome_app` | Tome management CLI (list/show/export/create/fork) |
| `config_app` | Config CLI (show/set/get/reset/path) |

## Commands

| Command | Purpose |
| --- | --- |
| `mvgeos <prompt>` | Run a one-shot prompt (or start REPL/TUI if omitted) |
| `mvgeos tome list` | List all tomes |
| `mvgeos tome show <id>` | Show Tome contents |
| `mvgeos tome export <id>` | Export Tome to file |
| `mvgeos tome create` | Create new Tome |
| `mvgeos tome fork <id>` | Fork Tome from a leaf |
| `mvgeos config show` | Show configuration |
| `mvgeos config set <key> <value>` | Set configuration value |
| `mvgeos config path` | Show configuration file path |

## Dependencies

- `typer` — CLI framework
- `rich` — console rendering
- `prompt_toolkit` — TUI framework
- `mvgeos-agent` — core agent loop
- `mvgeos-provider` — Realm protocol and providers
- `mvgeos-runes` — Rune system
- `coding-mvge` — Concrete coding agent

## Architecture

- One-shot path: `main.py` → creates `CodingMvge` → runs single prompt
- REPL path: `commands/repl.py` → interactive loop with streaming
- TUI path: `commands/tui.py` — full-screen interface
- All paths use `MvgeLoop` for the core turn loop
- Rune-registered commands and shortcuts are exposed via `runner.get_commands()` and `runner.get_shortcuts()`
