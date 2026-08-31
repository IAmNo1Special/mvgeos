# mvgeos-cli Technical Debt Remediation Plan

Based on `TECHNICAL_DEBT_BY_PACKAGE.md` and source code analysis.

---

## Issue Index

| ID | Title | Category | Priority | Effort |
|----|-------|----------|----------|--------|
| CLI-05 | Concrete coupling: CLI commands directly import `CodingMvge` | Architecture Quirk | Medium | M |

---

## Detailed Remediation Plans

---

## CLI-05: Concrete Coupling (CLI → `CodingMvge`)

**Files**: 
- `mvgeos_cli/main.py:11` — `from coding_mvge import CodingMvge`
- `mvgeos_cli/commands/repl.py:20` — `from coding_mvge import CodingMvge`

### Root Cause
CLI commands import and instantiate `CodingMvge` directly from the `coding-mvge` package. This couples the generic CLI entrypoint to a specific coding agent implementation rather than allowing pluggable agent backends conforming to an agent protocol.

### Fix Steps
1. **Extract interface/protocol** for agent in `mvgeos-agent`:
   ```python
   class MvgeAgent(Protocol):
       async def initialize(self) -> None: ...
       async def run(self, prompt: str) -> MvgeInvocation: ...
       async def close(self) -> None: ...
       @property
       def session_id(self) -> str | None: ...
   ```
2. **Make CLI commands accept an agent factory** or dynamic agent loader conforming to `MvgeAgent`.
3. Provide `CodingMvge` as the default agent implementation without hard-coding direct class instantiation in core command routines.

### Priority: Medium
### Effort: Medium (~60 lines across 3 files)
### Dependencies: mvgeos-agent (protocol definition)

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| CLI-05 | mvgeos-agent (protocol) | — |

---

## Recommended Implementation Order

1. **CLI-05** (Agent interface decoupling) — Decouple CLI from specific agent packages

---

## Testing Requirements

- Verify CLI works with mock agent implementing `MvgeAgent` protocol
- Run: `uv run python -m pytest mvgeos-cli/tests/ --cov`

