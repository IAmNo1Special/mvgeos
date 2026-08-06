# Testing Strategy — MvgeOS Seeker Protocol

## Summary

Three `Protocol` abstractions decouple search grimoire components from their production dependencies (ripgrep, LLM providers, subprocess/HTTP transports), enabling unit testing without external resources. Each protocol has a production implementation and a test double.

---

## A. Corpus Search Protocols

The three grimoires use different discovery mechanisms. Tool Search uses pure rg content search. Skill Search uses pure rg body search (no YAML frontmatter — removed per adversarial review). MCP Search uses file-glob discovery. Each gets its own Protocol.

### A1. `DCISearcher` — Content Search (rg)

**Applies to**: `DCIRouter` (Tool Search), `DCI_SkillMatcher.match_body()` (Skill Search body stage)

**Problem**: These components shell out to `rg` (ripgrep), making tests slow, noisy, and environment-dependent.

**Interface**:

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class DCIQuery(Protocol):
    pattern: str
    path: str
    file_types: list[str] | None = None


@runtime_checkable
class DCISearcher(Protocol):
    """Abstract filesystem search over a corpus."""

    async def search(self, query: DCIQuery) -> list[str]:
        """Return matching file paths."""
        ...
```

**Production — RipgrepSearcher**:

```python
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_RG_OK = 0
_RG_NO_MATCH = 1
_RG_BAD_PATTERN = 2


@dataclass
class RipgrepQuery:
    pattern: str
    path: str
    file_types: list[str] | None = None
    fixed_string: bool = False  # Use -F flag to avoid regex exit-code-2 failures
    timeout: int = 10


class RipgrepSearcher:
    """Shells out to rg -- with timeout and exit-code handling."""

    async def search(self, query: RipgrepQuery) -> list[str]:
        args = ["rg"]
        if query.fixed_string:
            args.append("-F")
        else:
            args.append("-E")
            args.append("auto")
        args.extend(["-il", query.pattern, query.path])
        if query.file_types:
            for ft in query.file_types:
                args.extend(["--type", ft])
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=query.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise TimeoutError(f"rg timed out after {query.timeout}s")

            if proc.returncode == _RG_BAD_PATTERN:
                raise ValueError(
                    f"rg invalid regex pattern (exit 2). "
                    f"stderr: {stderr.decode(errors='replace')[:200]}"
                )
            if proc.returncode not in (_RG_OK, _RG_NO_MATCH):
                raise RuntimeError(
                    f"rg failed (exit {proc.returncode}). "
                    f"stderr: {stderr.decode(errors='replace')[:200]}"
                )

            return [
                p.strip()
                for p in stdout.decode(errors="replace").splitlines()
                if p.strip()
            ]

        except FileNotFoundError:
            raise FileNotFoundError("rg not found on PATH")
```

**Test — FakeSearcher**:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FakeSearcher:
    """In-memory searcher returning pre-configured results."""

    _results: dict[str, list[str]] = field(default_factory=dict)

    async def search(self, query: Any) -> list[str]:
        return self._results.get(query.pattern, [])

    def add_result(self, pattern: str, paths: list[str]) -> None:
        self._results[pattern] = paths
```

**Update Tool Search** to accept a `DCISearcher` in its constructor:

| Component | Change |
|---|---|
| `DCIRouter.__init__(self, searcher: DCISearcher, spells_root: Path)` | Stores `self._searcher = searcher` |

### A2. `ConfigGlobber` — File-Glob Discovery (rglob)

**Applies to**: `MCPConfigDiscovery` (MCP Search)

**Problem**: `MCPConfigDiscovery._find_config_files()` uses `root.rglob("*.mcp.json")` — a filesystem glob, not a content search. A `DCISearcher` is the wrong abstraction.

```python
@runtime_checkable
class ConfigGlobber(Protocol):
    async def find_files(self, roots: list[Path], pattern: str) -> list[Path]: ...
```

**Production**: `FileGlobber` — wraps `Path.rglob`.
**Test double**: `FakeGlobber` — returns predefined paths.

### A3. `FrontmatterParser` — Structured YAML Parsing (REMOVED)

**Applies to**: Was `DCI_SkillMatcher` (Skill Search)

**Removed per adversarial review**: YAML frontmatter parsing is eliminated from Seeker of Skills. Skill search now uses `rg -ilF` (fixed-string) body search exclusively — same DCISearcher protocol as tool search. This removes the YAML bomb attack surface, UnicodeDecodeError crash path, `---` body-truncation bugs, and the need for a separate FrontmatterParser abstraction.

