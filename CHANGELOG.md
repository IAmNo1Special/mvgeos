# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


### Bug Fixes

- **root:** fix MD022/MD036/MD047 lint violations in handoff generator (3debd6f)

- **ci:** align pre-commit hooks with CI workflow (4e5bad4)

- **ci:** release workflow only triggers on tags not every push (d790374)

- **ci:** update handoff, distill, git-workflow skills - remove project-specific code (d66f49a)

- **ci:** fix handoff script quality gates and MD013 line length violations (ef7cdd5)

- resolve ruff lint issues and add heal-my-goap availability checks (faa241d)

- add pydantic to agent deps and fix formatting (3fbf33f)

- **agent:** fall back to default when config-dir system prompt is unreadable (428d707)

- **root:** stop test modules shadowing each other across packages (1c5cafb)

- **tome,agent:** repair entry lookup and advance the Leaf on every append (5c15906)

- **agent,provider:** honour custom guidelines and surface Contemplation (f5cba30)

- **prompt:** fix OSError fallback test to use mock (05e3b64)

- **test:** update default name assertion to default-mvge (18d7588)

- **cli:** wire mvgeos info command into the CLI app (0b77674)

- **cli:** unify tome dir to ~/.agents/.mvgeos/tomes and drop dead mvge_config (6bb98c3)

- **provider:** pass absolute request URLs and authorization headers (3ffc4ff)

- **cli:** reset narration buffers on turn start to isolate contemplation styling across multi-turn runs (075802e)

- **gitignore:** added .opencode/ dir (8bd2256)

- **runes:** resolve entrypoint dependencies for default system runes (2bafd15)

- **cli:** handle Windows console CP1252 encoding and sanitize Rich unicode output (f39d860)

- **agent:** shorten long log/raise lines to satisfy ruff E501 (91d7df4)

- **cli:** guard NoConsoleScreenBufferError import for non-Win32 platforms (b18c91a)

- **test:** supply OPENROUTER_API_KEY env in agent name validation tests (9c1221f)

- **agent,cli:** allow unknown agent in BaseMvge and fix mypy unused ignore (94e5a6a)

- **agent:** recognize coding-mvge and test-agent as known agent names (3be6ef7)

- **runes:** make set_active_spells additive and per-rune (d7d35b6)

- **cli:** add ellipsis truncation for table path columns in info and tome (e09d2e9)

- resolve issues #42, #43, #44, #45, #46 (runes, cli, tui, provider, tome) (24aa791)

