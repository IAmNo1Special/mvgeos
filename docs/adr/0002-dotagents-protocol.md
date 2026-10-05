# ADR 0002: dotagents Protocol Compliance

## Status

Superseded by [ADR 0014](0014-one-resolved-layer-stack.md)

> **Superseded 2026-10-04.** The `.agents` directory decision below still holds
> and is still correct. The *directory scheme* does not: no `.agents/.mvgeos/`
> subdirectory exists in any `src/` today, and ADR-0014 replaces it with standard
> protocol names (`sessions/`, `agents/`, `extensions/`, `auth/`,
> `models.json`) resolved through a single module. This ADR also predates
> `MVGEOS_GLOBAL_DIR`, which relocates the whole global layer.
>
> Read this ADR for the *why* of adopting `.agents/`. Read
> [ADR 0014](0014-one-resolved-layer-stack.md) for the *what* and *where*.

## Context

MvgeOS needs a configuration directory convention. The .agents Protocol (dotagentsprotocol.com) defines an open directory convention for AI agent configuration. It mandates a `.agents/` directory with a two-layer system (global `~/.agents/` and workspace `./.agents/`).

## Decision

MvgeOS adheres to the `.agents/` directory name per the dotagents protocol. MvgeOS-specific data is namespaced under `.agents/.mvgeos/`:

- `.agents/.mvgeos/runes/manifest.json` — Rune registry
- `.agents/.mvgeos/tomes/` — Tome JSONL files
- `.agents/.mvgeos/auth/` — API keys and credentials
- `.agents/.mvgeos/models.json` — Model configuration

## Consequences

- Configuration is portable across tools that support the .agents protocol
- The `.agents/` directory is committed to the repository (workspace layer)
- MvgeOS-specific files are isolated under the `mvgeos/` subdirectory
- Other tools reading `.agents/` can discover MvgeOS config in the conventional location