Skill metadata (name, description) is derived heuristically from markdown structure (first `# heading`, first paragraph) — no structured parsing protocol needed.

---

## B. `NLTEvaluator` — Natural Language Tool Selection

**Problem**: `NLTSelector`, `MCPNLTSelector`, and `SkillNLTSelector` each construct a `RealmRegistry` → `Realm` pipeline, coupling selection logic to the LLM provider and incurring real API costs in tests.

**Interface**:

```python
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class NLTEvaluator(Protocol):
    """YES/NO grid evaluator for candidate selection."""

    async def evaluate(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[bool]:
        """Return a bool per candidate: True if selected, False if rejected."""
        ...
```

**Production — RealmNLTEvaluator**:

```python
from __future__ import annotations
from typing import Any

from mvgeos_agent.types import SummonerRequest
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import ChannelConfig


class RealmNLTEvaluator:
    """YES/NO grid via RealmRegistry -> Realm LLM call."""

    def __init__(self, registry: RealmRegistry) -> None:
        self._registry = registry

    async def evaluate(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[bool]:
        model = self._registry.compose_model(
            model_id="openrouter/free",
            api_key="",
            provider_name=None,
        )
        if not model:
            return [True] * len(candidates)

        realm = self._registry.create_realm(model, api_key=model.api_key)
        config = ChannelConfig(model=model, temperature=0.1, max_tokens=512)

        prompt = self._build_prompt(query, candidates)
        invocations = [SummonerRequest(role="user", content=prompt)]
        response_text = ""
        async for resp in realm.stream(model, invocations, config):
            if resp.invocation and resp.invocation.content:
                for item in resp.invocation.content:
                    if item.get("type") == "text":
                        response_text += item.get("text", "")

        return self._parse_grid(response_text, candidates)

    def _build_prompt(self, query: str, candidates: list[dict[str, Any]]) -> str:
        lines = [
            "Select candidates matching the query. Output YES/NO for each.",
            "",
            f"Query: {query}",
            "",
            "Candidates:",
        ]
        for i, c in enumerate(candidates):
            lines.append(
                f"{i + 1}. {c.get('name', f'candidate-{i}')}: {c.get('description', '')[:200]}"
            )
        lines.append("")
        lines.append("Output each name followed by -- YES or -- NO:")
        return "\n".join(lines)

    def _parse_grid(
        self, response: str, candidates: list[dict[str, Any]]
    ) -> list[bool]:
        """Word-boundary-aware YES/NO parsing.
        Uses regex word boundary to prevent name-substring collisions.
        """
        import re

        results = []
        for c in candidates:
            name = c.get("name", "")
            escaped = re.escape(name)
            selected = any(
                bool(re.search(rf"\b{escaped}\b.*--\s*YES", line, re.IGNORECASE))
                for line in response.splitlines()
            )
            results.append(selected)
        return results
```

**Test — StubNLTEvaluator**:

```python
from __future__ import annotations
from typing import Any


class StubNLTEvaluator:
    """Returns pre-configured selection mask — no LLM call."""

    def __init__(self, mask: list[bool] | None = None) -> None:
        self._mask = mask

    async def evaluate(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> list[bool]:
        if self._mask is not None:
            return self._mask[: len(candidates)]
        return [True] * len(candidates)
```

**Update each NLT selector** to accept an `NLTEvaluator`:

| Architecture | Selector | Change |
|---|---|---|
| Tool Search | `NLTSelector.__init__(self, evaluator: NLTEvaluator)` | Removes `RealmRegistry` dependency |
| MCP Search | `MCPNLTSelector.__init__(self, evaluator: NLTEvaluator)` | Removes `RealmRegistry` dependency |
| Skill Search | `SkillNLTSelector.__init__(self, evaluator: NLTEvaluator)` | Removes `RealmRegistry` dependency |

Each selector's `select()` method calls `self._evaluator.evaluate(query, candidate_dicts)` instead of constructing a realm channel.

---

## C. `MCPTransport` — MCP Connection Transport

**Problem**: `MCPConnector` hardcodes stdio and Streamable HTTP transport logic, making it impossible to test connection logic or tool registration without spawning real subprocesses or hitting real HTTP endpoints.

**Interface**:

```python
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MCPTransport(Protocol):
    """Abstract transport for MCP JSON-RPC communication."""

    async def connect(self) -> None:
        """Establish the transport connection."""
        ...

    async def send(self, request: str) -> dict[str, Any]:
        """Send a JSON-RPC request and return the parsed response."""
        ...

    async def close(self) -> None:
        """Tear down the transport."""
        ...
```

