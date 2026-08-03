# ADR 0002: dotagents Protocol Compliance

## Status

Accepted

## Context

MvgeOS needs a configuration directory convention. The .agents Protocol (dotagentsprotocol.com) defines an open directory convention for AI agent configuration. It mandates a `.agents/` directory with a two-layer system (global `~/.agents/` and workspace `./.agents/`).

## Decision

MvgeOS adheres to the `.agents/` directory name per the dotagents protocol. MvgeOS-specific data is namespaced under `.agents/.mvgeos/`:

- `.agents/.mvgeos/extensions/manifest.json` — Extension registry
- `.agents/.mvgeos/sessions/` — Tome (session) JSONL files
- `.agents/.mvgeos/auth/` — Relics (API keys, credentials)
- `.agents/.mvgeos/models.json` — Model configuration

## Consequences

- Configuration is portable across tools that support the .agents protocol
- The `.agents/` directory is committed to the repository (workspace layer)
- MvgeOS-specific files are isolated under the `mvgeos/` subdirectory
- Other tools reading `.agents/` can discover MvgeOS config in the conventional location