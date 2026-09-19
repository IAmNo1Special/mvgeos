# Handoff: Decoupling MvgeOS Capability Layers into Marketplace Runes

## 1. Goal & Context
The mission is to refactor **MvgeOS** into an unopinionated microkernel by decoupling all capability layers (Layers 1, 2, 3, 4, 5) out of the core monorepo (`mvgeos`) into standalone marketplace runes (`mvgeos-marketplace`).

### Capability Layer Architecture
- **Layer 1**: Repository Steering (`AGENTS.md`, `.agents` protocol) -> `steering-bridge` rune [COMPLETE: Phase 2]
- **Layer 2**: Open Knowledge Format (`.okf/` bundle) -> `okf-bridge` rune [Phase 4: rune exists, core clean, verification only]
- **Layer 3**: Model Context Protocol & PEP 723 -> `mcp-bridge` rune [COMPLETE: Phase 3 verify-only — zero MCP coupling in core; PEP 723 kept in core by decision, see §6]
- **Layer 4**: Agent Skills & Capability Packaging (`agentskills.io`) -> `skills-bridge` rune [COMPLETE: Phase 1]
- **Layer 5**: Architectural Decision Records (MADR) -> `adr-bridge` rune [Phase 4: rune exists, core clean, verification only]
- **Layer 6**: OpenTelemetry Observability -> `opentelemetry-bridge` rune [In Marketplace]

---

## 2. Work Completed (Phase 1)

