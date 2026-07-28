# MvgeOS - Agent Instructions

## Development Rules

## Conversational Style

- Keep answers short and direct
- No emojis in commits, issues, PR comments, or code
- No fluff or cheerful filler text
- Technical prose only

## Code Quality

- Read files in full before wide-ranging changes
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Follow MvgeOS terminology (Mvge/Mvges, Spells, Grimoire, Mana, Tome, Rune, Sigil, Relic, Realm, Incantation, Invocation, Manifestation, Contemplation, Condensing)
- All code follows the red-green-refactor TDD cycle: write failing test first, then implement

## Commands

- After code changes: `uv run pytest --cov` (full output, no tail)
- Never run `uv run build` or `uv run test` unless requested
- For non-e2e tests, run specific package: `uv run pytest packages/mvgeos-agent/tests/`
- If you create or modify a test file, run it and iterate until it passes

## Dependency Management

- Use `uv` exclusively — never `pip`
- `uv sync` for installation, `uv add` for adding dependencies
- `uv.lock` is the source of truth
- `pyproject.toml` is the single package configuration source

## Python Conventions

- Google Python Style Guide
- `ruff` for linting and formatting (line-length 88)
- `mypy` strict mode for all packages
- Pre-commit hooks via `.pre-commit-config.yaml` (ruff, mypy, pytest)
- 88-character line length limit

## Testing

- pytest framework with pytest-asyncio
- 90%+ coverage target enforced by CI
- Tests mirror source structure: `tests/test_<module>.py`
- Unit, harness, and integration test types supported

## Architecture

MvgeOS is a monorepo with uv workspaces under `packages/`:

| Package | Purpose |
|---|---|
| mvgeos-agent | Core loop, Mvge class, MvgeState, MvgeEvent |
| mvgeos-provider | Realm protocol + OpenRouter provider |
| mvgeos-tome | JSONL session persistence with file locking |
| mvgeos-spells | Spell implementations (bash, read, edit, write, grep, find, list) |
| mvgeos-runes | Extension manifest, loader, sigil hooks |
| mvgeos-cli | CLI entry point (`mvgeos` command) |

Config follows dotagents protocol at `.agents/mvgeos/`.
Extension manifest at `.agents/mvgeos/extensions/manifest.json`.

## Key Types (MvgeOS Terminology)

| Concept | Type |
|---|---|
| Agent | Mvge |
| Tools | Spells |
| Toolsets | Grimoire |
| Tokens | Mana |
| Context window | Mana Pool |
| Provider | Realm |
| Session | Tome |
| Prompt | Incantation |
| Response | Manifestation |
| Error | Error |
| Extension | Rune |
| Callback | Sigil |
| Credential | Relic |
| API key | Arcane Key |
| OAuth | Covenant |