# ADR 0007: Unified Tome Session System on Pi-Compatible JSONL Format

## Status

Accepted

## Context

MvgeOS had two parallel session systems:

- `SessionManager` — Pi-compatible single JSONL per session, no MvgeOS features (branching, locking, indexing)
- `TomeLedger` — Custom format (`entries/{id}.jsonl` + `index.json` + `.meta.json`), full MvgeOS features

This created confusion, dual storage (`sessions/*.jsonl` + `sessions/entries/*.jsonl`), and maintenance burden.

## Decision

Unify on a single `TomeLedger` using Pi's session JSONL format:

- One `{tome_id}.jsonl` file per tome in `.agents/.mvgeos/sessions/`
- Header line: `{"type": "session", "version": 3, "id": "...", "timestamp": "...", "cwd": "...", "parentSession": "...", "activeLeafId": "..."}`
- Entry lines: Pi's 12 entry types (invocation, spellResult, modelChange, etc.)
- File locking via `filelock` for concurrency
- In-memory `Index` rebuilt on startup from JSONL files
- No `entries/` subdirectory, no `index.json`
- `SessionManager` class removed; CLI uses MvgeOS terminology (`tome`, `fork`, etc.)

## Consequences

- Pi session files work natively — users can resume Pi sessions in MvgeOS
- Single source of truth for session storage
- All MvgeOS features preserved (branching/forking, metadata, leaf tracking)
- Simplified codebase (~300 lines removed from `session.py`)
- CLI commands use consistent MvgeOS terminology: `mvgeos tome list|show|create|fork|export`