### Component 1: `skills-bridge` Rune (`mvgeos-marketplace`)
- Location: [runes/skills-bridge/](file:///c:/Users/ivmno/Desktop/mvgeos-marketplace/runes/skills-bridge/)
- Implements: [agentskills.io](https://agentskills.io) client guide and Agent Plugins v1.0.0.
- Modules: `parser.py`, `loader.py`, `prompt.py`, `activation.py`, `dedupe.py`, `rune.py`, `cli.py`.
- Features:
  - Scoped discovery (`PROJECT > USER > AGENT`) with collision detection and shadow logging.
  - Tolerant YAML parser with unquoted colon auto-repair and BOM stripping.
  - Anti-bloat turn updater modifying invocations in-place on multi-turn conversations.
  - `activate_skill` spell execution returning structured `<skill_content>` with bundled resources.
  - Dynamic Typer CLI commands (`list`, `dedupe`, `validate`, `show`) with cp1252-safe ASCII output.
- Status: 46 tests passing, 91% branch coverage, 0 ruff errors, 0 mypy strict errors.
- Commits: `f112553`, `1da4e8c` on `main`.

### Component 2: Microkernel Decoupling (`mvgeos`)
- Pruned 2,500 lines of hardcoded skill coupling from core monorepo:
  - [`mvgeos-runes`](file:///c:/Users/ivmno/Desktop/mvgeos/mvgeos-runes): Removed skill discovery, manifest parsing, YAML repair, and `create_activate_skill_spell`. Retained lightweight storage on `RuneRunner` for snapshot inspection.
  - [`mvgeos-agent`](file:///c:/Users/ivmno/Desktop/mvgeos/mvgeos-agent): Removed hardcoded skill discovery from `RuneLifecycle.load()`; removed `skills_paths` and catalog appending from `MvgeEnvironment.render_prompt`.
  - [`mvgeos-cli`](file:///c:/Users/ivmno/Desktop/mvgeos/mvgeos-cli): Removed static `skill_app` registration; deleted `commands/skill.py`. `mvgeos skill` is now dynamically discovered and mounted via `load_rune_cli_command` when `skills-bridge` is installed.
  - [`mvgeos-gui`](file:///c:/Users/ivmno/Desktop/mvgeos/mvgeos-gui): Replaced `mvgeos_runes.loader` coupling with direct filesystem inspection.
- Status: 2,365 tests passing, 90.24% branch coverage, 0 ruff lint errors, 0 mypy strict errors.
- Commit: `6b69c03` on `main`.

---

## 3. Next Session Focus: APPEND_SYSTEM.md Decision + Phase 4 Verification

### Phase 3 Close-Out (Layer 3: MCP & PEP 723) — COMPLETE (verify-only)
- `mcp-bridge` rune: 39 tests passing, 92% branch coverage (config.py 88% on defensive branches only).
- Core verification: no `mcp` in any `pyproject.toml`, no `mcp` in `uv.lock`, no MCP imports in `mvgeos-*/src`. Only references are string fixtures (`"mcp"` command name in `commands.py` tests) and `external_runes.py` tests behind the justified `ollama_realm` host-skip.
- PEP 723 decision: **keep in core** (`parse_pep723_metadata`, `PEP723ScriptSpell` stay in `mvgeos-agent/function_spell.py`). No code moved.

### Open Question: `APPEND_SYSTEM.md` Chain — DECIDED: keep in core (for now)
- Decision: `resolve_append_system_prompts` + `resolve_system_prompt` stay in `mvgeos-agent/environment.py`.
- Rationale: persona base resolution is kernel load-bearing (deletion test — every embedder reimplements it); `caller_dir` derivation is interpreter-coupled (stack inspection in `Mvge.__init__`); `APPEND_SYSTEM.md` is MvgeOS-internal convention with no external protocol boundary (unlike agentskills.io/MCP/.agents); runes already rewrite `base_prompt` via `BEFORE_MVGE_START`.
- Revisit triggers (not fully closed): if core must stop touching `~/.agents`/project dirs at prompt time, either move the global/project `APPEND_SYSTEM` cascade to `steering-bridge` (cheaper, but muddies its interface) or create a dedicated `persona-bridge` rune (cleaner seam, heavier; needs async persona resolution since `MvgeEnvironment.resolve` is sync and pre-runner).

### Phase 4 (Layers 2 & 5: `okf-bridge`, `adr-bridge`)
- Both runes exist in `mvgeos-marketplace` with full module/test suites; core has no OKF/ADR coupling. Expected to be verification-only (coverage check + zero-coupling grep), same pattern as Phase 3.

---

## 4. Key Decisions & Invariants
- **Rune Naming**: `steering-bridge`, `okf-bridge`, `mcp-bridge`, `skills-bridge`, `adr-bridge`.
- **OKF Path**: Strictly `.okf/` at project root per OKF spec (never `.agents/.okf/`).
- **Standard at Boundary, Persona Inside**: Use protocol names (`~/.agents/extensions/`, `~/.agents/skills/`, wire standard JSON schemas) at external boundaries.
- **Strictly ASCII Console Output**: Avoid Unicode characters (no checkmarks, crosses, arrows) on Windows cp1252. Use `OK:`, `FAIL:`, `ACTIVE:`, `SHADOWED:`.
- **PowerShell Syntax**: Always chain commands with `;` (semicolon), never `&&`.
- **Hermetic Testing**: Never read or write host `~/.agents` in tests; pass `global_dir` or isolate via `tmp_path`.
- **Uncommitted Changes Rule**: Always commit before handoff.

---

## 5. Suggested Skills to Invoke
When picking up the next session, the agent should invoke:
1. **`dot-agents-protocol`**: For exact directory layout rules and `AGENTS.md` specification compliance.
2. **`tdd`**: For red-green-refactor cycle across marketplace rune and core decoupling.
3. **`codebase-design`**: To maintain clean seam separation and deep module design.
4. **`ruff`**: For formatting and lint verification.

---

## 6. Decision Record: PEP 723 Stays in Core (Phase 3)

`parse_pep723_metadata` and `PEP723ScriptSpell` remain in `mvgeos-agent/function_spell.py`. Nothing moved.

1. **Wrong-layer lumping**: MCP (external wire protocol) and PEP 723 (neutral Python standard, stdlib `tomllib`) are different seams sharing a handoff label. The stdlib parser violates no protocol boundary.
2. **No correct home**: `mcp-bridge` is semantically wrong (script execution is not MCP); a new single-purpose rune adds packaging overhead for ~150 lines with no protocol win.
3. **Deletion test fails**: script-spell execution is load-bearing spell machinery — removal pushes reimplementation onto every consumer (coding_mvge, CLI script discovery).
4. **Goal already met**: zero MCP coupling in core, so Phase 3 closed verify-only.
