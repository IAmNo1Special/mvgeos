# P1 Plan: Rebuild One-Shot Mode on `CodingMvge`

## Goal
Replace the hand-rolled one-shot path in `mvgeos-cli/mvgeos_cli/main.py:_run_agent()` with a path that reuses the shared agent factory (`_create_agent` from `commands/repl.py`) + a print-mode runner, fixing 5 bugs in one change without regressing existing tests.

---

## Current State (Bugs)
| Bug | Location | Symptom |
|-----|----------|---------|
| 1. No tools | main.py:202-214 | `spells = []` → model hallucinates `{"name":"list",...}` as plain text |
| 2. No output | main.py:286-293 | Only `Done. Stop reason: stop` printed; answer lost |
| 3. Raw tracebacks | main.py:286-293 | `AuthenticationError`/`RateLimitError` and init errors uncaught |
| 4. Providers dropped | main.py:150 & 199 | `provider_registry` recreated twice; rune providers lost |
| 5. Positional `<prompt>` | main.py:325-383 | `mvgeos show version` → `Error: No such command 'show version'`; AGENTS.md documents `mvgeos <prompt>` |
| 6. (Bonus, same file) | repl.py:756-768 | `_create_agent` hardcodes `"default-mvge"`, dropping CLI `--agent-name` |

---

## Target Architecture (Mirroring Pi)

**Pi flow:** `main()` → `createAgentSessionRuntime()` → per-mode runners → `session.prompt()` → render `state.messages[last]` (print-mode.ts).

**MvgeOS flow (new):**
```
mvgeos [OPTIONS] [--incantation PROMPT] [POSITIONAL_PROMPTS...]
    → _repl_callback()
        → _run_agent()
            → shared _create_agent()  (extracted/reused, not re-implemented)
            → _run_print_mode()       → coding_agent.run(prompt)
            → final response captured from run() return value, rendered
            → agent.close() in finally
```