**Production — StdioTransport**:

```python
from __future__ import annotations
import asyncio
import json
from typing import Any


class StdioTransport:
    """MCP transport over subprocess stdin/stdout."""

    def __init__(
        self, command: str, args: list[str], env: dict[str, str] | None = None
    ) -> None:
        self._command = command
        self._args = args
        self._env = env or {}
        self._proc: asyncio.subprocess.Process | None = None

    STDIO_TIMEOUT = 30

    async def connect(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,  # prevent deadlock
            env=self._env,
        )

    async def send(self, request: str) -> dict[str, Any]:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "stdio not connected"}],
            }
        self._proc.stdin.write(request.encode())
        await asyncio.wait_for(self._proc.stdin.drain(), timeout=self.STDIO_TIMEOUT)
        line = await asyncio.wait_for(
            self._proc.stdout.readline(), timeout=self.STDIO_TIMEOUT
        )
        if not line:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "empty response"}],
            }
        return json.loads(line.decode()).get("result", json.loads(line.decode()))

    async def close(self) -> None:
        if self._proc is not None:
            if self._proc.stdin:
                self._proc.stdin.close()
            await self._proc.wait()
            self._proc = None
```

**Production — StreamableHTTPTransport**:

```python
from __future__ import annotations
import json
from typing import Any

import aiohttp
import asyncio


MCP_PROTOCOL_VERSION = "2025-03-26"


class StreamableHTTPTransport:
    """MCP transport over Streamable HTTP per MCP 2025-03-26.
    Uses a shared aiohttp.ClientSession to avoid TLS handshake per request.
    """

    HTTP_TIMEOUT = 30

    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers or {})
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()

    async def send(self, request: str) -> dict[str, Any]:
        if self._session is None:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "HTTP not connected"}],
            }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        headers.update(self._headers)
        async with asyncio.timeout(self.HTTP_TIMEOUT):
            async with self._session.post(
                self._base_url,
                data=request.encode(),
                headers=headers,
            ) as resp:
                body = await resp.read()
                return json.loads(body).get("result", json.loads(body))

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
```

**Test — FakeMCPTransport**:

```python
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeMCPTransport:
    """In-memory MCP transport returning canned responses.
    Supports cursor-based pagination: paginated methods match by
    method name + cursor hash for distinct page responses.
    """

    _responses: dict[str, dict[str, Any]] = field(default_factory=dict)

    async def connect(self) -> None:
        pass

    async def send(self, request: str) -> dict[str, Any]:
        req = json.loads(request)
        method = req.get("method", "")
        # For paginated methods, include cursor in lookup key
        params = req.get("params", {})
        cursor = params.get("cursor")
        key = f"{method}:{cursor}" if cursor else method
        return self._responses.get(key, {"isError": True, "content": []})

    async def close(self) -> None:
        pass

    def add_response(
        self, key: str, response: dict[str, Any], cursor: str | None = None
    ) -> None:
        """Add a canned response. For paginated responses, provide cursor."""
        lookup = f"{key}:{cursor}" if cursor else key
        self._responses[lookup] = response
```

**Update MCPConnector** to accept a transport in its constructor:

```python
class MCPConnector:
    """Manages an MCP server connection via injectable transport."""

    def __init__(
        self,
        server_info: MCPServerInfo,
        transport: MCPTransport,
        rune_runner: Any | None = None,
    ) -> None:
        self._info = server_info
        self._transport = transport
        self._rune_runner = rune_runner
        self._tool_spells: list[MCPToolSpell] = []

    async def connect(self) -> None:
        await self._transport.connect()
        await self._initialize()

    async def send_jsonrpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: str | int = 1,
    ) -> dict[str, Any]:
        request = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params or {},
                }
            )
            + "\n"
        )
        return await self._transport.send(request)

    async def close(self) -> None:
        await self._transport.close()
```

The factory logic (choosing `StdioTransport` vs `StreamableHTTPTransport` based on `server_info.transport`) moves to `MCPSearchSpell._connect_server()`:

