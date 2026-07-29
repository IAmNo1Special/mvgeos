# MvgeOS TODO — Agent Task Tracker

**Last Updated**: 2026-07-28
**Current Status**: Scaffold complete, core loop implemented, all quality gates passing
**Location**: `C:\Users\ivmno\Desktop\mvgeos\`

---

## 📋 QUICK STATUS

| Package | Tests | Coverage | Mypy | Ruff |
|---------|-------|----------|------|------|
| mvgeos-agent | 10 passed | 76-99% | ✅ | ✅ |
| mvgeos-provider | 4 passed | 67-100% | ✅ | ✅ |
| mvgeos-tome | 4 passed | 65-100% | ✅ | ✅ |
| mvgeos-spells | 3 passed | 59-100% | ✅ | ✅ |
| mvgeos-runes | 0 tests | N/A | ✅ | ✅ |
| mvgeos-cli | 0 tests | N/A | ✅ | ✅ |
| **TOTAL** | **21 passed** | **88%** | ✅ | ✅ |

---

## 🎯 NEXT PRIORITIES (In Order)

### 1. Complete mvgeos-spells ⭐ HIGH
**File**: `src/mvgeos/mvgeos-spells/src/mvgeos_spells/__init__.py`
- [ ] Add exports for all 7 spells
- [ ] Add `__all__` list

**Files**: `src/mvgeos/mvgeos-spells/tests/`
- [ ] `test_read.py` — read existing, non-existent, encoding
- [ ] `test_write.py` — write new, overwrite, create dirs
- [ ] `test_edit.py` — exact match, no match, multiple occurrences
- [ ] `test_find.py` — pattern match, no match, recursive
- [ ] `test_list.py` — non-recursive, recursive, non-existent
- [ ] `test_grep.py` — content match, line numbers, output modes

### 2. Implement OpenRouterRealm ⭐ HIGH
**File**: `src/mvgeos/mvgeos-provider/src/mvgeos_provider/openrouter.py`
- [ ] Real HTTP streaming to `https://openrouter.ai/api/v1/chat/completions`
- [ ] Handle tool calls (function calling), content streaming, stop reasons
- [ ] Map MvgeInvocation history to OpenAI-compatible messages
- [ ] Proper error handling: retries, timeouts, rate limits
- [ ] Mana tracking from response headers
- [ ] Async iteration yielding `RealmResponse` objects

**Tests**: `src/mvgeos/mvgeos-provider/tests/test_openrouter.py`
- [ ] Mock HTTP responses, test tool call parsing
- [ ] Test content streaming
- [ ] Test error recovery

### 3. Implement mvgeos-runes ⭐ HIGH
**Files**: `src/mvgeos/mvgeos-runes/src/mvgeos_runes/`
- [ ] `loader.py` — `RuneLoader.discover_runes()`, `load_rune()`, validate entry points
- [ ] `manifest.py` — `load_manifest(path)`, parse/validate JSON schema
- [ ] `sigils.py` — `SigilRegistry.register()`, `emit()`, async/sync handlers

**Tests**: `src/mvgeos/mvgeos-runes/tests/`
- [ ] Discovery, loading, hook registration/emission, error cases

### 4. Implement mvgeos-cli ⭐ HIGH
**Files**: `src/mvgeos/mvgeos-cli/src/mvgeos/commands/`
- [ ] `prompt.py` — `prompt <incantation>`: create MvgeState, load spells, create Realm, run MvgeLoop
- [ ] `tome.py` — `tome list|show|export`: session management
- [ ] `config.py` — `config show|set`: configuration at `.agents/mvgeos/config.json`

**Main**: `src/mvgeos/mvgeos-cli/src/mvgeos/main.py`
- [ ] Typer app with subcommands

---

## 🔧 QUALITY GATES (Always Run Before Committing)

