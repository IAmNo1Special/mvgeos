# mvgeos-provider Technical Debt Remediation Plan

Based on analysis of `TECHNICAL_DEBT_BY_PACKAGE.md` and source files in `mvgeos-provider/mvgeos_provider/`.

---

## Issue Index

| ID | Category | Description | Priority | Effort | Dependencies |
|----|----------|-------------|----------|--------|--------------|
| PROV-01 | Anti-Pattern | No connection pooling — new `httpx.AsyncClient` per `OpenRouterRealm` instance | High | M | None |
| PROV-02 | Anti-Pattern | No rate limiting / backoff / retry logic for OpenRouter API calls | High | M | PROV-01 |
| PROV-03 | Anti-Pattern | Model registry loads all models eagerly at init (no lazy loading) | Medium | M | None |
| PROV-04 | Anti-Pattern | Hardcoded `FREE_MODELS` / `PAID_MODELS` lists in `models.py` | Medium | S | None |
| PROV-05 | Anti-Pattern | Streaming tightly coupled to OpenRouter SSE format in `_invocations_to_messages()` | Medium | M | PROV-01 |
| PROV-06 | Performance | 24h cache TTL may serve stale model data | Low | S | None |
| PROV-07 | Performance | No HTTP/2 or connection pooling | Medium | M | PROV-01 |
| PROV-08 | Architecture | `mana_limit` in `ChannelConfig` ignored by OpenRouter provider | Medium | S | None |
| PROV-09 | Architecture | `ContemplationLevel` in `ChannelConfig` passed but unused by OpenRouter | Low | S | mvgeos-agent |

---

## Detailed Remediation Plans

---

### PROV-01: No Connection Pooling — New `httpx.AsyncClient` per Instance

**Root Cause**  
`OpenRouterRealm.__init__()` (openrouter.py:60-67) creates a new `httpx.AsyncClient` per instance. The `ProviderRegistry.create_realm()` (registry.py:35-84) creates a new `OpenRouterRealm` per request/agent, so each agent turn opens a new TCP connection. No connection reuse across requests.

**Files & Lines**
- `mvgeos_provider/openrouter.py:54-67` — `OpenRouterRealm.__init__()`
- `mvgeos_provider/registry.py:35-84` — `ProviderRegistry.create_realm()`

**Fix Steps**
1. **Add connection pool to `ProviderRegistry`** (registry.py)
   - Add `_http_client: httpx.AsyncClient | None = None` field
   - Add `async def get_http_client() -> httpx.AsyncClient` that creates shared client with limits
   - Add `async def close()` to close shared client on shutdown

2. **Modify `OpenRouterRealm` to accept shared client** (openrouter.py:54-67)
   - Add optional `client: httpx.AsyncClient | None` parameter to `__init__`
   - If provided, use it; else create own (backward compat)
   - Add `_owns_client` flag to track ownership for `close()`

3. **Update `ProviderRegistry.create_realm()`** (registry.py:78-84)
   - Get shared client via `await self.get_http_client()`
   - Pass to `OpenRouterRealm(api_key=..., base_url=..., client=shared_client)`

4. **Configure connection pool limits** (registry.py)
   ```python
   limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
   timeout = httpx.Timeout(60.0, connect=10.0)
   ```

5. **Add lifecycle management** — ensure `ProviderRegistry.close()` is called on agent shutdown (coordinate with mvgeos-agent)

**Priority**: High  
**Effort**: Medium (3-4 files, ~80 lines changed)  
**Dependencies**: None (but PROV-02 builds on this)

---

### PROV-02: No Rate Limiting / Backoff / Retry Logic

**Root Cause**  
`OpenRouterRealm.stream()` (openrouter.py:88-105) makes a single `httpx.AsyncClient.stream()` call with only httpx default timeout. No retry on 429/5xx, no exponential backoff, no respect for `Retry-After` headers. `ChannelConfig.max_retries` (types.py:28) exists but is ignored.

**Files & Lines**
- `mvgeos_provider/openrouter.py:88-105` — `stream()` method
- `mvgeos_provider/types.py:26-29` — `ChannelConfig.max_retries`, `timeout_ms`

**Fix Steps**
1. **Add retry utility** — new module `mvgeos_provider/retry.py` with:
   ```python
   async def stream_with_retry(
       client: httpx.AsyncClient,
       method: str,
       url: str,
       json: dict,
       config: ChannelConfig,
       max_retries: int = 3,
   ) -> AsyncIterator[httpx.Response]:
       # Exponential backoff with jitter
       # Respect Retry-After header
       # Retry on 429, 5xx
   ```

