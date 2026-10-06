# ADR 0004: OpenRouter as First Provider

## Status

Accepted (amended 2026-10-05: implementation location)

> **Amended 2026-10-05.** The decision — build and validate the Realm
> abstraction against one real provider before adding a second — is what made a
> second Realm cheap, and nothing here is in question. What moved is one fact it
> stated as fixed: where the implementation lives.
>
> - **Implementation location.** "MVP includes only the OpenRouter provider
>   (`OpenRouterRealm`)" described an in-package class. `OpenRouterRealm` ships as
>   the `openrouter-realm` Rune in `mvgeos-marketplace` and registers itself at
>   runtime, so `mvgeos-provider` contains the Realm *protocol* and no concrete
>   Realm. That is the shape the package's own AGENTS.md now documents.
>
> **Which provider is the default is not decided here.** A second Realm's
> plumbing — per-Realm credentials, per-Realm free-suffix scoping, a per-entry
> Realm in the baseline catalog, and one module the registry, CLI and GUI all
> read — landed before any default moved, so a default change is now a
> one-constant edit with the Realm table beside it rather than the refactor that
> default change would otherwise have required. The question of which provider a
> first run reaches for is separate, and is settled on its own evidence.
>
> The claim worth keeping from the original: the decision was made to build the
> abstraction, and the second provider arrived as a consequence rather than a
> goal.

## Context

MvgeOS needs at least one provider (realm) to be functional. OpenRouter provides unified access to 60+ LLM models through a single API. Starting with OpenRouter allows the provider abstraction to be built and validated before expanding.

## Decision

MVP includes only the OpenRouter provider (`OpenRouterRealm`). The `Realm` protocol defines the streaming interface that all providers must implement. The `Model` type holds provider/model identification and configuration. A `models.json` file in the config directory holds the model catalog.

## Consequences

- Single dependency on OpenRouter API for v0.1
- Provider abstraction (Realm protocol) is implemented first, enabling future providers
- Model configuration is externalized to `models.json`
- Authentication via API key stored in `~/.agents/.mvgeos/auth/`
