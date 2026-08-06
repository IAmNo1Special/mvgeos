# Technical Debt Remediation Plan — mvgeos-spells

> **DEPRECATED**: The `mvgeos-spells` package was deleted. Its functionality moved to `coding-mvge/spells/`. This document is retained for historical reference. See `coding-mvge/AGENTS.md` for current spell implementation.

## Overview

This document addresses each issue listed under the `mvgeos-spells` section of `TECHNICAL_DEBT_BY_PACKAGE.md`. The package currently consists of seven spell modules (`casting.py`, `reading.py`, `writing.py`, `editing.py`, `grep.py`, `finding.py`, `listing.py`) plus `types.py` and `__init__.py`. All spells are plain async functions returning `SpellResult`. The `aiofiles` dependency is declared in `pyproject.toml` but never used.

---

## Issue SP-1: Hardcoded empty parameters

**Root cause:** The `_build_spells()` functions in `mvgeos-cli/mvgeos/commands/prompt.py:63-74` and `coding-agent/coding_agent/agent.py:242-253` construct `MvgeSpell` objects with `parameters={}`. No JSON Schema is generated from the spell function signatures, so the LLM receives no parameter descriptions and cannot reliably produce valid tool-call arguments.

**Fix steps:**
1. Create `mvgeos_spells/schema.py` — a new module with a `generate_spell_schema(func: Callable) -> dict[str, Any]` function that uses `inspect.signature()` to introspect each `cast_*` function and produce a JSON Schema (`type: "object"`, `properties`, `required`, `description`).
2. Create `mvgeos_spells/registry.py` — a new module with a `SPELL_REGISTRY: dict[str, Callable]` mapping spell names to their cast functions, and a `get_spell_schema(name: str) -> dict[str, Any]` helper.
3. Populate `SPELL_REGISTRY` in `mvgeos_spells/__init__.py` and export it.
4. Update `mvgeos-cli/mvgeos/commands/prompt.py:63-74` — replace `parameters={}` with `parameters=generate_spell_schema(SPELL_MAP[name])`.
5. Update `coding-agent/coding_agent/agent.py:242-253` — replace `parameters={}` with `parameters=generate_spell_schema(DEFAULT_SPELL_MAP[name])`.

**Priority:** High  
**Effort:** M  
**Dependencies:** None (mvgeos-spells is a leaf package). Consumers (`mvgeos-cli`, `coding-agent`) must update their imports.

---

## Issue SP-2: Only bash has timeout

**Root cause:** `cast_bash()` in `mvgeos_spells/casting.py:8` accepts a `timeout_ms: int = 30000` parameter and uses `asyncio.wait_for()` to enforce it. No other spell function has any timeout mechanism. A long-running `cast_read` on a FIFO, `cast_find` on a massive tree, or `cast_grep` on a huge file can block the agent loop indefinitely.

**Fix steps:**
1. Create `mvgeos_spells/timeout.py` — a new module with an `async def with_spell_timeout[T](coro: Coroutine, timeout_ms: int, spell_name: str) -> SpellResult` helper that wraps any coroutine in `asyncio.wait_for()` and returns a `SpellResult` with `SpellStatus.PARTIAL` on `TimeoutError`.
2. Add a `DEFAULT_SPELL_TIMEOUT_MS: int = 30000` constant in `mvgeos_spells/types.py` (or `timeout.py`).
3. Wrap the body of `cast_read`, `cast_write`, `cast_edit`, `cast_grep`, `cast_find`, and `cast_list` in `with_spell_timeout()`.
4. Update `cast_bash` to use the shared `with_spell_timeout()` helper for consistency (refactor `casting.py:15-27`).

**Priority:** High  
**Effort:** M  
**Dependencies:** None.

---

## Issue SP-3: No sandboxing

**Root cause:** All spell functions operate on arbitrary `Path` objects with no restriction on which directories can be accessed. A malicious or buggy LLM could read `/etc/shadow`, write to system directories, or traverse outside the working directory. There is no `RuneContext`-style boundary enforcement in the spells package.

**Fix steps:**
1. Create `mvgeos_spells/sandbox.py` — a new module with a `SpellSandbox` class that holds an `allowed_roots: list[Path]` and provides:
   - `resolve_and_validate(path: str) -> Path` — resolves the path and checks it is within an allowed root; raises `PermissionError` otherwise.
   - `is_path_allowed(path: Path) -> bool` — public check.
