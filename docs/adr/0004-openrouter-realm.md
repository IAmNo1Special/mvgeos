# ADR 0004: OpenRouter as First Provider

## Status

Accepted

## Context

MvgeOS needs at least one provider (realm) to be functional. OpenRouter provides unified access to 60+ LLM models through a single API. Starting with OpenRouter allows the provider abstraction to be built and validated before expanding.

## Decision

MVP includes only the OpenRouter provider (`OpenRouterRealm`). The `Realm` protocol defines the streaming interface that all providers must implement. The `Model` type holds provider/model identification and configuration. A `models.json` file in the config directory holds the model catalog.

## Consequences

- Single dependency on OpenRouter API for v0.1
- Provider abstraction (Realm protocol) is implemented first, enabling future providers
- Model configuration is externalized to `models.json`
- Authentication via Arcane Key (API key) stored in `.agents/.mvgeos/auth/`