- **constants:** harmonize system-wide default model to nvidia/nemotron-3-ultra-550b-a55b:free (closes #49) (2142a8b)

- **tome:** record parent_id on tome entries to restore conversation tree branching (closes #47) (24b15c3)

- **gui:** update branding to MvgeOS, apply Windows dark titlebar, and fix bottom layout padding (0f9fc3e)

- **gui:** enforce symmetrical horizontal padding on center viewport and dock (1b37e55)

- **gui:** resolve OpenRouter API key from auth file, env, and cli args (4aabf14)

- **gui:** separate agent contemplation thoughts into distinct collapsible cards (a561ee7)

- **gui:** isolate message updates per turn and prevent duplicate event listeners (4e0e427)

- **provider:** include contemplation in final stream response for persistence (cd6ea3e)

- **gui:** resolve platform-specific mypy and test failures for Windows titlebar (5b02045)

- **cli:** refine stream filter to stop suppressing legitimate markdown headings (9ce388f)

- **cli:** honor every channel tag on a line in stream filter (1312c0f)

- **gui:** resolve ruff lint and format quality gate failures (2b52f06)

- **gui:** report working-tree diff and narrow exception handling in git_diff (bbf4f59)

- **gui:** resolve_git_branch returns None for non-git parent dirs (f897cd9)

- **gui:** render each reasoning segment in its own Thought card (f58c179)

- **gui:** restore cleaned text return in _extract_text_and_contemplation (9da4890)

- **runes:** skip dot-prefixed skill dirs and strip UTF-8 BOM in manifest parsing (e6e13e3)

- **tome:** use tmp_path in locking tests to avoid creating stray dir/ (529e8f5)


### Chores

- generate CHANGELOG.md for v0.1.0-dev (593e1f0)

- **agent:** update package configuration (3a7c211)

- **root:** update repository URL (db73648)

- **root:** fix test collection for monorepo (ea0823b)

- **ci:** trigger workflow run (88858df)

- **ci:** track uv.lock for CI caching (212822a)

- **ci:** fix test package installation and mypy target (dc56cc9)

- **root:** remove invalid hatch build config (2e60ad1)

- **ci:** fix workspace package installation with --all-packages (4188d35)

- **provider:** track uv.lock for CI caching (cb8e499)

- commit changes (57812bc)

- **docs:** commit changes (87fa48a)

- **root:** update root workspace config and lockfile (c68494d)

- **root:** update AGENTS.md, README.md, and add goap actions (cd78a2d)

- **root:** ignore goap_actions.json (1d2ebce)

- **root:** remove obsolete documentation files (db1260e)

- **config:** ignore agent session files (1976ad6)

- ignore AI-generated and coverage artifacts (d045732)

- **root:** normalize line endings to LF (dfef00f)

- remove one-shot rebuild plan documentation (d8a1487)


### Continuous Integration

- make heal-my-goap optional dependency for CI (66b4845)

- fix heal-my-goap local path source and sync test extra (e302579)

- remove heal-my-goap from deps, tests skip gracefully when not installed (c5c2eda)

- omit heal_my_goap tests from coverage (require external dep) (d82a002)

- bump checkout and setup-uv actions to node24 releases (7921c54)


### Documentation

- **root:** update documentation and configuration (a891aae)

- commit changes (c636871)

- commit changes (8755e88)

- **root:** update ADRs for new MvgeOS architecture (a824c74)

- **root:** add architecture, planning, and tech-debt documentation (f7157df)

- **root:** remove mvgeos-spells from package table (ac80d25)

- align terminology with MvgeOS and add agent docs (6fd9d35)

- **root:** document loop architecture, retry, compaction, and known gaps (66c3ac8)

- **root:** add mvgeos-harness to root documentation (f183a41)

- **agent:** update architecture with harness lifecycle (116805f)

- **coding-mvge:** update architecture for harness delegation (8e3f14d)

- **architecture:** add harness package and update invocation flow (60ebbb2)

- **all:** synchronize project documentation with source code implementation (dbadfa7)

- **cli:** add help description to tome subcommand application (c84d098)

- **tech-debt:** mark duplicate _build_spells entry resolved and drop stale line refs (d573406)

- **cli:** document non-interactive setup install (ac6d681)

- **architecture:** update terminology and supersede deprecated mvgeos-spells references (ea69a68)

- **root:** synchronize markdown documentation across monorepo (4a210bd)

- **adr:** record ADR 0009 for NiceGUI desktop application architecture (e7a2819)


### Features

- **coding-mvge:** add coding agent package with spells and tests (e5a8cc7)

- **agent,runes,coding-mvge:** relocate spell types and load runes from multi-level paths (875ad91)

- **cli:** add setup command for rune dependencies (1b1ee1d)

- **agent,runes,coding-mvge,cli:** rune prompt injection, config module, and gate alignment (621f036)

- **provider:** add two-layer retry policy for Realm calls (78e476a)

- **provider:** add Realm.complete() for non-channelled requests (a177147)

- **agent,tome:** compact the Mana Pool before it overflows (a285b80)

- **harness:** Implement MvgeHarness for Pi parity (327085e)

- **agent:** consolidate canonical name and rune-path resolution (56785c0)

- **runes:** provenance, dedup, and diagnostics for rune loading (b2affd4)

- **config:** ConfigManager with layered merge and agent-scope config (9d025dc)

- **prompts:** implement prompt resolution as a resource with source introspection (adb1aae)

- **runes:** core skills discovery + catalog (e16e750)

- **agent:** BaseMvge/CodingMvge/CLI construction consumes resolved config + resources (7d93c71)

- **agent:** runtime snapshot seam for resolved-state bundle (a1d9517)

- **cli:** add mvgeos build command for runtime manifest serialisation (8d2b027)

- **cli:** mvgeos info command renders runtime snapshot as rich tables (8e90506)

- **runes:** add extension error isolation, history capping, connection pooling, and loader validation (bf789ea)

- **cli:** add TUI stream rendering, queue modes, and slash commands (9b9f073)

- **cli:** add free model filtering, live rate limit countdown, and update default model to openrouter/free (c79394a)

- **cli:** rebuild one-shot mode reusing CodingMvge agent factory and print mode (d71936f)

- **cli:** add interactive setup prompt for API key initialization (#28) (1d17e2e)

- **runes:** generalize rune handling via active-spells set (#30) (0d5cb0b)

- **cli:** validate --agent-name option and environment resolution (0acb24b)

- **cli:** add --format {json,summary} and --pretty to build (32d0786)

- **cli:** surface rune load failures at startup (9188bff)

- **cli:** resolve tome IDs for session resume (4e9db31)

- **cli:** print group help for config/tome and default setup to check (e4c3b38)

- **cli:** add --format option and ISO 8601 timestamps to tome show (d9b5478)

- **cli:** standardize error formatting via format_error helper (#39) (87c4c78)

- **seeker:** widen active spell set on tool search discovery (#41) (8ae8be5)

- **seeker:** widen active spell set on tool search discovery (#41) (075a2a0)

- **gui:** scaffold mvgeos-gui workspace package, desktop runtime, and 3-column obsidian shell (eb4c4dd)

- **gui:** integrate TomeLedger session browser, git branch tags, and top navigation header (08291d6)

- **gui:** implement live agent channeling, Mana tracking, and collapsible execution step cards (a6d029a)

- **agent:** add QueueMode enum and granular queue draining (d8b837a)

- **runes:** add pre-flight python dependency validation for rune loading (closes #55) (0636b6a)

- **agent:** implement end-to-end AbortSignal cancellation architecture (87dfea4)

- **gui:** implement input dock with @-mention and /-slash autocomplete and attachments (981bc06)

- **gui:** track background tasks from MvgeEvents in inspector state (#70) (8b1e514)

- **gui:** wire agent service to populate active_skills from events (#71) (d3d3f92)

- **gui:** render reactive data in inspector Uploads and Background Tasks sections (1b4528d)

- **gui:** add inspector accordion and multi-item reactive integration tests (ef9fc5b)

- **gui:** implement Files Changed tracker and Diff Review modal (812ad55)

- **gui:** implement in-stream Artifact cards and sliding markdown preview drawer (fdc1932)

- **gui:** implement Application and Workspace Settings modals (73fecd3)

- **gui:** add chip-based input for autocomplete selections (8a822e3)

- **gui:** enrich step cards with Spell params and result rendering (e9cd29e)


### Performance

- **tome:** optimize ledger index updates and use atomic line appends (5988ae3)

- **cli:** stream tokens instantly without line-buffering delay (ce1e9e1)

- **tome:** implement lazy-loading and bounded LRU indexing for TomeLedger (05cfa99)

- **tome:** migrate synchronous file I/O in Tome ledger and spells to non-blocking async (closes #56) (5be0b53)


### Refactoring

- **cli:** restructure to flat layout (d3484b0)

- **provider:** update provider implementation (40b4efe)

- **runes:** restructure to flat layout (2618a96)

- **spells:** restructure to flat layout (aa8b75c)

- **tome:** restructure to flat layout (6a95f5e)

- **agent:** restructure agent package with new MvgeOS architecture (2541658)

- **cli:** restructure CLI package with new command structure (05a2ff4)

- **provider:** add model registry and OpenRouter improvements (29cab8b)

- **runes:** add rune API, runner, and watcher (fa2765b)

- **tome:** update ledger for unified session system (bf7b052)

- **spells:** remove deprecated mvgeos-spells package (057373a)

- **agent,cli:** load global runes by default and use ~/.agents/.mvgeos/tomes (d3de0d7)

- **provider:** rename ProviderRegistry to RealmRegistry, derive provider from model id (897615f)

- **tome:** rename session terms to tome (3dda4c8)

- **agent,cli,coding-mvge:** deepen the loop, invert the turn cycle, drop Mana Budget **BREAKING CHANGE** (a994eb7)

- **prompt:** consolidate to one path, one rendering, seeded defaults (c9e8327)

- **prompt:** consolidate to one path, one rendering, seeded defaults (3f83660)

- **harness:** Fix circular import and LSP issues (7374e88)

- **agent:** consolidate session lifecycle harness into mvgeos_agent.harness (ee63a08)

- **agent:** consolidate session lifecycle into MvgeHarness (2bfeae7)

- **agent:** extract SpellDispatcher module for parallel tool execution (b0fd123)

- **agent:** consolidate agent environment into deep MvgeEnvironment module (e15a39b)

- **agent:** remove duplicate realm initialization in BaseMvge (c30d06b)

- **coding-mvge:** consolidate builtin spell map constant (81eee0e)

- **cli:** use canonical BUILTIN_SPELL_MAP from coding-mvge (255da6b)

- **runes:** introduce strongly typed dataclass schemas for Sigil hook payloads (1d073ef)

- **agent:** rename session* to tome* **BREAKING CHANGE** (a9d5cbc)


### Tests

- **cli:** commit changes (01e8129)

- **all:** restructure tests into tests/unit and tests/integration (f611625)

- **harness:** add integration tests for full harness run with mocked Realm (d4c5520)

- **agent:** enforce no __init__.py in test directories (fddfe3e)

- **gui:** add mode-aware autocomplete tests for skill insertion (4940336)


### Fmt

- fix formatting in DESKTOP_APP_PLAN.md (1c68881)


### Prefactor

- **gui:** expand ExecutionStep and ChatMessage schemas for bug fixes (9697a12)


### Sec

- **cli:** enforce restricted file permissions on saved authentication credentials (closes #51) (50906f9)


### Style

- fix ruff formatting in base_mvge.py and main.py (b3fd848)

- **gui:** collapse line continuations and remove redundant lambdas (9508116)


## [0.1.0-dev] - 2026-07-28


### Bug Fixes

- **provider:** handle openrouter rate limits (bde8219)


### Chores

- add pre-commit hooks (bfa2c30)


### Continuous Integration

- add release workflow with git-cliff (3ecf9c4)


### Documentation

- add architecture decision records (ab077de)


### Features

- initial mvgeos monorepo setup (3a9e5a1)

- **agent:** add Mvge core loop with event bus (6417554)


### Performance

- **agent:** optimize mana pool allocation (d3dbbe6)


### Refactoring

- **tome:** improve JSONL locking (5a010ba)


### Tests

- **spells:** add unit tests for bash spell (ee2501c)

---
*Generated by [git-cliff](https://github.com/orhun/git-cliff)*