2. **Refactor `OpenRouterRealm.stream()`** (openrouter.py:69-161)
   - Use `stream_with_retry()` instead of raw `client.stream()`
   - Pass `config.max_retries` and `config.timeout_ms`
   - Handle `httpx.TooManyRedirects`, `httpx.ConnectError` etc.

3. **Add rate limit headers parsing** — extract `x-ratelimit-limit`, `x-ratelimit-remaining`, `retry-after` from response headers

4. **Add `RateLimitExceeded` exception** in `types.py` for explicit handling upstream

**Priority**: High  
**Effort**: Medium (new file + ~60 lines changed in openrouter.py)  
**Dependencies**: PROV-01 (shared client needed for connection reuse during retries)

---

### PROV-03: Model Registry Eager Loading — No Lazy Loading

**Root Cause**  
`ModelRegistry.__init__()` (model_registry.py:25-28) calls `_load_baseline()` which loads ALL hardcoded models (FREE_MODELS + PAID_MODELS = ~50 models) into `self._models` dict immediately. `load_cache()` loads entire cached JSON into memory. No lazy loading — all models in memory even if only 1-2 used.

**Files & Lines**
- `mvgeos_provider/model_registry.py:24-52` — `ModelRegistry.__init__`, `_load_baseline`, `load_cache`
- `mvgeos_provider/models.py:3-70` — Hardcoded model lists

**Fix Steps**
1. **Convert to lazy loading** (model_registry.py)
   - Remove `_load_baseline()` call from `__init__`
   - Add `_baseline_loaded: bool = False` flag
   - Add `_ensure_baseline_loaded()` called at start of `get()`, `list_all()`, `refresh()`
   - In `_ensure_baseline_loaded()`: load hardcoded models + cache if not loaded

2. **Add model lookup by provider/filter** — new method `list_by_provider(provider: str) -> list[Model]` that only loads matching models

3. **Optional: Pagination for `list_all()`** — add `limit`, `offset` params for large catalogs

4. **Update `ProviderRegistry.compose_model()`** (registry.py:86-121) — ensure it triggers lazy load

**Priority**: Medium  
**Effort**: Medium (~50 lines changed in model_registry.py)  
**Dependencies**: None

---

### PROV-04: Hardcoded Model Lists in `models.py`

**Root Cause**  
`FREE_MODELS` and `PAID_MODELS` (models.py:3-50) are hardcoded tuples. Adding/removing models requires code change + release. No mechanism to fetch from OpenRouter API dynamically or load from user config.

**Files & Lines**
- `mvgeos_provider/models.py:3-70` — `FREE_MODELS`, `PAID_MODELS`, `MODELS` dict

**Fix Steps**
1. **Add config file support** — new file `~/.agents/.mvgeos/models.json` with user-overridable model list
2. **Modify `ModelRegistry._load_baseline()`** (model_registry.py:40-52)
   - Load hardcoded models as fallback defaults
   - Merge with user config file (user config wins)
   - Load dynamic models from OpenRouter API cache
3. **Add `ModelRegistry.add_model(model: Model)` and `remove_model(model_id: str)`** for runtime modification
4. **Add CLI command** `mvgeos models refresh` → calls `ModelRegistry.refresh()`
5. **Deprecate module-level `MODELS` dict** (models.py:52) — move all access through `ModelRegistry`

**Priority**: Medium  
**Effort**: Small-Medium (new config file + ~40 lines in model_registry.py + models.py cleanup)  
**Dependencies**: None (but pairs well with PROV-03)

---

### PROV-05: Streaming Tightly Coupled to OpenRouter SSE Format

**Root Cause**  
`_invocations_to_messages()` (openrouter.py:13-51) and `stream()` parsing logic (openrouter.py:107-161) assume OpenRouter's specific SSE delta format:
- `chunk.choices[0].delta.content`
- `chunk.choices[0].delta.tool_calls`
- `chunk.choices[0].finish_reason`
- `chunk.usage.total_tokens`

The `Realm` base class (base.py:9-16) has no streaming abstraction — `OpenRouterRealm` implements OpenRouter-specific parsing directly.

**Files & Lines**
- `mvgeos_provider/openrouter.py:13-51` — `_invocations_to_messages()`
- `mvgeos_provider/openrouter.py:107-161` — SSE parsing in `stream()`
- `mvgeos_provider/base.py:9-16` — `Realm` base class (no streaming abstraction)

