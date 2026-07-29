# MvgeOS TODO — Agent Task Tracker

**Last Updated**: 2026-07-28
**Current Status**: Scaffold complete, core loop implemented,
all quality gates passing
**Location**: `C:\Users\ivmno\Desktop\mvgeos\`

---

## 📋 QUICK STATUS

| Package | Tests | Coverage | Mypy | Ruff |
|---------|-------|----------|------|------|
| mvgeos-agent | 10 passed | 76-99% | ✅ | ✅ |
| mvgeos-provider | 9 passed | 67-100% | ✅ | ✅ |
| mvgeos-tome | 4 passed | 65-100% | ✅ | ✅ |
| mvgeos-spells | 7 passed | 59-100% | ✅ | ✅ |
| mvgeos-runes | 5 passed | 85-100% | ✅ | ✅ |
| mvgeos-cli | 6 passed | 70-100% | ✅ | ✅ |
| **TOTAL** | **41 passed** | **93%** | ✅ | ✅ |

---

## 🎯 NEXT PRIORITIES (In Order)

### 1. Implement zerocontext Rune ⭐ HIGH

**ADR**: `docs/adr/0007-zerocontext-as-rune.md`

Port the zerocontext skill system as an mvgeos-runes extension:

- `mvgeos-runes`: loader, manifest, sigils (prereq) ✅
- `zerocontext` rune package structure
  - [ ] `zerocontext_registry.py` — port with frozen-skill fix (ADR #6)
  - [ ] `zerocontext_toolset.py` — port with `execute_capability` rename (ADR #2)
  - [ ] `zerocontext_tool.py` — fix phantom `execute_capability` reference
  - [ ] `tools.py` — `CapabilityExecutor`, `ActivateSkillTool`, `RunSkillScriptTool`
  - [ ] `batch_executor.py` — `ExecuteCapabilityTool` (renamed),
    input copy fix (ADR #8)
  - [ ] `wrappers.py` — **remove** `BudgetEnforcingSpellWrapper` (ADR #5, #10)
  - [ ] `__init__.py` — exports
- [ ] `ZEROCONTEXT_DISCOVERY_INSTRUCTION` rewrite (ADR #3)
- [ ] `prune_ephemeral_schemas` key fix (ADR #1)
- [ ] `zerocontext` rune manifest + entry point
- [ ] Integration tests: rune load → toolset → harness
- [ ] Wire into MvgeLoop via rune loader (not hardcoded)

### Future Decisions (from ADR)

- [ ] Capability threshold config (`rune_config.capability_threshold`)
- [ ] DCI-style `grep`/`read` tools for skill drilling (ADR #4)
- [ ] Keyword scoring → dual-match embeddings (ADR #3)

---

## 🔧 QUALITY GATES (Always Run Before Committing)

```bash
cd C:\Users\ivmno\Desktop\mvgeos

# Tests (must pass, 90%+ coverage target)
uv run pytest --import-mode=importlib --cov

# Type checking (must pass)
uv run mypy -p mvgeos_agent -p mvgeos_provider -p mvgeos_tome
-p mvgeos_spells -p mvgeos_runes -p mvgeos

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
├── mvgeos-spells/     # 7 spell implementations
├── mvgeos-runes/      # Extension system
├── mvgeos-cli/        # CLI entry point
├── docs/adr/          # ADRs
├── .github/workflows/ci.yml
├── SPEC.md            # Full technical spec
├── HANDOFF.md         # Quick reference
├── ARCHITECTURE.md    # Architecture doc
├── CHANGELOG.md       # Version history
├── README.md          # Project overview
├── AGENTS.md          # Project rules
├── TODO.md            # This file
├── pyproject.toml     # Root config
├── uv.lock            # Lock file
└── LICENSE            # MIT
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
10. **CHANGELOG** — Update under `[Unreleased]` for each change;
    `uv run git-cliff --config cliff.toml --unreleased` to preview

---

## 📚 KEY REFERENCES

- `SPEC.md` — Full technical specification
- `HANDOFF.md` — Quick reference for continuation
- `ARCHITECTURE.md` — Architecture diagrams & data flows
- `AGENTS.md` — Project rules & conventions
- `docs/adr/` — Architecture Decision Records

---

*Update this file after completing each task. Keep it current for the next agent.*

---

## 🔄 ZEROCONTEXT PORT (Rune) — Planned

**ADR**: `docs/adr/0007-zerocontext-as-rune.md`

### Port Tasks (TDD Order)

- [ ] `mvgeos-runes`: loader, manifest, sigils (prereq)
- [ ] `zerocontext` rune package structure
  - [ ] `zerocontext_registry.py` — port with frozen-skill fix (ADR #6)
  - [ ] `zerocontext_toolset.py` — port with `execute_capability` rename (ADR #2)
  - [ ] `zerocontext_tool.py` — fix phantom `execute_capability` reference
  - [ ] `tools.py` — `CapabilityExecutor`, `ActivateSkillTool`, `RunSkillScriptTool`
  - [ ] `batch_executor.py` — `ExecuteCapabilityTool` (renamed),
    input copy fix (ADR #8)
  - [ ] `wrappers.py` — **remove** `BudgetEnforcingSpellWrapper` (ADR #5, #10)
  - [ ] `__init__.py` — exports
- [ ] `ZEROCONTEXT_DISCOVERY_INSTRUCTION` rewrite (ADR #3)
- [ ] `prune_ephemeral_schemas` key fix (ADR #7)
- [ ] `zerocontext` rune manifest + entry point
- [ ] Integration tests: rune load → toolset → harness
- [ ] Wire into MvgeLoop via rune loader (not hardcoded)

### Future Decisions for Port (from ADR)

- [ ] Capability threshold config (`rune_config.capability_threshold`)
- [ ] DCI-style `grep`/`read` tools for skill drilling (ADR #4)
- [ ] Keyword scoring → dual-match embeddings (ADR #3)
