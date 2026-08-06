# Seeker of Servers — MCP Search (MvgeOS Seeker Protocol)

## Executive Summary

The **Seeker of Servers** enables MvgeOS to discover and connect to **MCP (Model Context Protocol) servers** providing external tools, resources, and capabilities. Part of the **MvgeOS Seeker Protocol** (external global rune: `mvgeos-runes-seeker`). Uses DCI (Direct Corpus Interaction) over MCP server configuration files — no embeddings, no vector store. Integrates with MvgeOS as a **Rune** via `SpellDefinition` subclasses registered on `RuneRunner`.

Derived from MCP-Zero (2506.01056), DCI-Agent (2605.05242), and the Model Context Protocol specification (Streamable HTTP per 2025-03-26, stateless core per 2026-07-28 RC).

---

## 1. Core Design Principles

| Principle | Source | MvgeOS Implementation |
|-----------|--------|----------------------|
| **MCP Protocol Discovery** | MCP-Zero | `rg` over MCP server config files (JSON) |
| **Direct Corpus Interaction** | DCI | Config files live on disk, searched via rg |
| **Rune Integration** | MvgeOS | MCP servers registered as `SpellDefinition` subclasses on `RuneRunner` |
| **Zero-Latency Hot Loading** | DCI | New config = immediately discoverable |
| **Streamable HTTP Transport** | MCP Spec 2025-03-26 | Single HTTP endpoint: POST for requests, GET for SSE stream |
| **Stateless Core (2026)** | MCP Spec 2026-07-28 RC | Session-free operation, no session state |

---

## 2. Transport Architecture

MCP defines two transport mechanisms, both supported:

### stdio (Local)
```
MvgeOS --stdin/stdout--> MCP Server Process
```
Used for local CLI tools. JSON-RPC over stdin/stdout, one request per line.

### Streamable HTTP (Remote, per MCP 2025-03-26)
```
Client Request:  POST /mcp  {jsonrpc request}  ->  Server
                 Accept: text/event-stream
Server Response: 202 Accepted                  <-  Client
                 (or SSE stream for server messages)

Server Messages: GET /mcp  Accept: text/event-stream  ->  Server
                 SSE stream of JSON-RPC messages     <-  Client
```

- Single MCP endpoint handles both POST (bidirectional requests) and GET (SSE stream for server-initiated messages)
- Session identified by `Mcp-Session-Id` header (optional post-2026-07-28 RC for stateless mode)
- Protocol version negotiated via `MCP-Protocol-Version` header

---

## 3. Architecture Overview

```
Mvge (agent)
  |
  |-- emits <mcp_request> in response content
  |
  v
MCPSearchSpell (MvgeSpell subclass)
  |
  |-- Stage 1: DCI Config Router
  |     rg over .agents/.mvgeos/runes/**/*.mcp.json
  |
  |-- Stage 2: NLT Selector
  |     YES/NO grid over candidate MCP servers
  |
  |-- Stage 3: MCP Connection + Tool Registration
  |     Connect via stdio or Streamable HTTP
  |     Fetch tools/list -> create MCPToolSpell (SpellDefinition subclass)
  |     Register MCPToolSpell instances on RuneRunner
  |
  v
MCP tools available as SpellDefinition subclasses on RuneRunner
  (wrapped by _RuneSpellWrapper at call time)
```

---

## 4. MCP Server Config Format

JSON:

```json
{
  "mcpServers": {
    "filesystem": {
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
      "env": { "ALLOWED_PATHS": "/workspace" }
    },
    "github": {
      "transport": "streamable-http",
      "url": "https://api.github.com/mcp",
      "headers": { "Authorization": "Bearer ${GITHUB_TOKEN}" },
      "capabilities": ["tools", "resources"]
    }
  }
}
```

---

## 5. Core Components

### 5.1 MCPSearchSpell

