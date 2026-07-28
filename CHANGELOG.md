# Changelog

## [Unreleased]

### Added

- MvgeLoop (mvgeos-agent) — Core agent loop with streaming response handling, spell execution, event emission, mana budget enforcement
- TomeLedger (mvgeos-tome) — JSONL session persistence with file locking, Index, JsonlStore
- 7 Spell implementations (mvgeos-spells) — bash, read, write, edit, find, list, grep
- uv workspace with 6 packages under `src/mvgeos/`
- CI workflow with pytest --import-mode=importlib, mypy, ruff
- 6 ADRs documenting architecture decisions

### Changed
- Fixed UTF-16 encoding issues in scaffold files
- Updated ruff `extend` paths to `../../../pyproject.toml`
- Fixed mypy duplicate module conflicts by removing `tests/__init__.py` files
- Fixed hatchling build for root package with `src/mvgeos/` package

### Fixed

- ChannelConfig initialization with proper Model construction
- Import sorting and line-length issues across all packages
- AsyncIterator import from collections.abc (Python 3.14+)

## [0.1.0-dev] - 2026-07-28

### Added

- Initial scaffold of MvgeOS monorepo
- mvgeos-agent package: core Mvge loop and invocation types
- mvgeos-provider package: Realm protocol and OpenRouter provider
- mvgeos-tome package: JSONL session persistence with file locking
- mvgeos-spells package: bash, read, edit, write, grep, find, ls spells
- mvgeos-runes package: extension manifest, loader, sigil hooks
- mvgeos-cli package: CLI entry point
- dotagents protocol compliance at `.agents/mvgeos/`
- mvge terminology throughout (Mvge, Mvges, Spells, Grimoire, Mana, Tome, Rune, Sigil, Relic, Realm, Incantation, Invocation, Manifestation, SpellResult)

### Changed

- MvgeLoop (mvgeos-agent): Implemented full agent loop with streaming response handling, spell/tool call execution, event emission (AGENT_START, MESSAGE_UPDATE, SPELL_CASTING_START/END, AGENT_END), mana budget enforcement, and error handling
- MvgeLoop tests: 5 tests covering single turn, spell casting, mana exhaustion, error handling, empty invocations
- TomeLedger (mvgeos-tome): Verified session persistence with FileLock, JsonlStore, Index
- Spell implementations (mvgeos-spells): All 7 spells functional (bash, read, write, edit, find, list, grep)