2. Add a module-level `_sandbox: SpellSandbox | None = None` singleton in `mvgeos_spells/sandbox.py` with `set_sandbox()` and `get_sandbox()` accessors.
3. In each spell function (`reading.py:10`, `writing.py:10`, `editing.py:10`, `grep.py:13`, `finding.py:10`, `listing.py:10`), call `get_sandbox().resolve_and_validate(path)` before any filesystem access. If no sandbox is set, fall back to current behavior (backward compatibility).
4. Add a `set_sandbox(allowed_roots: list[str])` convenience function in `mvgeos_spells/__init__.py` that delegates to `sandbox.set_sandbox()`.

**Priority:** Medium  
**Effort:** M  
**Dependencies:** None for the package itself. Consumers (`mvgeos-cli`, `coding-agent`) should call `set_sandbox()` during initialization, but that is a follow-up in those packages.

---

## Issue SP-4: No spell result caching

**Root cause:** `cast_read()` in `mvgeos_spells/reading.py:17` calls `file_path.read_text()` on every invocation. When the agent reads the same file multiple times in a session (common for source files), each call hits disk. No in-memory cache exists.

**Fix steps:**
1. Create `mvgeos_spells/cache.py` — a new module with a `SpellCache` class using `functools.lru_cache` or a simple `dict[Path, tuple[float, str]]` with TTL-based eviction.
2. Add `get_cache()` / `set_cache()` module-level accessors.
3. In `cast_read` (`reading.py:17`), check the cache before reading from disk; populate the cache on miss.
4. Add a `clear_cache()` function in `mvgeos_spells/__init__.py`.
5. Cache key: resolved `Path` + file mtime. Invalidate on mtime change.

**Priority:** Medium  
**Effort:** S  
**Dependencies:** None.

---

## Issue SP-5: Blocking sync I/O in async spells

**Root cause:** `cast_read` (`reading.py:17`), `cast_write` (`writing.py:12`), and `cast_edit` (`editing.py:17`) use `Path.read_text()` and `Path.write_text()`, which are synchronous blocking calls. These block the event loop during I/O. The `aiofiles` package is declared as a dependency in `mvgeos-spells/pyproject.toml:8` but is never imported or used.

**Fix steps:**
1. In `mvgeos_spells/reading.py:3,17` — replace `from pathlib import Path` usage with `aiofiles.open()` for reading: `async with aiofiles.open(file_path, encoding="utf-8") as f: content = await f.read()`.
2. In `mvgeos_spells/writing.py:3,12` — replace `file_path.write_text()` with `async with aiofiles.open(file_path, "w", encoding="utf-8") as f: await f.write(content)`.
3. In `mvgeos_spells/editing.py:3,17,25` — replace both `read_text()` and `write_text()` with `aiofiles` equivalents.
4. Keep `Path` for existence checks and path manipulation (non-blocking).

**Priority:** High  
**Effort:** S  
**Dependencies:** `aiofiles>=23.2` is already in `pyproject.toml:8`.

---

## Issue SP-6: cast_find uses rglob recursively

**Root cause:** `cast_find()` in `mvgeos_spells/finding.py:17` calls `base.rglob(pattern)`, which recursively traverses the entire directory tree. On large project trees (e.g., `node_modules`, `.git`), this can be extremely slow and produce enormous result sets.

**Fix steps:**
1. Add a `max_depth: int = 10` parameter to `cast_find()` (`finding.py:8`).
2. Add a `max_results: int = 1000` parameter to cap the number of matches.
3. Replace `base.rglob(pattern)` with an iterative `Path.walk()` traversal (Python 3.14+ native) that respects `max_depth` and `max_results`.
4. Skip hidden directories (`.git`, `__pycache__`, `node_modules`) by default; add a `include_hidden: bool = False` parameter.

**Priority:** Medium  
**Effort:** S  
**Dependencies:** None (Python 3.14 `Path.walk()` is available per `pyproject.toml:5`).

---

## Issue SP-7: cast_grep reads entire file into memory

**Root cause:** `cast_grep()` in `mvgeos_spells/grep.py:23-24` calls `file_path.read_text(encoding="utf-8").splitlines()`, which loads the entire file into memory before iterating. For large files (e.g., multi-GB log files, large JSON dumps), this causes excessive memory usage.

