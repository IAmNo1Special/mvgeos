# mvgeos-Provider — Agent Instructions

This package implements the Realm protocol (provider interface) and OpenRouter provider. Realms channel model responses and manage authentication.

## Package-Specific Conventions

- All code follows the red-green-refactor TDD cycle: write failing test first, then implement
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Mock sync methods with `MagicMock()`, async methods with `AsyncMock()` — mixing causes "coroutine never awaited" warnings

## Testing

```bash
# Run this package's tests
uv run pytest mvgeos-provider/tests/

# Run with coverage
uv run pytest mvgeos-provider/tests/ --cov
```

Test paths follow pattern: `mvgeos-provider/tests/unit/<module>.py` and `mvgeos-provider/tests/integration/<module>.py`

## Key Types

| Type | Purpose |
| --- | --- |
| `Realm` | Abstract provider protocol (`stream()`, `complete()`, `close()`) |
| `RealmFactory` | Protocol for pluggable realm constructors (`(api_key, base_url, **kwargs) -> Realm`) |
| `OpenRouterRealm` | OpenRouter SSE channeling implementation |
| `Model` | Model descriptor, canonical in `mvgeos-core` (has `realm`, `max_completion_mana`, `context_window`, `is_free`) |
| `ChannelConfig` | Per-request config, canonical in `mvgeos-core` (temperature, `max_tokens`, `max_output_mana`, contemplation, tools) |
| `RealmResponse` | Stream chunk wrapper, canonical in `mvgeos-core` (`invocation`, `mana_used`, error fields) |
| `RealmRegistry` | Factory for realms; dynamic factory registration; extension-provider configs |
| `ModelRegistry` | Model catalog with disk cache + OpenRouter refresh |

## Field Naming

- `Model.max_completion_mana` — model's maximum output tokens (capability)
- `ChannelConfig.max_output_mana` — per-request output token cap (can be `None`)
- `Model.context_window` — model's context window size (also called Mana Pool)
- `Model.provider` — derived property (from model ID), the organization that provides the model
- `Model.free` / `Model.is_free` — boolean indicating whether the model is free of charge
- `ChannelConfig.contemplation_level` — reasoning effort string (none, minimal, low, medium, high, xhigh, max)
- `ChannelConfig.contemplation_budget` — optional token cap for reasoning

**Do not confuse these**: `max_completion_mana` is the model's capability, `max_output_mana` is a per-request limit.

## Dependencies

- `mvgeos-core` — canonical channel vocabulary (`Model`, `ChannelConfig`, `RealmResponse`, abort primitives)
- `httpx` — HTTP client for OpenRouter API
- `filelock` — cross-process locking

## Architecture

- `Realm.stream(model, invocations, config)` → async generator of `RealmResponse`
- `Realm.complete(model, messages, config)` → single non-channeled completion (e.g. for compaction)
- `OpenRouterRealm` implements OpenRouter SSE streaming with retry/backoff
- `RealmRegistry` creates realms and registers rune-provided providers
- `ModelRegistry` maintains a catalog with disk cache and OpenRouter API refresh