```bash
cd C:\Users\ivmno\Desktop\mvgeos

# Tests (must pass, 90%+ coverage target)
uv run pytest --import-mode=importlib --cov

# Type checking (must pass)
uv run mypy -p mvgeos_agent -p mvgeos_provider -p mvgeos_tome -p mvgeos_spells -p mvgeos_runes -p mvgeos

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

```
mvgeos/
├── src/mvgeos/
│   ├── mvgeos-agent/      # Core loop, state, types
│   ├── mvgeos-provider/   # Realm protocol + OpenRouter
│   ├── mvgeos-tome/       # JSONL session persistence
│   ├── mvgeos-spells/     # 7 spell implementations
│   ├── mvgeos-runes/      # Extension system
│   ├── mvgeos-cli/        # CLI entry point
│   └── __init__.py
├── adr/                    # 6 ADRs
├── .github/workflows/ci.yml
├── SPEC.md                 # Full technical spec
├── HANDOFF.md              # Quick reference
├── ARCHITECTURE.md         # Architecture doc
├── CHANGELOG.md            # Version history
├── README.md               # Project overview
├── AGENTS.md               # Project rules
├── TODO.md                 # This file
├── pyproject.toml          # Root config
├── uv.lock                 # Lock file
└── LICENSE                 # MIT
```

---

## 🧪 TDD WORKFLOW (Required)

1. **RED** — Write failing test in `tests/test_<module>.py`
2. **GREEN** — Implement minimal code in `src/mvgeos_<pkg>/<module>.py`
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
| Tool | Spell |
| Toolset | Grimoire |
| Token | Mana |
| Context Window | Mana Pool |
| Provider | Realm |
| Session | Tome |
| Prompt | Incantation |
| Response | Manifestation |
| Extension | Rune |
| Callback | Sigil |
| Credential | Relic |
| API Key | Arcane Key |
| OAuth | Covenant |

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
10. **CHANGELOG** — Update under `[Unreleased]` for each change; `uv run git-cliff --config cliff.toml --unreleased` to preview

---

## 📚 KEY REFERENCES

- `SPEC.md` — Full technical specification
- `HANDOFF.md` — Quick reference for continuation
- `ARCHITECTURE.md` — Architecture diagrams & data flows
- `AGENTS.md` — Project rules & conventions
- `adr/` — Architecture Decision Records

---

*Update this file after completing each task. Keep it current for the next agent.*

---

## 🔄 ZEROCONTEXT PORT (Rune) — Planned

**ADR**: `adr/0003-zerocontext-as-rune.md`

### Port Tasks (TDD Order)
- [ ] `mvgeos-runes`: loader, manifest, sigils (prereq)
- [ ] `zerocontext` rune package structure
  - [ ] `zerocontext_registry.py` — port with frozen-skill fix (ADR #6)
  - [ ] `zerocontext_toolset.py` — port with `execute_capability` rename (ADR #2)
  - [ ] `zerocontext_tool.py` — fix phantom `execute_capability` reference
  - [ ] `tools.py` — `CapabilityExecutor`, `ActivateSkillTool`, `RunSkillScriptTool`
  - [ ] `batch_executor.py` — `ExecuteCapabilityTool` (renamed), input copy fix (ADR #8)
  - [ ] `wrappers.py` — **remove** `BudgetEnforcingSpellWrapper` (ADR #5, #10)
  - [ ] `__init__.py` — exports
- [ ] `ZEROCONTEXT_DISCOVERY_INSTRUCTION` rewrite (ADR #3)
- [ ] `prune_ephemeral_schemas` key fix (ADR #1)
- [ ] `zerocontext` rune manifest + entry point
- [ ] Integration tests: rune load → toolset → harness
- [ ] Wire into MvgeLoop via rune loader (not hardcoded)

### Open Decisions (from ADR)
- [ ] Capability threshold config (`rune_config.capability_threshold`)
- [ ] DCI-style `grep`/`read` tools for skill drilling (ADR #4)
- [ ] Keyword scoring → dual-match embeddings (ADR #3)