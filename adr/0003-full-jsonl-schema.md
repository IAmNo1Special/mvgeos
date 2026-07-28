# ADR 0003: Full JSONL Session Schema

## Status

Accepted

## Context

MvgeOS needs session persistence. The .agents protocol and Pi both use JSONL files for session storage. Pi's session JSONL schema defines 12 entry types as a discriminated union: invocation, spellResult, modelChange, contemplationLevelChange, toolCallsChange, label, branchSummary, compaction, custom, customMessage, leaf navigation, and sessionInfo.

## Decision

MvgeOS uses the exact same JSONL session schema as Pi (all 12 entry types). The schema is versioned with a `schema_version` field on each entry (`schema_version: "1.0"`). Session files are stored in `.agents/mvgeos/sessions/` and are file-locked for concurrent access using `filelock`.

An in-memory index (`Index`) at the `TomeLedger` level accelerates querying and persists as `index.json` alongside each JSONL file.

## Consequences

- Session files are portable and readable outside of MvgeOS
- All 12 entry types from Pi's schema are supported from day one
- Schema versioning allows future migration without breaking existing sessions
- File locking prevents data corruption from concurrent access (cross-platform via `filelock`)
- The index.json file provides fast lookup without re-parsing the JSONL