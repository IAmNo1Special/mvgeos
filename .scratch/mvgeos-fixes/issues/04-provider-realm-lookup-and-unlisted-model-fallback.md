# 04 — Prioritize execution realm in provider lookup and add unlisted model fallback

**What to build:** Prioritize `model.realm` over vendor prefix strings (`model.provider`) when matching extension configurations (`apiKey`, `baseUrl`, `headers`), and support fallback composition for unlisted self-hosted models (Ollama, vLLM).

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `compose_model()` and `create_realm()` in `mvgeos_provider/registry.py` check `model.realm` (`openrouter`) before `model.provider` (`nvidia`) when applying extension configuration overrides.
- [ ] Extension settings (`apiKey`, `baseUrl`, `headers`) are correctly applied to slash-prefixed model IDs (e.g. `nvidia/nemotron`).
- [ ] `compose_model()` falls back to dynamic model composition when `get_model(model_id)` returns `None` for a registered provider.
- [ ] Unit and integration tests in `mvgeos-provider/tests/` verify extension provider matching and unlisted model fallbacks.
