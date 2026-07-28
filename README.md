# MvgeOS

A Python-based AI coding agent inspired by pi. Mvges invoke spells (tools) across Models through Realms (providers) to perform coding tasks.

## Status

**v0.1.0-dev** — Scaffold complete, core loop implemented, all quality gates passing.

| Component | Status |
|-----------|--------|
| mvgeos-agent (MvgeLoop) | ✅ Implemented + tested |
| mvgeos-tome (TomeLedger) | ✅ Implemented + tested |
| mvgeos-spells (7 spells) | ✅ Implemented + tested (bash) |
| mvgeos-provider (OpenRouterRealm) | ⬜ Stub only |
| mvgeos-runes (extension system) | ⬜ Stub only |
| mvgeos-cli (commands) | ⬜ Empty |

## Structure

MvgeOS is a monorepo with uv workspaces:

| Package | Purpose |
|---|---|
| `mvgeos-agent` | Core Mvge loop, invocations, state, spell execution |
| `mvgeos-provider` | Realm protocol and OpenRouter provider |
| `mvgeos-tome` | JSONL session persistence with file locking and in-memory index |
| `mvgeos-spells` | Spell system: bash, read, edit, write, grep, find, ls |
| `mvgeos-runes` | Extension system: manifest, loader, sigil hooks |
| `mvgeos-cli` | CLI entry point (`mvgeos` command) |

## Quick Start

```bash
uv sync
uv run pytest --import-mode=importlib --cov
uv run mypy
uv run ruff check
uv run ruff format --check
```

## Configuration

MvgeOS adheres to the dotagents protocol. Configuration lives in `.agents/mvgeos/`:

- `.agents/mvgeos/extensions/manifest.json` — Extension registry
- `.agents/mvgeos/auth/` — Relics (API keys, credentials)
- `.agents/mvgeos/sessions/` — Tome (session) JSONL files

## License

MIT