**Fix Steps**
1. **Define streaming protocol in `base.py`** — add abstract methods:
   ```python
   async def _prepare_request(self, model, invocations, config) -> httpx.Request
   def _parse_sse_line(self, line: str) -> RealmResponse | None
   def _parse_error(self, response: httpx.Response) -> str
   ```

2. **Refactor `OpenRouterRealm`** to implement these methods
   - Move SSE parsing to `_parse_sse_line()`
   - Move request building to `_prepare_request()`
   - Keep `_invocations_to_messages()` as protected helper

3. **Add `RealmResponse` factory methods** in `types.py` for consistent creation

4. **Future-proof**: New providers (Anthropic, OpenAI direct) can subclass and only implement the 3 abstract methods

**Priority**: Medium  
**Effort**: Medium (~80 lines across base.py, openrouter.py, types.py)  
**Dependencies**: None (but enables multi-provider support)

---

### PROV-06: 24h Cache TTL May Serve Stale Model Data

**Root Cause**  
`CACHE_TTL_SECONDS = 86400` (model_registry.py:17) = 24 hours. OpenRouter adds/removes models frequently; cache may serve outdated model list (missing new models, showing deprecated ones).

**Files & Lines**
- `mvgeos_provider/model_registry.py:17` — `CACHE_TTL_SECONDS`
- `mvgeos_provider/model_registry.py:61-63` — TTL check in `load_cache()`

**Fix Steps**
1. **Reduce default TTL to 1 hour (3600s)** — balance freshness vs API calls
2. **Make TTL configurable** — add `cache_ttl_seconds` parameter to `ModelRegistry.__init__()`
3. **Add `force_refresh` parameter to `get()` and `list_all()`** for manual invalidation
4. **Add cache metadata** — store `etag`/`last-modified` from OpenRouter response for conditional requests

**Priority**: Low  
**Effort**: Small (~15 lines changed)  
**Dependencies**: None

---

### PROV-07: No HTTP/2 or Connection Pooling

**Root Cause**  
`httpx.AsyncClient` defaults to HTTP/1.1 with no connection pooling limits configured. Each request may open new connection. No `http2=True` enabled.

**Files & Lines**
- `mvgeos_provider/openrouter.py:60-67` — `AsyncClient` creation
- Related to PROV-01 fix location

**Fix Steps**
1. **Enable HTTP/2** in shared client (registry.py):
   ```python
   client = httpx.AsyncClient(http2=True, limits=limits, timeout=timeout)
   ```
2. **Configure connection pool limits** (see PROV-01 fix)
3. **Verify OpenRouter supports HTTP/2** — yes, openrouter.ai supports HTTP/2

**Priority**: Medium  
**Effort**: Small (part of PROV-01 fix, ~5 lines)  
**Dependencies**: PROV-01

---

### PROV-08: `mana_limit` in `ChannelConfig` Ignored by OpenRouter

**Root Cause**  
`ChannelConfig.mana_limit` (types.py:26) is passed to `OpenRouterRealm.stream()` (openrouter.py:74) and used only to cap `max_tokens` (line 86):
```python
if config.mana_limit is not None:
    payload["max_tokens"] = min(config.max_tokens, config.mana_limit)
```
But `mana_limit` represents token budget (mana), not output tokens. OpenRouter doesn't enforce input+output token budget. The provider should track cumulative `mana_used` across stream and stop when limit reached.

**Files & Lines**
- `mvgeos_provider/types.py:26` — `ChannelConfig.mana_limit`
- `mvgeos_provider/openrouter.py:74-86` — `stream()` method
- `mvgeos_provider/types.py:33-37` — `RealmResponse.mana_used`

**Fix Steps**
1. **Track cumulative tokens in `stream()`** (openrouter.py)
   - Initialize `total_tokens = 0`
   - On each chunk: `total_tokens += chunk.usage.total_tokens` (or `completion_tokens`)
   - If `config.mana_limit` and `total_tokens >= config.mana_limit`: break stream, yield final `RealmResponse` with `stop_reason="mana_exhausted"`

2. **Add `stop_reason="mana_exhausted"`** to `RealmResponse` handling in mvgeos-agent loop

3. **Update `ChannelConfig` docstring** to clarify `mana_limit` = total token budget (input + output)

**Priority**: Medium  
**Effort**: Small (~20 lines in openrouter.py)  
**Dependencies**: mvgeos-agent loop.py changes for `mana_exhausted` stop reason

---

### PROV-09: `ContemplationLevel` Not Plumbed to Provider

**Status**: Resolved