Fidelity rules:
- **Single runtime factory**: one `_create_agent()` shared by REPL, TUI, and one-shot (Pi's `createAgentSessionRuntime`). No inline duplication in `main.py`.
- **Print mode**: one-shot reuses the same `CodingMvge.run()` loop the REPL uses; there is no separate hand-rolled loop.
- **Final response**: captured from the value `agent.run()` returns (Pi's `state.messages[last]` equivalent, loop.py:503-507 `new_invocations[-1]`), NOT from `MESSAGE_END`/`TURN_END` subscription (those fire per-invocation / carry no content) and NOT via live StreamRenderer (avoids double render).

---

## Implementation Steps (red → green → refactor, per repo TDD convention)

### Step 0 (VERIFY, already done): Mechanism for bug 5 is empirically proven
A variadic `prompts: list[str] = typer.Argument(None)` on the callback **swallows every registered subcommand** (`mvgeos tome list` → callback with `prompts=['tome','list']`; `mvgeos config show`/`--help`-of-subcommand likewise) in the installed Typer 0.27 / vendored `typer._click`. That design is rejected.

**Proven replacement** (verified by live probes against installed Typer 0.27): subclass `TyperGroup` overriding `invoke`:
```python
class MvgeosGroup(TyperGroup):
    def invoke(self, ctx: _click.Context):
        if ctx._protected_args:
            args = [*ctx._protected_args, *ctx.args]
            first = args[0] if args else ""
            if not _split_opt(first)[0] and first not in self.commands:
                ctx.meta["prompts"] = list(args)
                ctx.args = []
                ctx._protected_args = []
                with ctx:
                    return _click.Command.invoke(self, ctx)
        return TyperGroup.invoke(self, ctx)
```
Apply via `@app.callback(invoke_without_command=True, cls=MvgeosGroup)` (chosen approach; both `typer.Typer(cls=...)` and callback `cls=` apply it to the root group in Typer 0.27 — verified by probes; do not "simplify" to one or the other without re-probing). Verified behavior:
- `mvgeos tome list` → subcommand routed (SUBCONTAINER: `_protected_args=['tome']`, recognized command).
- `mvgeos show version` → callback with `ctx.meta["prompts"] == ["show", "version"]` (bug fixed).
- `mvgeos --model x p1 p2` → callback, prompts `['p1','p2']`, options parsed.
- `mvgeos --incantation hi` → prompts `None`, incantation `'hi'`.
- `mvgeos --help` → help, unchanged.
- Caveat (documented): options must precede positionals (`mvgeos p1 --model x` yields `prompts=['p1','--model','x']`) — consistent with `mvgeos [OPTIONS] [MESSAGES...]` usage and Pi's arg ordering.

`_repl_callback` then reads `ctx.meta.get("prompts")` (a `<list[str> | None>`) and merges with `--incantation` (incantation first, then positional prompts, in order) before calling `_run_agent`. The `ctx.meta` value is typed `Any` in Typer strict-stubs; cast to `list[str] | None` at read time.

### Step 1 (RED): Add tests first
New files (flat naming, no `test_` prefix, `python_files = "*.py"`):
- `mvgeos-cli/tests/unit/print_mode.py` (NEW — `tests/unit/` does not exist yet; create it). Hermetic: `AsyncMock`-based `CodingMvge`, no network/auth.
  - `test_run_print_mode_renders_response` — run() returns `MvgeResponse`; assert final text printed exactly ONCE, exit 0.
  - `test_run_print_mode_empty_prompts` — zero prompts → returns 0, `agent.run()` NOT called, nothing printed (documented contract).
  - `test_run_print_mode_rate_limit` — run() raises `RateLimitError` → friendly markup via `_render_exception`, no traceback, exit 1.
  - `test_run_print_mode_auth_error` — `AuthenticationError` → `Authentication failed (401)...`, exit 1.
  - `test_run_print_mode_generic_error` — arbitrary Exception → `[red]Error: ...[/red]`, exit 1.
  - NOTE (`close()` is NOT `_run_print_mode`'s job): `agent.close()` lives in `_run_agent`'s `finally` (Step 4), not in `_run_print_mode`. The close-on-exception guarantee is covered by the `_run_agent` unit test in `tests/integration/cli.py` — `test_run_agent_closes_agent_on_error` (AsyncMock `_create_agent` returns a mock agent whose `run()` raises; assert `close()` awaited) — NOT in `tests/unit/print_mode.py`.
- `mvgeos-cli/tests/integration/cli.py` — REWRITE affected tests (below) so the file is red before refactor. **Bug-4 guard lives here** (integration, exercises the REAL `_create_agent`/`CodingMvge`):
    - `test_bug4_single_registry_and_rune_providers` — hermetic: build a temp rune directory with a rune that registers a provider + a `MvgeSpell`; call the real `_create_agent` (with `env` pointed at the temp dirs, `AsyncMock`-patched realm/channeling layer so no network); assert `agent.registered_providers` contains the rune-registered provider and that exactly ONE registry/`MvgeState` exists for the agent (no double-construction). Do NOT mock `_create_agent` for this — a mocked `_create_agent` proving "mock returns what mock does" is tautological, and asserting "zero `RealmRegistry` in `_run_agent`" is vacuous because the registry now lives in `BaseMvge.__init__`. AC#5 depends on this test.
  - `test_build_spells*` (3 tests) → DELETED (Step 6). Replace with:
    - `test_one_shot_merges_incantation_and_positionals` — `app, ["--incantation","p0","p1","p2"]` → `incantation=="p0"`, `prompts==["p1","p2"]`.
    - `test_one_shot_positional_only` — `app, ["list","files"]` → `incantation is None`, `prompts==["list","files"]` (regression for bug 5).
    - `test_subcommands_still_route` — `app, ["tome","list"]` → subcommand runs, callback NOT invoked with prompts (regression guard).
    - `test_options_after_positionals_are_prompts` — documents caveat: `app, ["p1","--model","x"]` → `prompts==["p1","--model","x"]`.
    - `test_error_exit_code_propagates` — mock `_run_agent` returns `1` → `CliRunner` exit code `1`. Use the existing `@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})` so the callback reaches the mocked `_run_agent` (API-key load happens before `asyncio.run`).
    - `test_success_exit_code_zero` — mock `_run_agent` returns `0` → `CliRunner` exit code `0`. Same env-var patch pattern.
    - `test_run_agent_closes_agent_on_error` — AsyncMock `_create_agent` returns a mock agent whose `run()` raises; assert `close()` awaited (covers Step 4's finally).
  - `test_repl_callback_with_incantation` and `test_repl_callback_with_options` → KEEP UNCHANGED (`--incantation` remains an option; they still pass).
  - `test_get_session_dir` → KEPT (see Step 6 decision).
  - `test_app_help` → still passes.
- `mvgeos-cli/tests/integration/prompt.py` → `test_prompt_app_exists` still passes ("incantation" stays in help).

All invoke against a mock `_run_agent` (`AsyncMock` patch) + `CliRunner`. No network.

### Step 2 (GREEN): Refactor `_create_agent` in `commands/repl.py` to be shared
- Add `agent_name: str = DEFAULT_AGENT_NAME` parameter; use it in `MvgeEnvironment.resolve(agent_name, ...)` (replaces hardcoded `"default-mvge"`).
- Plumb `agent_name` through `run_repl()` and `run_tui()` signatures (default `DEFAULT_AGENT_NAME`).
- `commands/tui.py` already imports `_create_agent` — only the added param.

### Step 3 (GREEN): Add `_run_print_mode()` to `main.py`
New function mirroring Pi print-mode.ts + repl.py `_display_response`:
```
async def _run_print_mode(agent: CodingMvge, prompts: list[str]) -> int:
    try:
        for prompt in prompts:
            result = await agent.run(prompt)       # returns MvgeResponse (loop.py:503-507)
            _display_response(result)              # single, guaranteed render (import from repl.py)
        return 0
    except (RateLimitError, AuthenticationError) as exc:
        console.print(_render_exception(exc) or "")
        return 1
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        return 1
```
- NO StreamRenderer, NO event subscription — output rendered exactly once per response via `_display_response` (matching Pi print-mode.ts).
- Top-level imports only (per repo rule).
- Note (do NOT "dedupe"): `_run_print_mode` renders errors via main.py's module-level `console`, while `_display_response` uses repl.py's own module-level `console` — two console instances both writing stdout. Harmless; leave both in place so capture behavior in tests is unchanged.
- **Exit-code contract**: `_run_print_mode` returns `0` (success) or `1` (any error). Empty `prompts` → returns `0` WITHOUT calling `run()` (guard belongs in the loop: `for prompt in prompts:` naturally iterates zero times and returns 0). The single-prompt guard lives in `_run_agent`'s REPL/TUI dispatch (when `prompts_out` is empty), so `_run_print_mode` never sees the empty case from one-shot callers.

### Step 4 (GREEN): Rewrite `_run_agent()` in `main.py` to use the shared factory
- Compute effective prompt list: `prompts_out = ([incantation] if incantation else []) + (prompts or [])`.
- If `prompts_out` is empty → existing REPL/TUI dispatch, now forwarding `agent_name` to both (fixes bug 6 in interactive modes). Both branches `return 0` after their `await` (mypy strict requires `-> int`; `None` is falsy at runtime but fails the type gate).
- Else:
  ```
  agent: CodingMvge | None = None
  try:
      _validate_api_key(api_key)                    # import from repl.py
      # signature keeps `spells_enabled: list[str] | None` (test_repl_callback_with_options
      # asserts the kwarg is a LIST ["bash","read"]) — do NOT split a string in _run_agent.
      env = MvgeEnvironment.resolve(agent_name, overrides=...)  # DEFAULT_SOURCE: configured default spells
      resolved = env.config
      spells_joined = ",".join(spells_enabled) if spells_enabled else _default_spells_from_config(resolved)
      # `_default_spells_from_config(resolved)` == `resolved["spells_enabled"].value`
      # (the existing config-key read at main.py:114 today) — reuse it, do NOT invent a new key.
      agent = await _create_agent(model=..., api_key=api_key, spells=spells_joined, ...,
                                  agent_name=agent_name)
      return await _run_print_mode(agent, prompts_out)
  except ValueError as exc:
      console.print(f"[red]{exc}[/red]")            # covers _validate_api_key, unknown model, bad resume
      return 1
  except Exception as exc:
      console.print(_render_exception(exc) or f"[red]{exc}[/red]")
      return 1
  finally:
      if agent is not None:
          await agent.close()                       # stops RuneWatchers, closes Realm, shuts Tome
  ```
  `_run_agent` returns `int` (0 success / 1 error) so callers can map it to a process exit code (see Step 5). All error branches return `1` (NOT `None`) so a non-zero code always propagates.
- `agent = None` initialized BEFORE the try (prevents UnboundLocalError when `_create_agent` itself raises).
- **Empty-spells safeguard**: NEVER pass an empty comma string (that would become `spells=[]`, which `CodingMvge.__init__` treats as explicit-empty → disables ALL builtin spells). main.py keeps its `MvgeEnvironment.resolve()` to source configured default spells before joining into the comma string. This preserves current behavior.
- All rune/provider/session wiring (RuneRunner, RealmRegistry, MvgeTome, TomeLedger, Model, MvgeLoop, MvgeState, build_system_prompt) DELETED from main.py — `CodingMvge.initialize()` (via `_create_agent`) does it exactly once.
- Double `_validate_api_key` (here + inside `_create_agent`) is harmless — noted, not removed.
- `tui` flag: when prompts present, one-shot runs (TUI is interactive-only); existing cli.py `test_repl_callback_with_options` (asserts `tui=True` forwarded) still passes. Documented.

### Step 5 (GREEN): Add positional prompts to `_repl_callback` via `MvgeosGroup` + exit-code propagation
- Define `MvgeosGroup(TyperGroup)` (Step 0 code) in main.py.
- Apply `cls=MvgeosGroup` on `@app.callback(invoke_without_command=True, ...)`.
- Keep `incantation: str | None = typer.Option(None, "--incantation", ...)` unchanged.
- Read `prompts: list[str] | None = cast(Any, ctx.meta).get("prompts") or None`; merge with incantation per Step 4; pass both into `_run_agent(incantation=..., prompts=..., ...)`.
- **Exit-code propagation** (fixes silent exit-0 on error): change the callback tail from `asyncio.run(_run_agent(...))` to:
  ```
  code = asyncio.run(_run_agent(...))
  if code:
      raise typer.Exit(code)
  ```
  Integration tests must cover this: mock `_run_agent` to return `1` → `CliRunner` exit code is `1`; return `0` → exit `0`. (Today unknown-model already raises `typer.Exit(1)` via main.py:185; this preserves that contract for ALL one-shot error paths.)

### Step 6 (GREEN): Delete dead code in `main.py` + prune imports
- `_build_spells()` (main.py:306-317): unreferenced by production code; its removal pairs with deleting its 3 tests in `tests/integration/cli.py` (Step 1). Delete together; prune orphaned `SPELL_MAP` import.
- `_scope_for_path()` (main.py:70-76): unused after rewrite (CodingMvge owns rune path scoping via `_build_rune_paths_with_scope`). Delete.
- `_get_session_dir()` (main.py:302-303): KEEP with its `test_get_session_dir` test — it becomes test-covered dead code after the rewrite (one-shot passes CLI `session_dir` or `None` → `BaseMvge` defaults to `DEFAULT_TOME_DIR`; REPL/TUI default via `_create_agent` — neither branch calls `_get_session_dir`). Keeping it is an explicit decision to avoid a test migration with no payoff; do NOT describe it as "still used by `_run_agent`".
- Duplicate `console = Console()` (51 & 320) and `app = typer.Typer(...)` (67 & 322): keep one of each.
- Prune now-unused main.py imports (ruff F401 + mypy strict): `dataclasses`, `AsyncIterator`, `MvgeInvocation`, `MvgeState`, `SummonerRequest`, `MvgeLoop`, `MvgeTome`, `ContemplationLevel`(if unused), `Model`, `RealmResponse`, `ChannelConfig`, `get_model`, `RealmRegistry`, `load_runes_from_paths`, `RuneRunner`, `RuneContext`, `RuneScope`, `RuneWatcher`, `TomeLedger`, `build_system_prompt`(if unused), `SPELL_MAP`, and the `ensure_config_files` import from `mvgeos_agent.prompt_config` (its only production call is main.py:152, which the rewrite deletes; the REPL path never calls it).
- Keep: `DEFAULT_AGENT_NAME`, `DEFAULT_TOME_DIR`, `resolve_rune_paths` (only if still referenced — re-check after rewrite; prune if not).

### Step 7 (REFACTOR): Verify cleanup + acceptance
- Run `uv run pytest mvgeos-cli/tests/` until green, then `ruff`, then mypy strict.
- No `RuneWatcher` constructed in main.py anymore; `agent.close()` handles shutdown for all modes.

---

## Files to Modify

| File | Changes |
|------|---------|
| `mvgeos-cli/mvgeos_cli/main.py` | Add `MvgeosGroup`; rewrite `_run_agent`; add `_run_print_mode`; read `ctx.meta["prompts"]` in callback; apply `cls=`; delete `_build_spells` + `_scope_for_path`; dedupe `console`/`app`; prune imports; keep `_get_session_dir` |
| `mvgeos-cli/mvgeos_cli/commands/repl.py` | Add `agent_name` param to `_create_agent`/`run_repl`; hardcoded `"default-mvge"` → param (fixes bug 6) |
| `mvgeos-cli/mvgeos_cli/commands/tui.py` | Plumb `agent_name` to `_create_agent` |
| `mvgeos-cli/tests/unit/print_mode.py` | NEW — hermetic unit tests for `_run_print_mode` |
| `mvgeos-cli/tests/integration/cli.py` | Rewrite `test_build_spells*` → one-shot prompt/merge/subcommand/caveat tests; keep `--incantation` + `_get_session_dir` tests unchanged |

---

## Acceptance Criteria

1. `mvgeos "List files in ."` → positional prompt runs one-shot, spells sent, answer rendered once.
2. `mvgeos --incantation "List files"` → same (backward-compatible; existing tests pass).
3. `mvgeos "p1" "p2"` and `mvgeos --incantation p0 p1 p2` → multi-turn, each response rendered once.
4. `mvgeos --api-key bogus "prompt"` → `_validate_api_key` ValueError rendered as red text, exit 1, no traceback. `mvgeos --api-key sk-or-bogus-1234 "prompt"` → 401 path renders `Authentication failed (401)...`, exit 1, no traceback. No UnboundLocalError when `_create_agent` fails.
5. Provider registry created once per process-run; rune providers registered. Verified by the integration test `test_bug4_single_registry_and_rune_providers` in `tests/integration/cli.py` (Step 1), which exercises the real `_create_agent`/`CodingMvge.initialize` against a hermetic temp rune fixture and asserts `agent.registered_providers` reflects rune registrations with no double construction. (`mvgeos info` builds a fresh snapshot and cannot observe this; a mocked-`_create_agent` unit test would be tautological.)
6. All existing REPL/TUI/tome/config/info/build/prompt tests pass (no regression), including `test_repl_callback_with_*` and `test_get_session_dir`.
7. `mvgeos tome list` (and `config/info/build/setup` subcommands) still route to their sub-Typer; `mvgeos <prompt>` no longer errors with `No such command`.
8. `uv run pytest mvgeos-cli/tests/ --cov` → 90% coverage on new code. (Measurement: run `--cov=mvgeos_cli` filtering to changed functions/modules; note repo CI enforces `fail_under` threshold globally.)

## Open Decisions (resolved)
- **`--incantation` vs positionals**: both supported; `--incantation` kept as an option for backward compat and merged before positionals.
- **`--tui` + prompts**: prompts win; `--tui` is interactive-only (documented), matches current cli.py test.
- **Multi-prompt output**: each response rendered once. Differs from Pi (prints only last) — intentional, documented.
- **Options-after-positionals**: consumed as prompts (caveat documented + tested). Consistent with Pi's `[OPTIONS] [MESSAGES...]` ordering.
- **`_get_session_dir`**: kept.

---

## Rollback Plan
If integration tests fail: revert `main.py`, `repl.py`, `tui.py` to HEAD, keep new test files for future.