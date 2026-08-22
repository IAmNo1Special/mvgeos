# mvgeos-cli Technical Debt Remediation Plan

Based on `TECHNICAL_DEBT_BY_PACKAGE.md` (lines 109-121) and source code analysis.

---

## Issue Index

| ID | Title | Category | Priority | Effort |
|----|-------|----------|----------|--------|
| CLI-01 | Two config systems | Architecture Quirk | High | M |
| CLI-02 | Duplicate `_default_config_dir()` | Anti-Pattern/Bug | Medium | S |
| CLI-03 | Default model mismatch (REPL vs CLI) | Anti-Pattern/Bug | Medium | S |
| CLI-04 | Prompt-toolkit history unbounded | Performance/Scale | Low | S |
| CLI-05 | Circular-ish import: CLI → CodingAgent | Architecture Quirk | Medium | M |

---

## CLI-01: Two Config Systems

**Files**: 
- `mvgeos_cli/commands/config.py` — `.agents/.mvgeos/config.json`
- `mvgeos_agent/prompt_config.py` — `~/.agents/.mvgeos/{name}/SYSTEM.md` + `GUIDELINES.md`

### Root Cause
Two independent configuration mechanisms:
1. **CLI config** (`config.py:14-25`): JSON file at `.agents/.mvgeos/config.json` with model, mana_budget, max_tokens, temperature, contemplation_level, spells_enabled, runes_paths
2. **Agent config** (`prompt_config.py:44, 92, 96-123`): Markdown files at `~/.agents/.mvgeos/{name}/SYSTEM.md` and `GUIDELINES.md` loaded by `load_system_prompt()` and `load_guidelines()`

No synchronization between them. User sets model in CLI config but agent loads from Markdown.

### Fix Steps
1. **Unify configuration source** — single source of truth
   - Option A: Move all config to JSON (extend `config.json` with system_prompt, guidelines)
   - Option B: Move all config to Markdown (parse YAML frontmatter in SYSTEM.md)
   - **Recommended**: Option A — JSON is easier to parse/validate programmatically

2. **Create `mvgeos_cli/config.py` → `ConfigManager` class**:
   ```python
   class ConfigManager:
       def __init__(self, config_dir: Path = Path(".agents/.mvgeos")):
           self.config_file = config_dir / "config.json"
           self.agent_configs_dir = Path("~/.agents/.mvgeos").expanduser()
       
       def load(self) -> Config  # merges global + agent-specific
       def save(self, config: Config)
       def get_agent_config(self, agent_name: str) -> AgentConfig
       def set_agent_config(self, agent_name: str, config: AgentConfig)
   ```

3. **Add agent-specific section to `config.json`**:
   ```json
   {
     "model": "openrouter/free",
     "mana_budget": 10000,
     "agents": {
       "coding-mvge": {
         "system_prompt_path": "~/.agents/.mvgeos/coding-mvge/SYSTEM.md",
         "guidelines_path": "~/.agents/.mvgeos/coding-mvge/GUIDELINES.md"
       }
     }
   }
   ```

4. **Update `prompt_config.py`** to read from `ConfigManager` instead of direct filesystem access:
   - `load_system_prompt()` → `config_manager.get_agent_config(name).system_prompt`
   - `ensure_config_files()` → `config_manager.ensure_agent_config(name)`

5. **Add migration** — on first run, migrate existing Markdown configs to JSON

6. **Deprecate direct Markdown reads** in `prompt_config.py` with warnings

### Priority: High
### Effort: Medium (~150 lines across 3 files)
### Dependencies: mvgeos-agent (prompt_config.py), mvgeos-runes (rune paths)

---

## CLI-02: Duplicate `_default_config_dir()`

**File**: `mvgeos_agent/prompt_config.py:44` and `prompt_config.py:92`

### Root Cause
Exact duplicate function defined twice:
```python
# Line 44
def _default_config_dir(name: str) -> Path:
    return Path(f"~/.agents/.mvgeos/{name}").expanduser()


# Line 92 (identical)
def _default_config_dir(name: str) -> Path:
    return Path(f"~/.agents/.mvgeos/{name}").expanduser()
```

Second definition shadows first. First used by `build_system_prompt()`, second by `ensure_config_files()` and `load_system_prompt()`.

### Fix Steps
1. **Delete duplicate at line 92-93**
2. **Ensure single definition** at line 44 is used by all callers
3. **Add unit test** to verify single definition

### Priority: Medium
### Effort: Small (2 lines deleted)
### Dependencies: None

---

## CLI-03: Default Model Mismatch

**Files**: 
- `mvgeos_cli/main.py:21` — `"openrouter/free"`
- `mvgeos_cli/commands/repl.py:248` — `"openrouter/anthropic/claude-3.5-sonnet"`