```python
async def _connect_server(self, info: MCPServerInfo) -> list[MCPToolSpell]:
    if info.name in self._connections:
        connector = self._connections[info.name]
        return await connector.register_all_capabilities()
    transport = self._build_transport(info)
    connector = MCPConnector(info, transport=transport, rune_runner=self._rune_runner)
    await connector.connect()
    self._connections[info.name] = connector
    tool_spells = await connector.register_all_capabilities()
    return tool_spells


def _build_transport(self, info: MCPServerInfo) -> MCPTransport:
    if info.transport == "stdio":
        return StdioTransport(
            command=info.config["command"],
            args=info.config.get("args", []),
            env=dict(info.config.get("env", {})),
        )
    return StreamableHTTPTransport(
        base_url=info.config["url"],
        headers=info.config.get("headers"),
    )
```

---

## Integration Example

Testing `ToolSearchSpell` with protocol doubles:

```python
from __future__ import annotations
from pathlib import Path
import pytest

from mvgeos_spells.tool_search.spell import ToolSearchSpell
from mvgeos_spells.tool_search.router import SpellFileMatch


class TestToolSearchSpell:
    @pytest.mark.asyncio
    async def test_exact_stem_match_skips_nlt(self) -> None:
        searcher = FakeSearcher()
        searcher.add_result("read", ["spells/read.py"])

        evaluator = StubNLTEvaluator(mask=[True])

        spell = ToolSearchSpell(
            searcher=searcher,
            evaluator=evaluator,
        )

        result = await spell.execute(
            spell_cast_id="test-1",
            params={"operation": "read"},
        )

        assert result["spellsFound"] == 1
        assert result["error"] is None
        assert "read" in result["results"][0]["name"]

    @pytest.mark.asyncio
    async def test_multi_match_uses_nlt(self) -> None:
        searcher = FakeSearcher()
        searcher.add_result(
            "search", ["spells/find.py", "spells/grep.py", "spells/list.py"]
        )

        evaluator = StubNLTEvaluator(mask=[True, False, True])

        spell = ToolSearchSpell(
            searcher=searcher,
            evaluator=evaluator,
        )

        result = await spell.execute(
            spell_cast_id="test-2",
            params={"operation": "search"},
        )

        assert result["spellsFound"] == 2
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_error_propagation(self) -> None:
        """Silent failures are eliminated — errors propagate in result dict."""
        searcher = FakeSearcher(raise_on_search=RuntimeError("rg crashed"))

        spell = ToolSearchSpell(
            searcher=searcher,
            evaluator=StubNLTEvaluator(),
        )

        result = await spell.execute(
            spell_cast_id="test-3",
            params={"operation": "read"},
        )

        assert result["spellsFound"] == 0
        assert result["error"] is not None
        assert "rg crashed" in result["error"]
```

Testing `MCPConnector` with `FakeMCPTransport` (bypasses sandbox + real transports):

