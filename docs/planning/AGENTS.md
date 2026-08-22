# MvgeOS TODO — Agent Task Tracker

**Last Updated**: 2026-08-20
**Current Status**: Core engine, provider, tome persistence, rune loader, CLI, desktop GUI, and coding agent implemented with 1,667 passing tests (2 skipped) and 93%+ coverage.
**Location**: `C:\Users\ivmno\Desktop\mvgeos\`

---

## 📋 QUICK STATUS

| Package | Tests | Coverage | Mypy | Ruff |
|---------|-------|----------|------|------|
| mvgeos-agent | 334 passed (1 skipped) | 96% | ✅ | ✅ |
| mvgeos-provider | 98 passed | 93% | ✅ | ✅ |
| mvgeos-tome | 27 passed | 90% | ✅ | ✅ |
| mvgeos-runes | 191 passed | 97% | ✅ | ✅ |
| mvgeos-cli | 405 passed | 95% | ✅ | ✅ |
| mvgeos-gui | 633 passed | 93% | ✅ | ✅ |
| coding-mvge | 65 passed (1 skipped) | 97% | ✅ | ✅ |
| **TOTAL** | **1,667 passed (2 skipped)** | **93%+** | ✅ | ✅ |

---

## 🎯 NEXT PRIORITIES (In Order)

### 1. Implement Seeker Protocol as Rune ⭐ HIGH ✅ DONE

**Docs**: `docs/architecture/ARCHITECTURE_TOOL_SEARCH.md`, `docs/architecture/ARCHITECTURE_SKILL_SEARCH.md`, `docs/architecture/ARCHITECTURE_MCP_SEARCH.md`

Implemented as external rune at `~/.agents/.mvgeos/runes/00-seeker/`:
- `mvgeos_runes_seeker` package with `ToolSearchSpell`, `SkillSearchSpell`, `SkillExecuteSpell`, `MCPSearchSpell`
- Manifest with `before_mvge_start`/`session_shutdown` hooks, `ripgrep` system dep
- 4 spells registered: `tool_search`, `skill_search`, `skill_execute`, `mcp_search`
- Auto-loaded via rune loader (project/user/agent scope precedence)

---

## 🔧 QUALITY GATES (Always Run Before Committing)

```bash
cd C:\Users\ivmno\Desktop\mvgeos

# Tests (must pass, 90%+ coverage floor) — canonical invocations: root TESTING.md
uv run python -m pytest --cov

# Type checking (must pass)
uv run mypy

# Linting (must pass)
uv run ruff check

# Formatting (must pass)
uv run ruff format --check

# Or auto-fix + format
uv run ruff check --fix
uv run ruff format
```

---

## 📁 PROJECT STRUCTURE

```text
mvgeos/
├── mvgeos-agent/      # Core loop, state, types
├── mvgeos-provider/   # Realm protocol + OpenRouter
├── mvgeos-tome/       # JSONL session persistence
├── mvgeos-runes/      # Extension system
├── mvgeos-cli/        # CLI entry point
├── mvgeos-gui/        # Desktop GUI application (NiceGUI)
├── coding-mvge/      # Coding agent package
├── docs/adr/          # ADRs
├── .github/workflows/ci.yml
├── CHANGELOG.md       # Version history
├── README.md          # Project overview
├── AGENTS.md          # Project rules
├── pyproject.toml     # Root config
├── uv.lock            # Lock file
└── LICENSE            # MIT
```

---

## 🧪 TDD WORKFLOW (Required)

1. **RED** — Write failing test in `<package>/tests/unit/<module>.py` or `<package>/tests/integration/<module>.py`
2. **GREEN** — Implement minimal code in `<package>/<package_name>/<module>.py`
3. **REFACTOR** — Clean up, ensure types pass
4. **VERIFY** — Run all quality gates above

**Test Naming**: `test_<function>_<scenario>`

- `test_loop_single_turn_no_spells`
- `test_loop_with_spell_cast`
- `test_cast_bash_success`
- `test_cast_bash_timeout`

---

## 📝 MvgeOS TERMINOLOGY (Use Consistently)

| Standard | MvgeOS |
|----------|--------|
| Agent | Mvge |
| User | Summoner |
| Tool | Spell |
| Token | Mana |
| Context Window | Mana Pool |
| Provider | Realm |
| Session | Tome |
| Message | Invocation |
| Streaming | Channeling |
| Extension | Rune |
| Callback | Sigil |
| Reasoning Effort | Contemplation |

---

## 📌 IMPORTANT NOTES FOR FUTURE AGENTS

1. **uv only** — Never use pip. `uv sync`, `uv add`, `uv run`
2. **Python 3.14+** — Use `StrEnum`, modern typing
3. **Top-level imports only** — No inline imports
4. **pathlib.Path** — Never raw string concatenation for paths
5. **Google docstrings** — Follow existing style
6. **MvgeOS terminology** — Use terms above consistently
7. **No backward compat** — Unless explicitly asked
8. **Pre-commit** — Runs ruff + mypy + pytest on commit
9. **ADRs** — Add for significant architectural decisions
10. **CHANGELOG** — Update under `[Unreleased]` for each change;
    `uv run git-cliff --config cliff.toml --unreleased` to preview

---

## 📚 KEY REFERENCES

- `docs/architecture/SPEC.md` — Full technical specification
- `docs/architecture/ARCHITECTURE.md` — Architecture diagrams & data flows
- `AGENTS.md` — Project rules & conventions
- `docs/adr/` — Architecture Decision Records

---

*Update this file after completing each task. Keep it current for the next agent.*