### Root Cause
REPL default (`repl.py:248`) differs from CLI callback default (`main.py:21`). User running `mvgeos` (REPL) gets Claude 3.5 Sonnet; user running `mvgeos prompt` gets free router.

### Fix Steps
1. **Define single constant** in `mvgeos_cli/constants.py` (new file):
   ```python
   DEFAULT_MODEL = "openrouter/free"
   DEFAULT_REPL_MODEL = "openrouter/anthropic/claude-3.5-sonnet"
   ```
2. **Use constants** in both `main.py:21` and `repl.py:248`
3. **Document why they differ** (REPL = better default for interactive; prompt = cost-conscious default)

### Priority: Medium
### Effort: Small (new file + 2 imports + 2 line changes)
### Dependencies: None

---

## CLI-04: Prompt-Toolkit History Unbounded

**File**: `mvgeos_cli/commands/repl.py:88-91`

### Root Cause
```python
def _get_history_path() -> Path:
    path = Path(os.path.expanduser("~/.agents/.mvgeos/history"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
```

`FileHistory(path)` created at `repl.py:302` with no max size/rotation. History file grows indefinitely.

### Fix Steps
1. **Add `max_history_size` parameter** to `_get_history_path()` or `run_repl()`
2. **Use custom `FileHistory` subclass** with rotation:
   ```python
   class RotatingFileHistory(FileHistory):
       def __init__(self, filename: str, max_entries: int = 10000):
           super().__init__(filename)
           self.max_entries = max_entries

       def append(self, string: str) -> None:
           super().append(string)
           self._rotate_if_needed()

       def _rotate_if_needed(self):
           if len(self._history) > self.max_entries:
               # Keep last max_entries
               self._history = self._history[-self.max_entries :]
               self._save()
   ```
3. **Default `max_entries=10000`** (~1MB)

### Priority: Low
### Effort: Small (~30 lines)
### Dependencies: None

---

## CLI-05: Circular-ish Import: CLI → CodingMvge

**Files**: 
- `mvgeos_cli/commands/prompt.py:10` — `from coding_mvge import CodingMvge`
- `mvgeos_cli/commands/repl.py:13` — `from coding_mvge import CodingMvge`

### Root Cause
CLI commands import `CodingMvge` from `coding-mvge` package. `coding-mvge` imports from `mvgeos-agent`, `mvgeos-provider`, `mvgeos-runes`, `mvgeos-tome`. No direct import back to CLI, but creates tight coupling:
- CLI cannot be used without `coding-mvge` package
- `coding-mvge` is a specific agent implementation, not the framework

### Fix Steps
1. **Extract interface/protocol** for agent in `mvgeos-agent`:
   ```python
   # mvgeos_agent/agent_protocol.py
   class MvgeAgent(Protocol):
       async def initialize(self) -> None: ...
       async def run(self, prompt: str) -> MvgeInvocation: ...
       async def close(self) -> None: ...
       @property def session_id(self) -> str | None: ...
   ```
2. **Make `CodingMvge` implement `MvgeAgent`** (already does implicitly)
3. **Update CLI commands** to accept `MvgeAgent` factory instead of hardcoded `CodingMvge`:
   - `prompt.py:_run_agent()` → accept `agent_factory: Callable[[], MvgeAgent]`
   - `repl.py:run_repl()` → accept `agent_factory`
4. **Provide default factory** in `coding_mvge/__init__.py`:
   ```python
   def create_coding_mvge(...) -> CodingMvge: ...
   ```
5. **CLI entry points** import and use factory

### Priority: Medium
### Effort: Medium (~80 lines across 4 files)
### Dependencies: mvgeos-agent (new protocol), coding-mvge (factory)

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| CLI-01 | mvgeos-agent (prompt_config), mvgeos-runes | — |
| CLI-02 | — | — |
| CLI-03 | — | — |
| CLI-04 | — | — |
| CLI-05 | mvgeos-agent (protocol), coding-mvge (factory) | — |

---

## Recommended Implementation Order

1. **CLI-02** (Duplicate function) — Quick win, 2 minutes
2. **CLI-03** (Model mismatch) — Quick win, 5 minutes
3. **CLI-04** (History rotation) — Low risk, independent
4. **CLI-01** (Config unification) — High impact, medium effort
5. **CLI-05** (Import decoupling) — Architecture, medium effort

---

## Testing Requirements

- **CLI-01**: Config round-trip test (load → modify → save → load)
- **CLI-01**: Migration test (existing Markdown → JSON)
- **CLI-04**: History rotation test (append 15000 entries, verify only 10000 kept)
- **CLI-05**: Verify CLI works with mock agent implementing `MvgeAgent` protocol

Run: `uv run python -m pytest mvgeos-cli/tests/ --cov`
