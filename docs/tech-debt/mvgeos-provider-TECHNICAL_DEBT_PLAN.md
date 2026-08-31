# mvgeos-provider Technical Debt Remediation Plan

Based on analysis of `TECHNICAL_DEBT_BY_PACKAGE.md` and source files in `mvgeos-provider/mvgeos_provider/`.

---

## Issue Index

| ID | Category | Description | Priority | Effort | Dependencies |
|----|----------|-------------|----------|--------|--------------|
| PROV-05 | Architecture | Streaming tightly coupled to OpenRouter SSE format in `openrouter.py` | Medium | M | None |
| PROV-06 | Performance | 24h cache TTL may serve stale model data | Low | S | None |

---

## Detailed Remediation Plans

---

### PROV-05: Streaming Tightly Coupled to OpenRouter SSE Format

**Root Cause**  
`_invocations_to_messages()` (openrouter.py:99-143) and `stream()` parsing logic (openrouter.py:182-266) assume OpenRouter's specific SSE delta format:
- `chunk.choices[0].delta.content`
- `chunk.choices[0].delta.tool_calls`
- `chunk.choices[0].finish_reason`
- `chunk.usage.total_tokens`

The `Realm` base class (`base.py:9-16`) has no streaming parser abstraction — `OpenRouterRealm` implements OpenRouter-specific parsing directly.

**Files & Lines**
- `mvgeos_provider/openrouter.py:99-143` — `_invocations_to_messages()`
- `mvgeos_provider/openrouter.py:337-467` — SSE parsing in `_consume_stream()`
- `mvgeos_provider/base.py:9-16` — `Realm` base class (no streaming abstraction)

**Fix Steps**
1. **Define streaming parser protocol in `base.py`**:
   ```python
   async def _prepare_request(self, model, invocations, config) -> httpx.Request: ...
   def _parse_sse_line(self, line: str) -> RealmResponse | None: ...
   ```

2. **Refactor `OpenRouterRealm`** to implement these methods.

3. **Future-proof**: Alternate provider realms (Anthropic, OpenAI direct) can subclass and implement provider-specific line parsers.

**Priority**: Medium  
**Effort**: Medium (~60 lines across base.py and openrouter.py)  
**Dependencies**: None

---

### PROV-06: 24h Cache TTL May Serve Stale Model Data

**Root Cause**  
`CACHE_TTL_SECONDS = 86400` (`model_registry.py:17`) = 24 hours. OpenRouter adds/removes models frequently; cache may serve outdated model list (missing new models, showing deprecated ones).

**Files & Lines**
- `mvgeos_provider/model_registry.py:17` — `CACHE_TTL_SECONDS`
- `mvgeos_provider/model_registry.py:51-53` — TTL check in `load_cache()`

**Fix Steps**
1. **Make TTL configurable** — add `cache_ttl_seconds: int = 86400` parameter to `ModelRegistry.__init__()`.
2. **Add `force_refresh` parameter to `get()` and `list_all()`** for manual invalidation.
3. **Add CLI command flag** `mvgeos models refresh --force` to bypass TTL.

**Priority**: Low  
**Effort**: Small (~15 lines changed)  
**Dependencies**: None

---

## Cross-Package Dependencies Summary

| Issue | Depends On | Blocks |
|-------|------------|--------|
| PROV-05 | None | Multi-provider expansion |
| PROV-06 | None | CLI model refresh |

---

## Suggested Implementation Order

1. **PROV-06** (Configurable Cache TTL) — Low risk, quick win
2. **PROV-05** (Streaming Abstraction) — Architecture cleanup for future providers

---

## Testing Requirements

- Unit tests in `mvgeos-provider/tests/unit/test_registry.py`
- Verify cache invalidation when TTL expires
- Run with: `uv run python -m pytest mvgeos-provider/tests/ --cov`

