# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.12.0] - 2026-09-02


### Bug Fixes

- **coding-mvge:** make system prompt fallback tests hermetic (aca960a)


### Chores

- update CHANGELOG.md [skip ci] (2100ccf)

- **release:** v1.12.0 (99ffa82)


### Documentation

- add Design Philosophy & Standards to AGENTS.md files (614e7b3)


### Features

- **agent:** implement Two-Layer Invariant Scaffolding and modular coding agent (685f807)

- **mvgeos-agent:** validate rune spell schema and signature on assembly (#126) (432b45e)


### Refactoring

- **runes:** make RuneContext immutable and thread-safe (#123) (1156c54)

- **cli:** decouple CLI command runners via MvgeAgent protocol and factory (9d93cc6)

- **runes:** remove dead RuneLoader, legacy load_runes, and unneeded sigil helpers (d78de65)

- **tome:** remove dead Index, obsolete INVOCATION, fix ledger typo (e3097ef)

- **provider:** eliminate duplicate model registry loading, dead get_model export, and null abort signal (a8341bd)


## [1.11.0] - 2026-09-01


### Chores

- update CHANGELOG.md [skip ci] (32a1151)

- **release:** v1.11.0 (614e068)


### Features

- **runes:** add override flag to spell and command registrations (233c5e7)


## [1.10.0] - 2026-09-01


### Chores

- update CHANGELOG.md [skip ci] (9c67c19)

- **release:** v1.10.0 (3df06e2)


### Features

- **provider:** implement pluggable RealmFactory protocol in RealmRegistry (#121) (8526f5b)


### Refactoring

- **provider:** extract generic SSE streaming realm base class (a76059d)

- **agent:** isolate external wire tool formats and align internal events on spell terminology (#120) (9b47f12)


## [1.9.0] - 2026-09-01


### Chores

- update CHANGELOG.md [skip ci] (d466c54)

- **release:** v1.9.0 (d6f072d)


### Features

- **provider:** make model registry cache TTL configurable with force-refresh support (#118) (6f0585a)


## [1.8.0] - 2026-09-01


### Chores

- update CHANGELOG.md [skip ci] (4cce39e)

- **release:** v1.8.0 (5d81101)


### Features

- **agent:** integrate tome session version migration into resume lifecycle (#117) (9e1e08f)


## [1.7.0] - 2026-09-01


### Chores

- update CHANGELOG.md [skip ci] (70f34d1)

- **release:** v1.7.0 (76580f3)


### Features

- **agent:** validate model and spell compatibility on session resume (#116) (41b49ef)


## [1.6.0] - 2026-09-01


### Bug Fixes

- **tome:** resolve cross-platform mypy ctypes and wintypes type resolution (70b2643)


### Chores

- update CHANGELOG.md [skip ci] (302e2e6)

- **release:** v1.6.0 (c856e35)


### Features

- **agent:** optimize spell lookup in dispatch loop with indexed map (#111) (b063308)

- **tome:** add session file and line-level integrity verification (81c552d)

- **tome:** implement line streaming iterator and tail reader (#114) (0286f01)

- **tome:** add automated session schema version migration pipeline (closes #115) (c0ade5c)


### Refactoring

- **gui:** consolidate Git workspace inspection behind git_workspace (5452a7b)

- **coding-mvge:** deepen BuiltinSpells and eliminate per-cast reflection (146f04e)

- **agent:** remove unused spell_map property and redundant constants (d05d7d2)


## [1.5.0] - 2026-08-31


### Chores

- update CHANGELOG.md [skip ci] (72f8ba2)

- **release:** v1.5.0 (060b18f)


### Features

- **provider:** unify model catalog into RealmRegistry and remove GUI duplicate (4ae784b)


### Refactoring

- **runes:** collapse SigilRegistry into RuneRunner (4afc0f7)


## [1.4.0] - 2026-08-31


### Chores

- update CHANGELOG.md [skip ci] (408983b)

- **release:** v1.4.0 (9e98ebb)


### Features

- **gui:** align workspace settings persistence with canonical ConfigManager seam (c87dff8)


### Tests

- **integration:** verify full architecture deepening and ratchet coverage (5e7e41a)


## [1.3.0] - 2026-08-31


### Bug Fixes

- **agent:** update fork target_session_file and refine session terminology (6e3ecd7)


### Chores

- update CHANGELOG.md [skip ci] (462b1d6)

- **release:** v1.3.0 (158606c)


### Features

- **agent:** fold TomeLifecycle session transitions into deep MvgeTome (#107) (46283bd)

- **agent:** consolidate prompt discovery and config coercion into deep MvgeEnvironment (8fd312a)


## [1.2.0] - 2026-08-31


### Chores

- update CHANGELOG.md [skip ci] (3ae757b)

- **deps-dev:** update uv-build requirement (10ecb3b)

- **deps-dev:** bump ruff from 0.16.3 to 0.16.4 (d3deb76)

- **release:** v1.2.0 (02e9c9b)


### Documentation

- **architecture:** define Invocation Transcript in the domain glossary (7d12edb)


### Features

- **provider:** unify model catalog and realm resolution in deep RealmRegistry (#106) (dd232f6)


### Refactoring

- **gui:** assemble Invocation bubbles via InvocationTranscript (3c2e0e9)

- eliminate verified redundancies and dead code across monorepo (7f74a84)


## [1.1.0] - 2026-08-23


### Chores

- update CHANGELOG.md [skip ci] (18c4f74)

- **release:** v1.1.0 (a4edd7c)


### Documentation

- **architecture:** amend ADR-0008 to the shipped GUI pipeline (f9ea325)


### Features

- **gui:** wire settings modals into shell and live Mvge status light (421d766)


### Refactoring

- **gui:** remove dead UI pipeline and port composer tests (6717f66)


### Tests

- add model_registry/sandbox coverage, ratchet floor to 84 (aea8444)

- cover conversation_view/home_screen/sessions_panel/input_dock helpers, ratchet floor to 85 (232692f)

- cover message_parts/diff_review/config_manager, ratchet floor to 86 (cf8fdd2)

- add input_dock full render and state extra coverage (97ef41b)

- cover input_dock icon helpers and chat_panel side panels (f8d617f)


## [1.0.1] - 2026-08-23


### Bug Fixes

- **release:** install git-cliff via taiki-e and fix changelog output (3656042)


### Chores

- **release:** v1.0.1 (3532b80)


### Continuous Integration

- **release:** dispatch Release workflow explicitly after bump (ccd059e)


## [1.0.0] - 2026-08-23


### Bug Fixes

- **provider:** handle openrouter rate limits (bde8219)

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

- **provider:** handle empty choices chunks in OpenRouter stream (5c5e68d)

- **gui:** P1 bug fixes for input_dock, state, and agent_service (75bbe03)

- **gui:** correct window geometry fallback to target dimensions (1400x900) (c720d8e)

- **gui:** show milliseconds for sub-second durations in _format_duration (67fe5c6)

- **gui:** wire _active_task in AgentService for proper cancellation (065e226)

- **gui:** address P3 reliability issues from technical audit (da81c37)

- **gui:** resolve pre-existing mypy strict-mode errors (83a86da)

- **agent:** validate switch/fork targets before shutting down source (a2cae53)

- **gui:** persist api key to file when keyring unavailable (28dc47d)

- **release:** skip changelog commit on dry-run dispatches (4da24fa)


### Build System

- raise full-suite coverage floor to the documented 90 percent (59a4f1a)

- adopt src layout with uv_build and overhaul workspace packaging (ca1dd30)

- **root:** measure coverage over first-party source only (558195d)


### Chores

- add pre-commit hooks (bfa2c30)

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

- **deps:** bump typer from 0.27.0 to 0.27.1 (04d878c)

- **deps:** bump filelock from 3.32.0 to 3.32.2 (52c6414)

- **deps-dev:** bump ruff from 0.16.0 to 0.16.2 (f2772f6)

- **deps-dev:** bump pre-commit from 4.6.1 to 4.6.2 (d43c3e4)

- **deps-dev:** bump mypy from 2.3.0 to 2.3.1 (80c7d26)

- **deps-dev:** bump types-pyyaml (0062b29)

- **deps-dev:** bump ruff from 0.16.2 to 0.16.3 (2fe989c)

- **root:** update project docs and pytest config (0abad34)

- **root:** update project status and format step_cards (ee6018a)

- **root:** fix pre-commit hooks to use python -m for Windows compatibility (75bd8a1)

- **release:** v1.0.0 (2998a44)


### Continuous Integration

- add release workflow with git-cliff (3ecf9c4)

- make heal-my-goap optional dependency for CI (66b4845)

- fix heal-my-goap local path source and sync test extra (e302579)

- remove heal-my-goap from deps, tests skip gracefully when not installed (c5c2eda)

- omit heal_my_goap tests from coverage (require external dep) (d82a002)

- bump checkout and setup-uv actions to node24 releases (7921c54)

- run only unit tests in CI and pre-commit (6b6228c)

- gate main pushes with the full test suite (c119bef)

- run hermetic suites per-package with aggregated 90% floor (47a68b3)

- **release:** gate publish jobs on full-suite verification (0cc5a9d)

- **precommit:** drop coverage gate, adopt charter command forms (90d80c9)

- **precommit:** stop uv run from auto-syncing during hooks (90bbaa7)

- **release:** automate version bumps via bump job in ci.yml (7476a38)


### Documentation

- add architecture decision records (ab077de)

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

- update architecture, spec, and tech-debt plans (f89580b)

- add testing standards charter as single test authority (82745d8)

- **testing:** drop resolved workflow-lag note from charter (e54d6c9)

- **testing:** retire e2e tier from project vocabulary (ee833b4)

- **architecture:** remove seeker protocol architecture docs (2f73ca3)

- **architecture:** retire seeker concept and renumber ADRs (c92805b)


### Features

- initial mvgeos monorepo setup (3a9e5a1)

- **agent:** add Mvge core loop with event bus (6417554)

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

- **coding-mvge:** improve bash spell Windows support and cleanup (0f8e709)

- **agent:** add environment-aware prompt rendering (e14aa56)

- **gui:** refactor layout and add Antigravity-matching components (ab870a0)

- **gui:** consolidate clipboard/download utilities with improved security (bce4368)

- **gui:** add keyring dependency for secure API key storage (1780014)

- **gui:** store API key in OS keyring instead of plaintext JSON (a0abe1c)


### Performance

- **agent:** optimize mana pool allocation (d3dbbe6)

- **tome:** optimize ledger index updates and use atomic line appends (5988ae3)

- **cli:** stream tokens instantly without line-buffering delay (ce1e9e1)

- **tome:** implement lazy-loading and bounded LRU indexing for TomeLedger (05cfa99)

- **tome:** migrate synchronous file I/O in Tome ledger and spells to non-blocking async (closes #56) (5be0b53)

- **gui:** cache ModelRegistry instance in model_catalog (39eb05b)


### Refactoring

- **tome:** improve JSONL locking (5a010ba)

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

- **gui:** simplify _track_spell_end status logic to ternary (91f8fb5)

- **agent:** deepen loop core into core_loop + mvge_loop adapter (dae0ba3)

- **agent:** extract ConfigParsing module (25f996b)

- **provider:** extract ModelComposer module (27295aa)

- **agent:** extract TomeLifecycle module (dca56f4)

- **agent:** extract PromptAssembly module (85ed4e0)

- **agent:** extract RuneLifecycle module (79b7f46)

- **agent:** wire BaseMvge.initialize() to the five extracted modules (5c2dfd3)

- **runes:** expose diagnostics retention on RuneRunner (b5ba063)

- **agent:** drop dead fallback in queue_mode getter (38a615c)

- **provider:** own the response and abort vocabulary (978f6bb)

- **runes:** invert sandbox dependency behind a protocol (06a5f2a)

- **gui:** hoist keyring, webview, and subprocess imports to module top (5882b32)

- **coding-mvge:** import AbortError from provider at module top (3632a0a)

- hoist remaining inline imports to top-level (6a34dd8)


### Tests

- **spells:** add unit tests for bash spell (ee2501c)

- **cli:** commit changes (01e8129)

- **all:** restructure tests into tests/unit and tests/integration (f611625)

- **harness:** add integration tests for full harness run with mocked Realm (d4c5520)

- **agent:** enforce no __init__.py in test directories (fddfe3e)

- **gui:** add mode-aware autocomplete tests for skill insertion (4940336)

- **gui:** update config_service tests for keyring-backed storage (3374abd)

- **agent:** strengthen ConfigParsing coverage (3b69fcf)

- **coding-mvge:** remove permanently skipped heal-my-goap demo test (84e2217)

- **coding-mvge:** rename rune integration file to charter naming (d7e9a13)

- **runes:** schedule watcher reloads onto the captured event loop (9bc739a)

- cover previously 0% modules and spell_schema (9cddc0e)


### Fmt

- fix formatting in DESKTOP_APP_PLAN.md (1c68881)


### Prefactor

- **gui:** expand ExecutionStep and ChatMessage schemas for bug fixes (9697a12)


### Sec

- **cli:** enforce restricted file permissions on saved authentication credentials (closes #51) (50906f9)


### Style

- fix ruff formatting in base_mvge.py and main.py (b3fd848)

- **gui:** collapse line continuations and remove redundant lambdas (9508116)

---
*Generated by [git-cliff](https://github.com/orhun/git-cliff)*
