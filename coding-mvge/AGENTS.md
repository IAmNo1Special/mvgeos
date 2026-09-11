# coding-mvge — Agent Instructions

This package implements the concrete coding agent: `root_mvge = Mvge(name="coding_mvge")` with zero-config auto-discovery of modular built-in coding spells (`bash`, `read`, `edit`, `write`, `grep`, `find`, `list_files`), colocated `SYSTEM.md` / `GUIDELINES.md`, and self-modification authoring contracts.

## Package-Specific Conventions

- All code follows the red-green-refactor TDD cycle: write failing test first, then implement
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Mock sync methods with `MagicMock()`, async methods with `AsyncMock()` — mixing causes "coroutine never awaited" warnings

## Design Philosophy & Standards

- **Strict Standards Adherence**: 100% adherence to open protocols (`.agents`, `agentskills.io`, standard JSON Schema, MCP). Do not build polyfills or fallbacks for proprietary deviations (e.g. inject only `AGENTS.md`, never `CLAUDE.md`).
- **Zero Backward Compatibility Burden**: Keep the architecture greenfield and clean without legacy shims.

## Testing

```bash
# Run this package's tests
uv run python -m pytest coding-mvge/tests/

# Run with coverage
uv run python -m pytest coding-mvge/tests/ --cov
```

Test paths follow pattern: `coding-mvge/tests/unit/<module>.py` and `coding-mvge/tests/integration/<module>.py`

## Structure

```text
coding-mvge/src/coding_mvge/
├── __init__.py         # Re-exports root_mvge
├── mvge.py             # Instantiates root_mvge = Mvge(name="coding_mvge")
├── system_prompt/      # Layer 1 persona instructions and guidelines
│   ├── SYSTEM.md       # Identity, persona, and guidelines
│   └── AGENTS.md       # Authoring guide for system prompt customization
├── spells/             # Modular Python spell files (one file per spell)
│   ├── __init__.py     # Re-exports all spells & defines __all__
│   ├── AGENTS.md       # Spell authoring guide for autonomous self-modification
│   ├── bash.py
│   ├── read.py
│   ├── write.py
│   ├── edit.py
│   ├── find.py
│   ├── list_files.py
│   ├── grep.py
│   └── _process_tree.py
├── skills/             # On-demand agent skills
│   └── AGENTS.md       # Skill authoring guide
└── runes/              # Local agent extensions
    └── AGENTS.md       # Rune authoring guide
```

## Built-in Spells

| Spell | Module | Purpose |
| --- | --- | --- |
| `bash` | `spells/bash.py` | Execute shell commands |
| `read` | `spells/read.py` | Read files |
| `edit` | `spells/edit.py` | Edit files using exact string replacement |
| `write` | `spells/write.py` | Write complete file contents |
| `grep` | `spells/grep.py` | Search file contents with regex |
| `find` | `spells/find.py` | Find files by glob pattern |
| `list_files` | `spells/list_files.py` | List directory contents |

## Dependencies

- `mvgeos-agent` — Mvge, harness, prompt engine, and auto-discovery
- `mvgeos-core` — spell and invocation vocabulary
- `mvgeos-provider` — Realm protocol and providers
- `mvgeos-runes` — Rune extension system