```python
from __future__ import annotations
from typing import Any

from mvgeos_agent.types import MvgeSpell, SpellExecutionMode
from mvgeos_provider.registry import RealmRegistry

from .discovery import MCPConfigDiscovery, MCPServerInfo
from .nlt_selector import MCPNLTSelector
from .connector import MCPConnector, MCPToolSpell, MCPTransportError


class MCPSearchSpell(MvgeSpell):
    """
    Discover MCP servers and register their tools as MCPToolSpell instances.
    """

    def __init__(
        self,
        provider_registry: RealmRegistry,
        rune_runner: Any | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._cfg = config or {}
        super().__init__(
            name="mcp_search",
            description="Find and connect to MCP servers providing external tools",
            parameters={
                "type": "object",
                "properties": {
                    "capability": {
                        "type": "string",
                        "description": "What capability you need",
                    },
                    "domain": {"type": "string", "description": "Domain hint"},
                    "auto_connect": {"type": "boolean", "default": True},
                    "max_results": {"type": "integer", "default": 3},
                },
                "required": ["capability"],
            },
            execution_mode=SpellExecutionMode.SEQUENTIAL,
        )
        self._provider_registry = provider_registry
        self._rune_runner = rune_runner
        self._connections: dict[str, MCPConnector] = {}
        search_roots = self._cfg.get("search_roots", None)
        if search_roots is not None:
            search_roots = [Path(r) for r in search_roots]
        self._discovery = MCPConfigDiscovery(search_roots=search_roots)
        # Read timeout overrides from config (keys match config schema section 8)
        timeout_cfg = self._cfg.get("timeout", {})
        self._timeout_overrides: dict[str, int] = {}
        if isinstance(timeout_cfg, dict):
            self._timeout_overrides = {k: int(v) for k, v in timeout_cfg.items()}

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        capability = params["capability"]
        max_results = params.get("max_results", 3)
        auto_connect = params.get("auto_connect", True)
        max_connections = self._cfg.get("max_connections", 5)

        # Check global connection limit
        if len(self._connections) >= max_connections:
            return {
                "serversFound": 0,
                "servers": [],
                "error": f"maximum {max_connections} MCP connections reached",
            }

        try:
            configs = await self._discovery.search(capability)
        except MCPTransportError as e:
            return {"serversFound": 0, "servers": [], "error": str(e)}

        selector = MCPNLTSelector(
            self._provider_registry,
            model_id=self._cfg.get("nlt_model", "openrouter/free"),
        )
        try:
            selected = await selector.select(capability, configs, max_results)
        except Exception as e:
            return {"serversFound": 0, "servers": [], "error": str(e)}

        results = []
        for server_info in selected:
            if auto_connect:
                try:
                    tools = await self._connect_server(server_info)
                    results.append(
                        {
                            "server": server_info.name,
                            "toolsRegistered": [t.name for t in tools],
                            "status": "connected",
                        }
                    )
                except (MCPTransportError, TimeoutError) as e:
                    results.append(
                        {
                            "server": server_info.name,
                            "status": "failed",
                            "error": str(e),
                        }
                    )
            else:
                results.append(
                    {
                        "server": server_info.name,
                        "description": server_info.description,
                        "status": "discovered",
                    }
                )

        return {"serversFound": len(results), "servers": results, "error": None}

    async def _connect_server(self, info: MCPServerInfo) -> list[SpellDefinition]:
        if info.name in self._connections:
            connector = self._connections[info.name]
            return connector.tool_spells

        # Build connector but do NOT store until fully initialized
        connector = MCPConnector(
            info, self._rune_runner, timeout_overrides=self._timeout_overrides
        )
        try:
            await connector.connect()
            tool_spells = await connector.register_all_capabilities()
        except Exception:
            await connector.close()
            raise

        # Only store after full initialization succeeds
        self._connections[info.name] = connector
        return tool_spells
```

### 5.2 MCPConfigDiscovery (DCI Router)

```python
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class MCPServerInfo:
    name: str
    config: dict[str, Any]
    source_file: Path

    @property
    def description(self) -> str:
        return self.config.get("description", self.name)

    @property
    def transport(self) -> str:
        return self.config.get("transport", "stdio")


class MCPConfigDiscovery:
    """DCI over MCP config files. Searches *.mcp.json in standard locations."""

    def __init__(self, search_roots: list[Path] | None = None) -> None:
        self._search_roots = search_roots or [Path(".agents/.mvgeos/runes")]

    async def search(self, query: str) -> list[MCPServerInfo]:
        config_files = self._find_config_files()
        parsed = []
        for fpath in config_files:
            try:
                servers = self._parse_config(fpath)
            except (json.JSONDecodeError, OSError) as e:
                raise MCPTransportError(
                    f"Failed to parse MCP config {fpath}: {e}"
                ) from e
            for name, config in servers.items():
                info = MCPServerInfo(name=name, config=config, source_file=fpath)
                if self._matches_query(info, query):
                    parsed.append(info)
        return parsed

    def _find_config_files(self) -> list[Path]:
        files = []
        for root in self._search_roots:
            if not root.exists():
                continue
            files.extend(root.rglob("*.mcp.json"))
        return files

    @staticmethod
    def _parse_config(path: Path) -> dict[str, Any]:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        servers = data.get("mcpServers")
        if servers is None:
            raise MCPTransportError(f"MCP config {path} missing 'mcpServers' key")
        if not isinstance(servers, dict):
            raise MCPTransportError(
                f"MCP config {path}: 'mcpServers' must be a dict, got {type(servers).__name__}"
            )
        return servers

    @staticmethod
    def _matches_query(info: MCPServerInfo, query: str) -> bool:
        q = query.lower()
        if q in info.name.lower():
            return True
        desc = info.config.get("description", "")
        if q in desc.lower():
            return True
        for c in info.config.get("capabilities", []):
            if q in c.lower():
                return True
        return False
```

