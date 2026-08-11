# MvgeOS - Agent Instructions

## Development Rules

MVGEOS IS A CUSTOM IMPLEMENTATION OF THE ARCHITECTURE INTRODUCED BY [Pi](https://github.com/earendil-works/pi) CHECK OUT IT'S SOURCE CODE FOR A REFRESHER ON HOW WE ARE MAKING MVGEOS

## Conversational Style

- Keep answers short and direct
- No emojis in commits, issues, PR comments, or code
- No fluff or cheerful filler text
- Technical prose only

## Code Quality

- Read files in full before wide-ranging changes
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Follow MvgeOS terminology (Mvge, Spell, Realm, Mana, Mana Pool, Tome, Invocation, Summoner, Rune, Seeker, Skill, Channeling, Sigil, Contemplation, Leaf, Fork)
- All code follows the red-green-refactor TDD cycle: write failing test first, then implement

## Commands

- After code changes: `uv run pytest --cov` (full output, no tail)
- Never run `uv run build` or `uv run test` unless requested
- For non-e2e tests, run specific package: `uv run pytest mvgeos-agent/tests_agent/`
- If you create or modify a test file, run it and iterate until it passes
- **Use `;` (semicolon) to chain commands in PowerShell, not `&&`** — PowerShell does not support `&&`

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
- Tests mirror source structure: `<package>/tests/unit/test_<module>.py` and `<package>/tests/integration/test_<module>.py` (e.g., `mvgeos-agent/tests/unit/test_types.py`)
- Unit, harness, and integration test types supported
- **Mock sync methods with `MagicMock()`, async methods with `AsyncMock()`** — mixing causes "coroutine never awaited" warnings
- **Add coverage omit patterns for temp directories** in pyproject.toml to avoid "couldn't parse" warnings
- **90% is practical ceiling** — 100% requires brittle mocks of external dependencies
- **Test file naming**: use flat `*.py` naming (no `test_` prefix) in `tests/unit/` and `tests/integration/`. Configure pytest with `python_files = "*.py"`.
- **Never add `__init__.py` to test directories** — with `--import-mode=importlib` every package's `tests/unit/types.py` collapses to the same dotted path and they silently shadow each other (one file's tests get collected three times, the others never run).
- **E2E tests must use `nvidia/nemotron-3-ultra-550b-a55b:free`** — this is also the default model everywhere it applies (`mvgeos_cli.DEFAULT_MODEL`, `BaseMvge`, `CodingMvge`, CLI config default).
- **Footer/status-line assertions must match a model-ID prefix**, not the full slug — `_fit_footer` truncates to console width.
- **`_build_spells()` interface**: must use `self._runner` (not `self._state.rune_runner`) and return all spell types (rune spells from enabled runes only + builtin spells). Seeker is a rune — it only works through the rune/extension system, not as a built-in category.
- **Test cleanup**: use `_watchers` (plural), not `_watcher` (singular).

## Debugging

- **RuntimeWarning "coroutine never awaited"** = async mock used on sync method
- **CoverageWarning "couldn't parse"** = test creates temp files outside project; add to `[tool.coverage.run] omit`
- **TUI tests fail silently** = check indentation of early returns in rendering loops

## Architecture

MvgeOS is a monorepo with uv workspaces:

| Package | Purpose |
| --- | --- |
| mvgeos-agent | Core loop, Mvge class, MvgeState, MvgeEvent, and MvgeHarness session lifecycle |
| mvgeos-provider | Realm protocol + OpenRouter provider |
| mvgeos-tome | JSONL session persistence with file locking |
| mvgeos-runes | Rune/Extension manifest, loader, sigil hooks |
| mvgeos-cli | CLI entry point (`mvgeos` command) |
| coding-mvge | Coding agent package |

Config follows dotagents protocol at `~/.agents/.mvgeos/`.
Rune/Extension manifest at `~/.agents/.mvgeos/runes/manifest.json`.

Test paths follow pattern: `<package>/tests/unit/test_<module>.py` and `<package>/tests/integration/test_<module>.py` (e.g., `mvgeos-agent/tests/unit/test_types.py`).

**Terminology updates**: `ProviderRegistry` → `RealmRegistry` (Realm = provider abstraction). `Model.provider` field removed — provider derived from model ID prefix (e.g., `nvidia/nemotron` → provider = "nvidia").

## Key Types (MvgeOS Terminology)

| Concept | Type |
| --- | --- |
| Agent | Mvge |
| User | Summoner |
| Tools | Spells |
| Tokens | Mana |
| Context window | Mana Pool |
| Provider | Realm |
| Session | Tome |
| Message | Invocation |
| Streaming | Channeling |
| Extension | Rune |
| Callback | Sigil |
| Reasoning effort | Contemplation |

## Changelog & Releases

- **git-cliff** configured at `cliff.toml` — generates CHANGELOG.md from conventional commits
- **Release workflow**: `.github/workflows/release.yml` — triggers on `v*` tags or manual dispatch
- **Conventional commits required**: `feat(scope):`, `fix(scope):`, `perf(scope):`, `refactor(scope):`, `docs(scope):`, `test(scope):`, `build(scope):`, `ci(scope):`, `chore(scope):`, `revert(scope):`
- **Breaking changes**: include `BREAKING CHANGE:` in commit body
- **Commands**:
  - `uv run git-cliff --config cliff.toml --unreleased` — preview unreleased changes
  - `uv run git-cliff --config cliff.toml --output CHANGELOG.md` — generate full changelog
  - `git tag vX.Y.Z && uv run git-cliff --config cliff.toml --tag vX.Y.Z --output CHANGELOG.md` — release

## Agent skills

### Issue tracker

GitHub Issues via `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single context — root `CONTEXT.md`. See `docs/agents/domain.md`.
