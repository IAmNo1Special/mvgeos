# mvgeos-Runes — Agent Instructions

This package implements the Rune system: extension manifest parsing, dynamic loading, sigil hook registry, and hot reload. Runes are MvgeOS extensions that hook into the agent lifecycle.

## Package-Specific Conventions

- All code follows the red-green-refactor TDD cycle: write failing test first, then implement
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Mock sync methods with `MagicMock()`, async methods with `AsyncMock()` — mixing causes "coroutine never awaited" warnings

## Testing

```bash
# Run this package's tests
uv run pytest mvgeos-runes/tests/

# Run with coverage
uv run pytest mvgeos-runes/tests/ --cov
```

Test paths follow pattern: `mvgeos-runes/tests/unit/<module>.py` and `mvgeos-runes/tests/integration/<module>.py`

## Key Types

| Type | Purpose |
| --- | --- |
| `RuneManifest` | Rune metadata (name, version, description, hooks, entry_point) |
| `RuneLoader` | Discovery and loading of runes from paths |
| `RuneRunner` | Extension host: registers sigils/spells/commands/shortcuts/providers |
| `RuneAPI` | Facade handed to rune factories |
| `RuneFactory` | `Callable[[RuneAPI], None \| Awaitable[None]]` |
| `SigilHook` | Enum of 17 lifecycle hook names |
| `SigilRegistry` | Hook → handlers map |
| `RuneWatcher` | watchdog-based hot reload |

## SigilHook Values

| Hook | When Fired |
| --- | --- |
| `BEFORE_INVOCATION` | Before an invocation is processed |
| `AFTER_INVOCATION` | After an invocation is processed |
| `BEFORE_SPELL_CAST` | Before a spell is executed (can block) |
| `AFTER_SPELL_RESULT` | After a spell result is received |
| `BEFORE_PROVIDER_REQUEST` | Before sending request to Realm |
| `AFTER_PROVIDER_RESPONSE` | After receiving response from Realm |
| `BEFORE_PROVIDER_HEADERS` | Before provider headers are finalized |
| `TURN_START` / `TURN_END` | Turn lifecycle |
| `AGENT_START` / `AGENT_END` | Agent lifecycle |
| `SESSION_START` / `SESSION_SHUTDOWN` | Session lifecycle |
| `SESSION_BEFORE_SWITCH` / `SESSION_BEFORE_FORK` | Session switch/fork |
| `CONTEXT_TRANSFORM` | Transform invocations before sending to Realm |

## Rune Discovery Paths

Runes are user-installed extensions (not built-in). They are loaded from three scopes (in precedence order):

1. **Project**: `./.agents/.mvgeos/runes/`
2. **User**: `~/.agents/.mvgeos/runes/`
3. **Agent**: `~/.agents/.mvgeos/{agent_name}/runes/`

## Dependencies

- `importlib.util` — dynamic module loading
- `watchdog` — file system events for hot reload

## Architecture

- Each Rune is a directory containing `manifest.json` + a Python entry file exposing `rune_factory`
- `RuneRunner.load_runes()` calls each factory with a fresh `RuneAPI`
- Sigils are emitted four ways: `emit_async` (fire-all), `emit_chain` (thread value), `emit_first` (first non-None), `emit_block` (handler can veto)
- `RuneWatcher` uses watchdog per rune directory with 0.5s debounce