```python
@pytest.mark.asyncio
async def test_mcp_connector_register_tools() -> None:
    transport = FakeMCPTransport()
    transport.add_response("initialize", {"result": {"protocolVersion": "2025-03-26"}})
    transport.add_response(
        "tools/list",
        {
            "result": {
                "tools": [
                    {
                        "name": "read_file",
                        "description": "Read a file",
                        "inputSchema": {},
                    },
                ],
            },
        },
    )

    info = MCPServerInfo(
        name="test-server",
        config={"transport": "stdio", "command": "echo"},
        source_file=Path("test.mcp.json"),
    )
    connector = MCPConnector(info, transport=transport)
    # Sandbox check only applies to real transports — FakeMCPTransport bypasses it
    await connector.connect()
    tools = await connector.register_all_capabilities()

    assert len(tools) == 1
    assert tools[0].name == "mcp_read_file"


@pytest.mark.asyncio
async def test_mcp_connector_leak_prevention() -> None:
    """Connector is NOT stored in _connections until full init succeeds."""
    transport = FakeMCPTransport()
    transport.add_response("initialize", {"result": {"protocolVersion": "2025-03-26"}})
    transport.add_response("tools/list", {"result": {"tools": []}})

    spell = MCPSearchSpell(provider_registry=MagicMock(), rune_runner=None)
    info = MCPServerInfo(
        name="test-server",
        config={"transport": "stdio", "command": "echo"},
        source_file=Path("test.mcp.json"),
    )

    # Before connect: not in connections
    assert info.name not in spell._connections

    # After successful connect+register: stored
    await spell._connect_server(info)
    assert info.name in spell._connections

    # On failure: not stored
    transport.add_response("tools/list", {"error": {"message": "crash"}})
    info2 = MCPServerInfo(
        name="failing-server",
        config={"transport": "stdio", "command": "echo"},
        source_file=Path("test.mcp.json"),
    )
    with pytest.raises(MCPTransportError):
        await spell._connect_server(info2)
    assert "failing-server" not in spell._connections


@pytest.mark.asyncio
async def test_mcp_connector_pagination() -> None:
    """Paginated list methods collect all pages up to the item limit."""
    transport = FakeMCPTransport()
    transport.add_response("initialize", {"result": {"protocolVersion": "2025-03-26"}})
    transport.add_response(
        "tools/list",
        {
            "result": {
                "tools": [
                    {"name": f"tool_{i}", "description": "", "inputSchema": {}}
                    for i in range(50)
                ],
                "nextCursor": "page-2",
            },
        },
    )
    transport.add_response(
        "tools/list",
        {
            "result": {
                "tools": [
                    {"name": f"tool_{i}", "description": "", "inputSchema": {}}
                    for i in range(50, 75)
                ],
            },
        },
        cursor="page-2",  # matches the cursor-based lookup key "tools/list:page-2"
    )

    info = MCPServerInfo(
        name="paged-server",
        config={"transport": "stdio", "command": "echo"},
        source_file=Path("test.mcp.json"),
    )
    connector = MCPConnector(info, transport=transport)
    await connector.connect()
    tools = await connector.register_all_capabilities()

    assert len(tools) == 75  # 50 from page 1, 25 from page 2


@pytest.mark.asyncio
async def test_sandbox_rejects_arbitrary_command() -> None:
    """Sandbox layer prevents arbitrary command execution."""
    from mvgeos_spells.mcp_search.connector import _check_sandbox, MCPPermissionError

    info = MCPServerInfo(
        name="evil-server",
        config={"transport": "stdio", "command": "rm", "args": ["-rf", "/"]},
        source_file=Path("evil.mcp.json"),
    )
    with pytest.raises(MCPPermissionError, match="not in permitted list"):
        _check_sandbox(info)


@pytest.mark.asyncio
async def test_sandbox_rejects_http_without_https() -> None:
    """HTTP transport requires HTTPS URL."""
    from mvgeos_spells.mcp_search.connector import _check_sandbox, MCPPermissionError

    info = MCPServerInfo(
        name="http-server",
        config={"transport": "streamable-http", "url": "http://example.com/mcp"},
        source_file=Path("http.mcp.json"),
    )
    with pytest.raises(MCPPermissionError, match="HTTPS"):
        _check_sandbox(info)
```

---

## Dependency Injection Wiring (Proposed Refactoring)

The architecture documents currently use direct constructor args (`provider_registry`, `rune_runner`). The Protocol abstractions in this doc require a constructor refactoring — each component accepts its Protocol dependency rather than constructing it internally. This section shows the target state after that refactoring.

Production wiring in `base_mvge.py` (or `Mvge.build()`):

```python
# Protocol-based constructors
searcher = RipgrepSearcher()
globber = FileGlobber()
evaluator = RealmNLTEvaluator(provider_registry=self._provider_registry)

# Tool search
dcirouter = DCIRouter(
    searcher=searcher,
    spells_root=Path(".agents/.mvgeos/runes/spells"),
    rg_timeout=10,
)
nlt_selector = NLTSelector(evaluator=evaluator)
lazy_registry = LazySpellRegistry()
tool_search_spell = ToolSearchSpell(
    router=dcirouter,
    nlt_selector=nlt_selector,
    lazy_registry=lazy_registry,
)

# MCP search
nlt_selector_mcp = MCPNLTSelector(evaluator=evaluator)
mcp_search_spell = MCPSearchSpell(
    discovery=MCPConfigDiscovery(globber=globber),
    nlt_selector=nlt_selector_mcp,
    rune_runner=self._runner,
    sandbox_enabled=True,
)

# Skill search
nlt_selector_skill = SkillNLTSelector(evaluator=evaluator)
skill_search_spell = SkillSearchSpell(
    matcher=DCI_SkillMatcher(searcher=searcher),  # no frontmatter parser
    nlt_selector=nlt_selector_skill,
)

state.spells.extend([tool_search_spell, mcp_search_spell, skill_search_spell])
```

Test DI wiring (in any `conftest.py` or test fixture):

```python
@pytest.fixture
def fake_searcher() -> FakeSearcher:
    return FakeSearcher()


@pytest.fixture
def fake_globber() -> FakeGlobber:
    return FakeGlobber()


@pytest.fixture
def stub_evaluator() -> StubNLTEvaluator:
    return StubNLTEvaluator()
```
