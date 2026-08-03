# Implementation Plan: Decoupled Host Sandbox Dependency Injection Architecture

Establish host sandbox ownership in `mvgeos-agent` while strictly avoiding inverted dependencies, by converting `BaseSandboxExecutor` in `heal_my_goap` to a structural `typing.Protocol`, creating `MvgeSandbox` in `mvgeos-agent`, exposing `api.sandbox` on `RuneAPI`, and injecting `api.sandbox` into `GoapEngine(sandbox=api.sandbox)` in the `heal_my_goap` extension Rune.

## User Review Required

> [!IMPORTANT]
> **Key Architectural Enhancements**:
> 1. **Structural Subtyping Contract (`typing.Protocol`)**: Convert `BaseSandboxExecutor` in `heal_my_goap.sandbox` from `abc.ABC` to `@runtime_checkable class BaseSandboxExecutor(Protocol)`. This allows any object implementing `execute_code(...)` to satisfy `heal_my_goap`'s type signatures without requiring `mvgeos` to import `heal_my_goap` (preventing core OS dependency inversion).
> 2. **Mage Host Sandbox (`MvgeSandbox` in `mvgeos-agent`)**: Create `MvgeSandbox` in `mvgeos-agent/mvgeos_agent/sandbox.py`. The Mage (`mvgeos-agent`) becomes the single host authority over process isolation, AST allowlists, and execution timeouts without depending on any extension.
> 3. **RuneAPI Host Sandbox Exposure**: Update `RuneRunner` and `RuneAPI` in `mvgeos-runes` to expose `api.sandbox`, allowing any loaded Rune extension to access the host Mage execution sandbox.
> 4. **Extension Rune Dependency Injection**: Update `rune.py` in `C:\Users\ivmno\.agents\.mvgeos\extensions\heal_my_goap\rune.py` to instantiate `engine = GoapEngine(sandbox=api.sandbox)` during `rune_factory(api)`.
> 5. **Standalone Fallback Autonomy**: `heal_my_goap`'s `GoapEngine` retains its internal `SandboxExecutor` as a default fallback when instantiated standalone outside MvgeOS (`engine = GoapEngine()`).
> 6. **Strict QA Gates**: Enforce 80-char line limit for `heal_my_goap` and 88-char line limit for `mvgeos`, alongside mypy strict mode and 100% pytest test coverage.

---

## Proposed Changes

### `heal_my_goap` Package

#### [MODIFY] [sandbox.py](file:///c:/Users/ivmno/Desktop/heal_my_goap/src/heal_my_goap/sandbox.py)
- Convert `BaseSandboxExecutor` from `abc.ABC` to `@runtime_checkable class BaseSandboxExecutor(Protocol)`.

---

### `mvgeos-agent` Package

#### [NEW] [sandbox.py](file:///c:/Users/ivmno/Desktop/mvgeos/mvgeos-agent/mvgeos_agent/sandbox.py)
- Define `MvgeSandbox` implementing `execute_code(self, code_str: str, context_globals: dict[str, Any] | None = None, timeout_seconds: float = 5.0, allowed_modules: set[str] | None = None) -> dict[str, Any]`.
- Provides Mage host sandbox execution using process isolation and configurable module allowlists (`allowed_modules`).

#### [MODIFY] [__init__.py](file:///c:/Users/ivmno/Desktop/mvgeos/mvgeos-agent/mvgeos_agent/__init__.py)
- Export `MvgeSandbox` in `mvgeos_agent.__all__`.

---

### `mvgeos-runes` Package

#### [MODIFY] [rune_runner.py](file:///c:/Users/ivmno/Desktop/mvgeos/mvgeos-runes/mvgeos_runes/rune_runner.py)
- Instantiate `self._sandbox = MvgeSandbox()` in `RuneRunner.__init__`.
- Expose `@property def sandbox(self) -> MvgeSandbox` on `RuneRunner`.

#### [MODIFY] [rune_api.py](file:///c:/Users/ivmno/Desktop/mvgeos/mvgeos-runes/mvgeos_runes/rune_api.py)
- Expose `@property def sandbox(self) -> MvgeSandbox` on `RuneAPI` returning `self._runner.sandbox`.

#### [MODIFY] [test_rune_api.py](file:///c:/Users/ivmno/Desktop/mvgeos/mvgeos-runes/tests_runes/test_rune_api.py)
- Add unit tests verifying `api.sandbox` property returns `MvgeSandbox` instance.

---

### MvgeOS Extension Rune

#### [MODIFY] [rune.py](file:///C:/Users/ivmno/.agents\.mvgeos\extensions\heal_my_goap\rune.py)
- Update `rune_factory(api: RuneAPI)` to instantiate `engine = GoapEngine(sandbox=api.sandbox)`.
- Update `SynthesizedRuneSpell.execute` to execute code via `self._engine.sandbox.execute_code(...)`.

#### [MODIFY] [test_heal_my_goap_integration.py](file:///c:/Users/ivmno/Desktop/mvgeos/coding-agent/tests_coding_agent/test_heal_my_goap_integration.py)
- Update integration tests to verify MvgeOS host sandbox dependency injection.

---

## Verification Plan

### Automated Tests
1. **`heal_my_goap` Test Suite**:
   ```bash
   uv run --dev pytest -v -s --cov=heal_my_goap --cov-report=term-missing --cov-fail-under=100 -W error
   uv run --dev mypy src tests
   uvx ruff check . --line-length 80 --fix
   uvx ruff format . --line-length 80
   ```
2. **`mvgeos` Test Suite**:
   ```bash
   uv run pytest --cov
   uv run mypy mvgeos-runes/ coding-agent/ mvgeos-agent/
   uvx ruff check mvgeos-runes/ coding-agent/ mvgeos-agent/ --line-length 88 --fix
   uvx ruff format mvgeos-runes/ coding-agent/ mvgeos-agent/ --line-length 88
   ```

### Manual & Interactive Verification
Run interactive demo script (`test_interactive_cli_demo.py`) to confirm MvgeOS host sandbox execution and dynamic spell registration.
