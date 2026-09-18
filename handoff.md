# Handoff: Decoupling MvgeOS Capability Layers into Marketplace Runes

## 1. Goal & Context
The mission is to refactor **MvgeOS** into an unopinionated microkernel by decoupling all capability layers (Layers 1, 2, 3, 4, 5) out of the core monorepo (`mvgeos`) into standalone marketplace runes (`mvgeos-marketplace`).

### Capability Layer Architecture
- **Layer 1**: Repository Steering (`AGENTS.md`, `.agents` protocol) -> `steering-bridge` rune [NEXT: Phase 2]
- **Layer 2**: Open Knowledge Format (`.okf/` bundle) -> `okf-bridge` rune [Phase 4]
- **Layer 3**: Model Context Protocol & PEP 723 -> `mcp-bridge` rune [Phase 3]
- **Layer 4**: Agent Skills & Capability Packaging (`agentskills.io`) -> `skills-bridge` rune [COMPLETE: Phase 1]
- **Layer 5**: Architectural Decision Records (MADR) -> `adr-bridge` rune [Phase 4]
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

## 3. Next Session Focus: Phase 2 (Decouple Layer 1: `steering-bridge` Rune)

### Requirements for Phase 2:
1. **Create `runes/steering-bridge` in `mvgeos-marketplace`**:
   - Strictly follow the [.agents protocol](https://dotagentsprotocol.com) and `dot-agents-protocol` skill.
   - Global steering: discover `~/.agents/AGENTS.md`.
   - Workspace steering: discover `<project_root>/AGENTS.md` and fallback `<project_root>/.agents/AGENTS.md`.
   - Precedence: project steering overrides/supplements global steering.
   - Inject `<project_context>` containing `<global_instructions path="...">` and `<project_instructions path="...">`.
   - Progressive disclosure: scan first-level subdirectories for localized `AGENTS.md` and declare pointers.
   - Hook into `BEFORE_MVGE_START` sigil to inject instructions into `BeforeMvgeStartData.base_prompt`.
   - Hook into `SESSION_START` for path resolution.
2. **Decouple Steering from `mvgeos` Core**:
   - Remove hardcoded `resolve_workspace_agents_file`, `resolve_global_agents_file`, and `<project_context>` formatting from `mvgeos-agent/src/mvgeos_agent/environment.py`.
   - Core prompt rendering remains focused strictly on Layer 2 invariant scaffolding: base system prompt, active spells listing, environment info (OS, shell, date/time UTC), and PowerShell rules.
   - Ensure `MvgeEnvironment` accepts dynamic steering sections contributed by runes via `BEFORE_MVGE_START`.
3. **Verification**:
   - Monorepo suite: `uv run python -m pytest --cov` (>= 90.0% branch coverage).
   - Ruff lint & format: `uv run ruff check` ; `uv run ruff format --check`.
   - Mypy: `uv run mypy`.

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