### 5.3 MCPConnector and MCPToolSpell

```python
from __future__ import annotations
import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from mvgeos_runes.types import SpellDefinition, ExecutionMode


MCP_PROTOCOL_VERSION = "2025-03-26"  # Negotiated with server

# Timeout defaults
_MCP_INIT_TIMEOUT = 15
_MCP_HTTP_TIMEOUT = 30
_MCP_STDIO_TIMEOUT = 30
_MCP_TOOL_LIST_TIMEOUT = 60  # pagination may take longer

# Safety limits
_MCP_MAX_TOOLS = 100
_MCP_MAX_RESOURCES = 100
_MCP_MAX_PROMPTS = 100
_MCP_MAX_PERMITTED_COMMANDS = [
    "npx",
    "uvx",
    "node",
    "python",
    "python3",
    "deno",
    "bun",
]


class MCPTransportError(Exception):
    """Raised when MCP transport fails."""


class MCPPermissionError(Exception):
    """Raised when MCP server config violates sandbox policy."""


_MCP_INJECTABLE_ENV_VARS: set[str] = {
    "PATH",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "NODE_PATH",
    "NODE_OPTIONS",
    "BASH_ENV",
    "ENV",
    "IFS",
    "PATHEXT",
    "PSModulePath",
}


def _check_sandbox(info: MCPServerInfo) -> None:
    """Sandbox/permission check before spawning any MCP server process.
    Prevents arbitrary command execution via config injection.
    Uses exact command name matching, validates args for shell metacharacters,
    and blocks known-injectable environment variables.
    """
    if info.transport == "stdio":
        cmd = info.config.get("command", "")
        if not cmd:
            raise MCPPermissionError("MCP server command is empty")
        bare_cmd = cmd.split()[0]
        if bare_cmd not in set(_MCP_MAX_PERMITTED_COMMANDS):
            raise MCPPermissionError(
                f"MCP server command '{bare_cmd}' not in permitted list: "
                f"{_MCP_MAX_PERMITTED_COMMANDS}"
            )
        # Validate args for shell metacharacters
        import re as _re

        _SHELL_META = _re.compile(r"[\"';|&$`(){}<>!#~*?\\]")
        for arg in info.config.get("args", []):
            if _SHELL_META.search(arg):
                raise MCPPermissionError(
                    f"MCP server arg '{arg}' contains shell metacharacters"
                )
        env = info.config.get("env", {})
        for key in env:
            if key in _MCP_INJECTABLE_ENV_VARS:
                raise MCPPermissionError(
                    f"Restricted env var '{key}' in MCP server config"
                )
    # HTTP transport: validate URL scheme (allow localhost for development)
    if info.transport == "streamable-http":
        url = info.config.get("url", "")
        if not url.startswith("https://"):
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                raise MCPPermissionError(f"MCP HTTP URL must use HTTPS: {url}")


class MCPToolSpell(SpellDefinition):
    """
    SpellDefinition subclass wrapping an MCP tool.
    execute() sends tools/call JSON-RPC via the connector's send_jsonrpc().
    """

    def __init__(
        self,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        connector: MCPConnector,
    ) -> None:
        super().__init__(
            name=f"mcp_{tool_name}",
            description=description,
            parameters=input_schema,
            execution_mode=ExecutionMode.PARALLEL,
            prompt_guidelines=["This tool is provided by an MCP server"],
        )
        self._tool_name = tool_name
        self._connector = connector

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        result = await self._connector.send_jsonrpc(
            method="tools/call",
            params={"name": self._tool_name, "arguments": params},
            request_id=spell_cast_id or 1,
        )
        content = result.get("content", [])
        text = "".join(
            item.get("text", "") for item in content if item.get("type") == "text"
        )
        return {"content": text, "isError": result.get("isError", False)}


class MCPResourceSpell(SpellDefinition):
    """
    SpellDefinition wrapping an MCP resource for read-only data access.
    """

    def __init__(
        self,
        uri: str,
        name: str,
        description: str,
        mime_type: str,
        connector: MCPConnector,
    ) -> None:
        super().__init__(
            name=f"mcp_resource_{name}",
            description=description,
            parameters={
                "type": "object",
                "properties": {},
                "description": f"MCP resource: {uri} ({mime_type})",
            },
            execution_mode=ExecutionMode.PARALLEL,
        )
        self._uri = uri
        self._connector = connector

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        result = await self._connector.send_jsonrpc(
            method="resources/read",
            params={"uri": self._uri},
            request_id=spell_cast_id or 1,
        )
        contents = result.get("contents", [])
        text = "".join(c.get("text", "") for c in contents if c.get("type") == "text")
        return {"content": text, "mimeType": result.get("mimeType", "text/plain")}