**Fix steps:**
1. In `mvgeos_spells/grep.py:3,23-24` — replace `file_path.read_text().splitlines()` with `aiofiles.open()` and iterate line-by-line: `async with aiofiles.open(file_path, encoding="utf-8") as f: async for line in f:`.
2. This also resolves the blocking I/O issue for `cast_grep` (partially overlaps with SP-5).
3. Add a `max_file_size: int = 10 * 1024 * 1024` (10 MB) parameter; if the file exceeds this size, return a `SpellResult` with `SpellStatus.PARTIAL` and an error message indicating the file is too large.

**Priority:** Medium  
**Effort:** S  
**Dependencies:** `aiofiles` (already declared).

---

## Issue SP-8: No parameter validation

**Root cause:** All spell functions accept `dict[str, Any]` parameters directly from LLM tool calls (dispatched in `mvgeos-agent/mvgeos_agent/loop.py:388-391` via `spell.execute(tool_call["id"], tool_call.get("arguments", {}))`). There is no schema validation before execution. If the LLM passes wrong types, missing required params, or unexpected keys, the spell either crashes (caught by the broad `except Exception` in each spell) or silently produces incorrect results.

**Fix steps:**
1. In `mvgeos_spells/schema.py` (new module, see SP-1) — add a `validate_parameters(func: Callable, params: dict[str, Any]) -> dict[str, Any]` function that:
   - Uses `inspect.signature()` to get expected parameter names, types, and defaults.
   - Checks that all required parameters (no default) are present in `params`.
   - Casts values to the annotated types where possible.
   - Raises `ValueError` with a descriptive message on validation failure.
2. Call `validate_parameters()` at the top of each spell function before proceeding.
3. In `mvgeos_spells/__init__.py` — export `validate_parameters` and `generate_spell_schema`.

**Priority:** High  
**Effort:** M  
**Dependencies:** None. The `MvgeSpell.prepare_arguments()` method in `mvgeos-agent/mvgeos_agent/types.py:93-94` is currently a no-op pass-through; it could delegate to `validate_parameters()` in a follow-up.

---

## Issue SP-9: No global spell timeout

**Root cause:** Only `cast_bash()` has a timeout. Other spells (`cast_read`, `cast_write`, `cast_edit`, `cast_grep`, `cast_find`, `cast_list`) have no timeout at all. A spell operating on a FIFO (blocks forever on read), a very large file, or a deeply nested directory tree can hang the agent loop indefinitely. The `SpellExecutionMode.PARALLEL` enum value exists in `mvgeos-agent/mvgeos_agent/types.py:18-20` but is never used.

**Fix steps:**
1. Create `mvgeos_spells/timeout.py` (shared with SP-2) — define `DEFAULT_SPELL_TIMEOUT_MS = 30000` and an `async def with_spell_timeout()` helper.
2. Wrap each non-bash spell's core logic in `with_spell_timeout()`.
3. On `TimeoutError`, return `SpellResult` with `SpellStatus.PARTIAL`, `error_message=f"Spell '{name}' timed out after {timeout_ms}ms"`.
4. Make the timeout configurable per-spell via an optional `timeout_ms: int | None = None` parameter; when `None`, use `DEFAULT_SPELL_TIMEOUT_MS`.

**Priority:** High  
**Effort:** M  
**Dependencies:** None. Overlaps with SP-2 (same fix).

---

## Cross-Issue Notes

- **SP-2 and SP-9 overlap**: Both require a shared timeout mechanism. Implement `mvgeos_spells/timeout.py` once and use it for all spells.
- **SP-5 and SP-7 overlap**: Both require `aiofiles`. Implement async I/O in `reading.py`, `writing.py`, `editing.py`, and `grep.py` together.
- **SP-1 and SP-8 overlap**: Both require `mvgeos_spells/schema.py`. Implement schema generation and parameter validation in the same module.
- **SP-3 (sandboxing)** is the largest architectural change. It should be implemented as an opt-in feature (disabled by default) to avoid breaking existing behavior.
- **SP-4 (caching)** is the simplest and lowest-risk. It can be implemented independently.
- The `SpellDefinition` class in `mvgeos-runes/mvgeos_runes/types.py:64-88` has a `parameters` field that is already a `dict[str, Any]`. The schema generation function should be compatible with this format so that rune-provided spells can also benefit.
- The `MvgeSpell` dataclass in `mvgeos-agent/mvgeos_agent/types.py:87-103` has a `parameters: dict[str, Any]` field and a no-op `prepare_arguments()` method. In a follow-up to `mvgeos-agent`, `prepare_arguments()` could delegate to `validate_parameters()`.