**Root Cause**  
`ContemplationLevel` is defined in `mvgeos_agent/types.py` (not in provider). It is stored in `MvgeState.contemplation_level` but `ChannelConfig` had no corresponding field, so it was never forwarded to any provider.

**Fix Applied**
1. Added `contemplation_level: str = "medium"` to `ChannelConfig` in `mvgeos_provider/types.py`
2. Changed `ContemplationLevel.OFF` value from `"off"` to `"none"` to match OpenRouter's `reasoning.effort` enum values directly
3. Changed `MvgeState.contemplation_level` default from `OFF` to `MEDIUM` (reasoning enabled by default)
4. Pass `contemplation_level` from `MvgeState` to `ChannelConfig` in `loop.py`
5. `OpenRouterRealm.stream()` sends `reasoning: { effort: <level> }` to OpenRouter — the `ContemplationLevel` enum values map 1:1 to OpenRouter's `reasoning.effort` parameter

**ContemplationLevel → OpenRouter `reasoning.effort` Mapping**

| ContemplationLevel | OpenRouter `reasoning.effort` |
|---|---|
| `OFF` | `"none"` |
| `MINIMAL` | `"minimal"` |
| `LOW` | `"low"` |
| `MEDIUM` | `"medium"` |
| `HIGH` | `"high"` |
| `XHIGH` | `"xhigh"` |
| `MAX` | `"max"` |

**Files Modified**
- `mvgeos_provider/types.py` — added `contemplation_level` field to `ChannelConfig`
- `mvgeos_agent/types.py` — changed `OFF` value to `"none"`, changed default to `ContemplationLevel.MEDIUM`
- `mvgeos_agent/loop.py` — pass `state.contemplation_level.value` to `ChannelConfig`, default to `"medium"`
- `mvgeos_provider/openrouter.py` — send `reasoning` parameter in payload
- `mvgeos-provider/tests_provider/test_realm.py` — tests for reasoning on/none
- `mvgeos-agent/tests_agent/test_loop.py` — updated `"off"` → `"none"` in test calls
- `mvgeos-agent/tests_agent/test_event_bus.py` — updated `"off"` → `"none"` in test calls

**Priority**: Low  
**Effort**: S (completed)  
**Status**: Done — ContemplationLevel is fully wired through to OpenRouter's `reasoning.effort` parameter

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| PROV-01 | None | PROV-02, PROV-07 |
| PROV-02 | PROV-01 | mvgeos-agent retry handling |
| PROV-08 | None | mvgeos-agent loop.py (mana_exhausted) |
| PROV-09 | mvgeos-agent types | None |

---

## Suggested Implementation Order

1. **PROV-01** (Connection Pooling) — Foundation for PROV-02, PROV-07
2. **PROV-02** (Rate Limiting/Retry) — Critical for production reliability
3. **PROV-03** (Lazy Model Loading) — Memory optimization
4. **PROV-04** (Configurable Models) — Operational flexibility
5. **PROV-08** (Mana Limit Enforcement) — Budget control
6. **PROV-05** (Streaming Abstraction) — Architecture cleanup
7. **PROV-06** (Cache TTL) — Low risk, quick win
8. **PROV-09** (ContemplationLevel) — Verify/cleanup

---

## Testing Requirements

Each fix should include:
- **Unit tests** in `mvgeos-provider/tests/test_<module>.py`
- **Integration test** for PROV-01+PROV-02: mock OpenRouter 429/5xx responses, verify retry/backoff
- **Memory test** for PROV-03: verify only accessed models loaded
- **Config test** for PROV-04: user config overrides hardcoded models

Run with: `uv run pytest mvgeos-provider/tests/ --cov=mvgeos_provider`

---

## File Change Summary

| File | Issues Addressed | Est. Lines Changed |
|------|------------------|-------------------|
| `mvgeos_provider/registry.py` | PROV-01, PROV-07 | ~40 |
| `mvgeos_provider/openrouter.py` | PROV-01, PROV-02, PROV-05, PROV-08 | ~80 |
| `mvgeos_provider/model_registry.py` | PROV-03, PROV-04, PROV-06 | ~50 |
| `mvgeos_provider/models.py` | PROV-04 | ~30 (cleanup) |
| `mvgeos_provider/base.py` | PROV-05 | ~20 |
| `mvgeos_provider/types.py` | PROV-08, PROV-09 | ~10 |
| `mvgeos_provider/retry.py` (new) | PROV-02 | ~60 |
| `mvgeos_provider/__init__.py` | Exports | ~5 |

Total: ~295 lines across 8 files (1 new)