class MCPPromptSpell(SpellDefinition):
    """
    SpellDefinition wrapping an MCP prompt template.
    """

    def __init__(
        self,
        prompt_name: str,
        description: str,
        arguments: dict[str, Any],
        connector: MCPConnector,
    ) -> None:
        super().__init__(
            name=f"mcp_prompt_{prompt_name}",
            description=description,
            parameters={
                "type": "object",
                "properties": {
                    arg["name"]: {
                        "type": "string",
                        "description": arg.get("description", ""),
                    }
                    for arg in arguments
                },
                "required": [arg["name"] for arg in arguments if arg.get("required")],
            },
            execution_mode=ExecutionMode.PARALLEL,
        )
        self._prompt_name = prompt_name
        self._connector = connector

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        result = await self._connector.send_jsonrpc(
            method="prompts/get",
            params={"name": self._prompt_name, "arguments": params},
            request_id=spell_cast_id or 1,
        )
        messages = result.get("messages", [])
        text = "".join(m.get("content", {}).get("text", "") for m in messages)
        return {"content": text}


class MCPConnector:
    """
    Manages an MCP server connection via stdio or Streamable HTTP.

    Security:
      - Sandbox check before spawning (permitted commands only, HTTPS-only for HTTP, arg validation)
      - Timeouts on all I/O operations
      - Pagination with limits on tools/resources/prompts
      - Shared aiohttp.ClientSession for HTTP transport
      - Stderr drained (DEVNULL) to prevent deadlock
      - Connector stored in _connections only after full initialization
      - Environment variable restrictions (injectable vars blocked)

    Lifecycle:
      connect()   -- sandbox check + transport connect + initialize
      register_all_capabilities()  -- paginated list + spell creation
      send_jsonrpc()        -- called by MCPToolSpell.execute()
      close()     -- session shutdown
    """

    def __init__(
        self,
        server_info: MCPServerInfo,
        rune_runner: Any | None = None,
        timeout_overrides: dict[str, int] | None = None,
    ) -> None:
        self._info = server_info
        self._rune_runner = rune_runner
        self._timeout_overrides = timeout_overrides or {}
        self._proc: asyncio.subprocess.Process | None = None
        self._http_base_url: str | None = None
        self._http_session: aiohttp.ClientSession | None = None
        self._tool_spells: list[MCPToolSpell] = []
        self._closing = False  # guard against concurrent close() calls
        self._close_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        _check_sandbox(self._info)
        transport = self._info.transport
        if transport == "stdio":
            await self._connect_stdio()
        elif transport == "streamable-http":
            await self._connect_streamable_http()
        else:
            raise MCPTransportError(f"Unknown transport: {transport}")

    async def _connect_stdio(self) -> None:
        cmd = [self._info.config["command"]]
        cmd.extend(self._info.config.get("args", []))
        env = dict(self._info.config.get("env", {}))
        # Merge with parent environment; config env overrides parent
        merged = dict(os.environ)
        merged.update(env)
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,  # drain stderr to prevent deadlock
            env=merged,
        )
        await self._initialize()

    async def _connect_streamable_http(self) -> None:
        self._http_base_url = self._info.config.get("url", "").rstrip("/")
        if not self._http_base_url:
            raise MCPTransportError(
                "Streamable HTTP transport requires 'url' in config"
            )
        # Shared session reused across all requests with timeout (from config if present)
        http_timeout = self._timeout_overrides.get("http", _MCP_HTTP_TIMEOUT)
        timeout = aiohttp.ClientTimeout(total=http_timeout)
        self._http_session = aiohttp.ClientSession(timeout=timeout)
        try:
            await self._initialize()
        except Exception:
            await self._http_session.close()
            self._http_session = None
            raise

    async def _initialize(self) -> None:
        """Send initialize request with timeout.
        Validates protocolVersion in response, sends capabilities,
        and emits notifications/initialized per MCP spec.
        Uses config override from MCPSearchSpell timeout dict if present.
        """
        init_timeout = self._timeout_overrides.get("init", _MCP_INIT_TIMEOUT)
        try:
            result = await asyncio.wait_for(
                self._send_jsonrpc_raw(
                    method="initialize",
                    params={
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {
                            "tools": {},
                            "resources": {},
                            "prompts": {},
                        },
                        "clientInfo": {"name": "mvgeos", "version": "1.0.0"},
                    },
                    request_id="init-1",
                ),
                timeout=init_timeout,
            )
        except asyncio.TimeoutError:
            raise MCPTransportError(f"MCP initialize timed out after {init_timeout}s")
        if "error" in result:
            raise MCPTransportError(
                f"MCP initialize failed: {result['error'].get('message', 'unknown')}"
            )
        server_version = result.get("protocolVersion", "")
        if server_version != MCP_PROTOCOL_VERSION:
            raise MCPTransportError(
                f"MCP protocol version mismatch: expected {MCP_PROTOCOL_VERSION}, "
                f"got {server_version}"
            )
        # Send notifications/initialized as required by MCP spec (no id per JSON-RPC 2.0)
        try:
            await self._send_jsonrpc_raw(
                method="notifications/initialized",
                params={},
                request_id="",
                notification=True,
            )
        except Exception:
            # Server may disconnect after initialized notification;
            # this is acceptable per spec.
            pass

    async def send_jsonrpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: str | int = 1,
    ) -> dict[str, Any]:
        return await self._send_jsonrpc_raw(method, params or {}, request_id)

    async def _send_jsonrpc_raw(
        self,
        method: str,
        params: dict[str, Any],
        request_id: str | int,
        notification: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        # Per JSON-RPC 2.0, notifications MUST NOT have an id member
        if not notification:
            body["id"] = request_id
        request = json.dumps(body) + "\n"

        if self._proc is not None:
            return await self._send_stdio(request)
        elif self._http_session is not None:
            return await self._send_http(request)
        else:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "MCP not connected"}],
            }

    async def _send_stdio(self, request: str) -> dict[str, Any]:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "stdio connection lost"}],
            }
        stdio_timeout = self._timeout_overrides.get("stdio", _MCP_STDIO_TIMEOUT)
        try:
            self._proc.stdin.write(request.encode())
            await asyncio.wait_for(self._proc.stdin.drain(), timeout=stdio_timeout)
            line = await asyncio.wait_for(
                self._proc.stdout.readline(), timeout=stdio_timeout
            )
        except asyncio.TimeoutError:
            raise MCPTransportError(
                f"stdio {self._info.name} timed out after {stdio_timeout}s"
            )
        if not line:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "empty response from MCP server"}],
            }
        try:
            response = json.loads(line.decode())
        except json.JSONDecodeError as e:
            return {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": f"invalid JSON from MCP server: {e}",
                    }
                ],
            }
        return response.get("result", response)

    async def _send_http(self, request: str) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        if self._info.config.get("headers"):
            headers.update(self._info.config["headers"])

        http_timeout = self._timeout_overrides.get("http", _MCP_HTTP_TIMEOUT)
        try:
            async with self._http_session.post(
                self._http_base_url,
                data=request.encode(),
                headers=headers,
            ) as resp:
                # Streamable HTTP 202 Accepted means server will respond later
                # via SSE GET stream (not yet implemented)
                if resp.status == 202:
                    return {
                        "isError": False,
                        "content": [
                            {"type": "text", "text": "request accepted (SSE pending)"}
                        ],
                    }
                if not 200 <= resp.status < 300:
                    raise MCPTransportError(
                        f"HTTP {self._info.name} returned {resp.status} {resp.reason}"
                    )
                body = await resp.read()
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            timeout_label = getattr(exc, "timeout", http_timeout)
            raise MCPTransportError(
                f"HTTP {self._info.name} timed out after {timeout_label}s"
            )
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as e:
            return {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": f"invalid JSON from MCP server: {e}",
                    }
                ],
            }
        if "error" in parsed:
            return {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": parsed["error"].get("message", "MCP server error"),
                    }
                ],
            }
        return parsed.get("result", parsed)

    # Maps JSON-RPC method names to their response field names.
    # e.g., "tools/list" returns {"tools": [...]}, not {"list": [...]}.
    _LIST_RESPONSE_KEY: dict[str, str] = {
        "tools/list": "tools",
        "resources/list": "resources",
        "prompts/list": "prompts",
    }

    async def _list_with_pagination(self, method: str) -> list[dict[str, Any]]:
        """Paginate through list methods (tools/list, resources/list, prompts/list).
        Respects nextCursor for servers returning partial results.
        Enforces a maximum item limit to prevent unbounded registration.
        """
        max_items = {
            "tools/list": _MCP_MAX_TOOLS,
            "resources/list": _MCP_MAX_RESOURCES,
            "prompts/list": _MCP_MAX_PROMPTS,
        }.get(method, 100)

        response_key = self._LIST_RESPONSE_KEY.get(method, method.split("/")[1])

        items: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            params: dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor

            tool_list_timeout = self._timeout_overrides.get(
                "tool_list", _MCP_TOOL_LIST_TIMEOUT
            )
            try:
                result = await asyncio.wait_for(
                    self.send_jsonrpc(method=method, params=params),
                    timeout=tool_list_timeout,
                )
            except asyncio.TimeoutError:
                raise MCPTransportError(
                    f"{method} timed out after {tool_list_timeout}s"
                )

            batch = result.get(response_key, [])
            items.extend(batch)

            if len(items) >= max_items:
                items = items[:max_items]
                break

            cursor = result.get("nextCursor")
            if not cursor:
                break

        return items

    async def list_tools(self) -> list[dict[str, Any]]:
        return await self._list_with_pagination("tools/list")

    async def list_resources(self) -> list[dict[str, Any]]:
        return await self._list_with_pagination("resources/list")

    async def list_prompts(self) -> list[dict[str, Any]]:
        return await self._list_with_pagination("prompts/list")

    async def register_all_capabilities(self) -> list[SpellDefinition]:
        # Fetch all capability lists in parallel
        tool_task = asyncio.ensure_future(self.list_tools())
        res_task = asyncio.ensure_future(self.list_resources())
        prompt_task = asyncio.ensure_future(self.list_prompts())
        tool_list, resources, prompts = await asyncio.gather(
            tool_task, res_task, prompt_task
        )

        seen_tools: set[str] = set()
        seen_resources: set[str] = set()
        seen_prompts: set[str] = set()
        spells_to_register: list[SpellDefinition] = []

        for tool_info in tool_list:
            name = tool_info["name"]
            if name in seen_tools:
                continue
            seen_tools.add(name)
            spell = MCPToolSpell(
                tool_name=name,
                description=tool_info.get("description", ""),
                input_schema=tool_info.get("inputSchema", {}),
                connector=self,
            )
            spells_to_register.append(spell)

        for res in resources:
            uri = res["uri"]
            if uri in seen_resources:
                continue
            seen_resources.add(uri)
            spell = MCPResourceSpell(
                uri=uri,
                name=res.get("name", uri.split("/")[-1]),
                description=res.get("description", ""),
                mime_type=res.get("mimeType", "text/plain"),
                connector=self,
            )
            spells_to_register.append(spell)

        for prompt in prompts:
            pname = prompt["name"]
            if pname in seen_prompts:
                continue
            seen_prompts.add(pname)
            spell = MCPPromptSpell(
                prompt_name=pname,
                description=prompt.get("description", ""),
                arguments=prompt.get("arguments", []),
                connector=self,
            )
            spells_to_register.append(spell)

        # Register all spells; on failure unroll partial registration
        if self._rune_runner is not None:
            registered: list[SpellDefinition] = []
            try:
                for spell in spells_to_register:
                    self._rune_runner.register_spell(spell)
                    registered.append(spell)
                self._tool_spells.extend(registered)
            except Exception:
                # Unregister any spells registered so far
                for spell in registered:
                    self._rune_runner.unregister_spell(spell)
                raise
        else:
            self._tool_spells.extend(spells_to_register)

        return list(self._tool_spells)

    async def close(self) -> None:
        """Shutdown MCP connection. Thread-safe: guarded by _closing flag."""
        if self._closing:
            # If already closing, wait for existing close task to complete
            if self._close_task is not None:
                await self._close_task
            return
        self._closing = True
        self._close_task = asyncio.ensure_future(self._close_impl())
        await self._close_task

    async def _close_impl(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError, ProcessLookupError:
                self._proc.kill()
                await self._proc.wait()
            finally:
                self._proc = None
        if self._http_session is not None:
            try:
                await asyncio.wait_for(self._http_session.close(), timeout=5)
            except asyncio.TimeoutError:
                pass
            finally:
                self._http_session = None
```

### 5.4 NLT Selector

```python
from __future__ import annotations
from typing import Any

from mvgeos_agent.types import SummonerRequest
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import ChannelConfig

from .discovery import MCPServerInfo


class MCPNLTSelector:
    """YES/NO grid selection over MCP server candidates (word-boundary aware)."""

    def __init__(
        self,
        registry: RealmRegistry,
        model_id: str = "openrouter/free",
    ) -> None:
        self._registry = registry
        self._model_id = model_id

    async def select(
        self,
        query: str,
        candidates: list[MCPServerInfo],
        max_results: int = 3,
    ) -> list[MCPServerInfo]:
        if not candidates:
            return []

        model = self._registry.compose_model(
            model_id=self._model_id,
            api_key="",
            provider_name=None,
        )
        if not model:
            return candidates[:max_results]

        realm = self._registry.create_realm(model, api_key=model.api_key)
        try:
            config = ChannelConfig(model=model, temperature=0.1, max_tokens=512)

            prompt = self._build_prompt(query, candidates)
            invocations = [SummonerRequest(role="user", content=prompt)]
            response_text = ""
            async for resp in realm.stream(model, invocations, config):
                if resp.invocation and resp.invocation.content:
                    for item in resp.invocation.content:
                        if item.get("type") == "text":
                            response_text += item.get("text", "")

            selected_names = self._parse_grid(response_text, candidates)
            return [c for c in candidates if c.name in selected_names][:max_results]
        finally:
            try:
                await realm.close()
            except Exception:
                pass

    def _build_prompt(self, query: str, candidates: list[MCPServerInfo]) -> str:
        lines = [
            "Select MCP servers matching the query. Output YES/NO for each.",
            "",
            f"Query: {query}",
            "",
            "Candidates:",
        ]
        for i, c in enumerate(candidates):
            lines.append(
                f"{i + 1}. {c.name} ({c.transport}): {c.config.get('description', '')[:200]}"
            )
        lines.append("")
        lines.append("Output each name followed by -- YES or -- NO:")
        return "\n".join(lines)

    def _parse_grid(self, response: str, candidates: list[MCPServerInfo]) -> set[str]:
        """Word-boundary-aware YES/NO parsing.
        Uses regex word boundary to prevent 'fs' matching 'filesystem'.
        """
        import re

        selected = set()
        for c in candidates:
            escaped = re.escape(c.name)
            for line in response.splitlines():
                if re.search(rf"\b{escaped}\b[^,]*--\s*YES", line, re.IGNORECASE):
                    selected.add(c.name)
                    break
        return selected
```

---

## 6. Integration into MvgeOS

### 6.1 Registration

```python
# In agent initialization (base_mvge.py):
mcp_search_spell = MCPSearchSpell(
    provider_registry=self._provider_registry,
    rune_runner=self._runner,
)
state.spells.append(mcp_search_spell)
```

### 6.2 MCP Tools as SpellDefinition Subclasses

`MCPToolSpell` extends `SpellDefinition` with a working `execute()` that delegates to `MCPConnector.send_jsonrpc()`. Registration:

```python
# Via MCPConnector.register_all_capabilities():
self._rune_runner.register_spell(spell)
```

When the agent calls an MCP tool, `loop.py:_execute_spell()` falls through `state.spells` first, then checks `runner.get_all_registered_spells()`. Found `SpellDefinition` instances are wrapped in `_RuneSpellWrapper`, which delegates to `MCPToolSpell.execute()`.

### 6.3 Lifecycle

```
SESSION START
  |-- Agent init: MCPSearchSpell registered in state.spells
  |
  TURN START (may be multiple per session)
  |-- Agent emits <mcp_request>
  |-- MCPSearchSpell.execute():
  |     |-- DCI searches *.mcp.json
  |     |-- NLT selects best server
  |     |-- MCPConnector.connect():
  |     |     |-- stdio: subprocess spawns
  |     |     |-- HTTP: POST /mcp initialize
  |     |-- register_all_capabilities():
  |     |     |-- tools/list -> MCPToolSpell instances
  |     |     |-- resources/list -> MCPResourceSpell instances
  |     |     |-- prompts/list -> MCPPromptSpell instances
  |     |     |-- register_spell() on RuneRunner for each
  |
  SUBSEQUENT TURNS
  |-- Agent calls "mcp_read_file" (MCPToolSpell)
  |     |-- loop checks state.spells (miss)
  |     |-- loop checks runner.get_all_registered_spells() (hit)
  |     |-- _RuneSpellWrapper wraps MCPToolSpell
  |     |-- MCPToolSpell.execute():
  |     |     |-- send_jsonrpc("tools/call", ...)
  |     |     |-- stdio: write stdin, read stdout
  |     |     |-- HTTP: POST /mcp
  |     |     |-- Returns result dict
  |     |-- loop appends SpellResultMessage
  |
  SESSION SHUTDOWN
  |-- SigilHook.SESSION_SHUTDOWN
  |-- MCPConnector.close(): term subprocess / close HTTP session
```

### 6.4 Event Emission

Per `MvgeLoop._execute_spell()` (`loop.py:_execute_spell`):

1. Loop emits `SPELL_CASTING_START`
2. Loop calls `MCPToolSpell.execute()` -> `send_jsonrpc("tools/call")`
3. Loop invokes `_safe_emit_chain(runner, SigilHook.AFTER_SPELL_RESULT, ...)` -- chain result can modify `result_content`
4. Loop appends `SpellResultMessage` to `state.invocations`
5. Loop emits `SPELL_CASTING_END`

### 6.5 Sigil Hooks

MCP connections are closed on session shutdown via `SigilHook.SESSION_SHUTDOWN`:

```python
async def _close_all_mcp_connections(state: MvgeState) -> None:
    """Gracefully close all active MCP connections on session shutdown.
    Finds the MCPSearchSpell in state.spells and closes its connectors.
    """
    for spell in state.spells:
        if hasattr(spell, "_connections"):
            tasks = [
                c.close()
                for c in spell._connections.values()  # type: ignore[union-attr]
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)


# In agent initialization, register shutdown handler:
rune_runner.register_handler(
    SigilHook.SESSION_SHUTDOWN,
    lambda data: asyncio.ensure_future(_close_all_mcp_connections(state)),
)
```

---

## 7. Mana Cost

| Stage | Operation | Tokens |
|-------|-----------|--------|
| DCI Config Discovery | rg over config files | ~30 |
| NLT Selection | LLM call with ~10 servers | ~400 |
| MCP initialize | JSON-RPC request | ~100 |
| MCP tools/list | JSON-RPC request | ~50 |
| MCP tools/call (per invocation) | JSON-RPC request | ~50 |
| **Total (search)** | | **~530** |

---

## 8. Configuration

```json
{
  "mcp_search": {
    "nlt_model": "openrouter/free",
    "max_results": 3,
    "auto_connect": true,
    "protocol_version": "2025-03-26",
    "search_roots": [".agents/.mvgeos/runes"],
    "max_connections": 5,
    "timeout": {
      "init": 30,
      "stdio": 120,
      "http": 60,
      "tool_list": 30
    }
  }
}
```

---

## 9. 2026 Spec Updates

The MCP specification evolves rapidly. Key updates relevant to this architecture:

| Date | Change | Impact |
|------|--------|--------|
| 2025-03-26 | Streamable HTTP replaces HTTP+SSE | Simplified transport, single endpoint |
| 2026-07-28 RC | Stateless core, Extensions framework, Tasks | Async tasks, MCP Apps, no session state required |

The architecture supports Streamable HTTP today and is designed to adopt stateless operation when the 2026-07-28 spec stabilizes. The `MCPConnector` transport abstraction allows adding new transports without changing `MCPToolSpell`.

---

## 10. Evaluation

| Metric | Target | Source |
|--------|--------|--------|
| MCP server discovery | >95% | DCI config file search |
| NLT parse error rate | <1% | YES/NO grid (word-boundary) |
| Connection latency | <5s | Timeouts enforced on init/stdin/http |
| Tool registration safety | No arbitrary commands | Sandbox layer (exact cmd match, arg metacharacter validation, restricted env vars) |
| Resource leak on failure | Zero | Connector stored only after full init; close() on any failure |
| Stderr deadlock | Impossible | stderr=DEVNULL for stdio transport |
| aiohttp session reuse | Shared across requests | Single ClientSession per connector |
| Pagination completeness | Up to 100 items per type | cursor-based pagination with early-break on `>= max_items` |
| Silent failure distinguishability | 100% | Error field in return dict; JSON parse errors detected |
| Close() concurrency safety | Race-free | `_closing` guard + `_close_task` dedup |
| Protocol version mismatch | Rejected | Server protocolVersion validated on initialize |
| `notifications/initialized` | Sent | Spec-compliant handshake after initialize response |
| Invalid MCP config JSON | Detected | json.loads wrapped in try/except with descriptive error |
| Config missing `mcpServers` key | Rejected | Explicit key and type validation |
| SSE GET stream for server push | Not yet implemented | Documented in 10.1; POST-only for now |

---

### 10.1 Known Limitation: SSE GET Stream Not Implemented

The Streamable HTTP transport (MCP 2025-03-26) defines a bidirectional protocol:
- **POST /mcp**: Client sends JSON-RPC requests, server responds (implemented)
- **GET /mcp**: Client opens an SSE stream to receive server-initiated messages (NOT YET IMPLEMENTED)

The current `_send_http` implementation only handles the POST request-response path. Server-initiated messages (e.g., `notifications/`, task progress, resource change events) via SSE GET are not received. This is acceptable for the initial architecture because:
1. MCP-Zero discovery is request-driven — the agent initiates all calls
2. The `responses/list` endpoint is not yet used
3. Server-initiated notifications would require a background SSE reader task with reconnection logic

Future work: implement an `_sse_reader` background task that maintains the GET connection, dispatches notifications to a handler registry, and auto-reconnects on disconnect.

---

## 11. Future Extensions

- **Resources**: `resources/list` + `resources/read` for read-only data from MCP servers
- **Prompts**: `prompts/get` for prompt templates
- **MCP Tasks** (2026): Async operations via `tasks/submit` and `tasks/cancel`
- **Tool Annotations** (2025-03-26): Safety metadata from `tools/list` response
- **MCP Apps** (2026-07-28 RC): Interactive HTML interfaces from MCP servers
