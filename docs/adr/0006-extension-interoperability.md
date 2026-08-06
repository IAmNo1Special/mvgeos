# ADR 0006: Extension Interoperability at Data Level

## Status

Accepted

## Context

MvgeOS mirrors Pi's extension architecture. Pi extensions are TypeScript modules running in Bun/V8. MvgeOS runes are Python modules running in CPython. These runtimes are incompatible for shared executable code.

## Decision

Extension interoperability is achieved at the data/config level, not the runtime level:
- Shared JSON manifest format (`manifest.json`)
- Shared session JSONL format (both read/write the same schema)
- Shared auth.json format (both read the same credentials)
- Shared tool definitions (both use the same JSON schema)

MvgeOS runes are Python modules (`.py` files) loaded dynamically from `.agents/.mvgeos/runes/`. Pi extensions are TypeScript modules loaded by Bun. TUI extensions from Pi cannot run in MvgeOS (different rendering engine).

The rune manifest lives at `.agents/.mvgeos/runes/manifest.json`.

## Consequences

- Both Pi and MvgeOS can use the same extension config files
- A session started in Pi can be resumed in MvgeOS and vice versa
- Auth credentials are shared at rest (same file format)
- No cross-runtime code sharing (TypeScript cannot run in Python and vice versa)
- TUI extensions require separate implementations for each platform