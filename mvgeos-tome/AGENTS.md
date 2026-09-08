# mvgeos-Tome — Agent Instructions

This package implements Tome persistence: JSONL session storage with file locking and in-memory indexing. A Tome is a tree of conversation entries stored in a single Pi-compatible JSONL file.

## Package-Specific Conventions

- All code follows the red-green-refactor TDD cycle: write failing test first, then implement
- No inline imports (`await import()`, `import("pkg").Type`). Top-level imports only
- Use `pathlib.Path` for all file path operations — never raw string concatenation
- Mock sync methods with `MagicMock()`, async methods with `AsyncMock()` — mixing causes "coroutine never awaited" warnings

## Testing

```bash
# Run this package's tests
uv run python -m pytest mvgeos-tome/tests

# Run with coverage
uv run python -m pytest mvgeos-tome/tests --cov
```

Test paths follow pattern: `mvgeos-tome/tests/unit/<module>.py` and `mvgeos-tome/tests/integration/<module>.py`

## Key Types

| Type | Purpose |
| --- | --- |
| `TomeLedger` | Create/open/fork tomes; append entries; rewrite JSONL per write |
| `TomeEntry` | Single entry in a Tome (id, parent_id, type, timestamp, payload) |
| `TomeEntryType` | Enum of entry types (MESSAGE, LABEL, COMPACTION, CUSTOM, LEAF, TOME_INFO) |
| `TomeMetadata` | Tome header (id, created_at, cwd, parent_tome_id, active_leaf_id) |
| `FileLock` | filelock wrapper (sync+async context manager) |

## TomeEntryType Values

| Value | Purpose |
| --- | --- |
| `MESSAGE` | User, assistant, and tool messages |
| `LABEL` | Label/tag on an entry |
| `COMPACTION` | Context compaction summary |
| `CUSTOM` | Arbitrary extension/sigil data |
| `LEAF` | Active position marker (current tip of a conversation branch) |
| `TOME_INFO` | Tome metadata (name, etc.) |

## Entry Type Naming

- `TOME_INFO` (not `SESSION_INFO`) — aligns with MvgeOS "Tome" terminology

## Dependencies

- `filelock` — cross-platform file locking

## Architecture

- One `{tome_id}.jsonl` per Tome in a tome directory
- Line 1 = header `{"type":"session","version":3,"id","timestamp","cwd","parentSession"?,"activeLeafId"?}`
- Subsequent lines = entries `{"id","parentId","type","timestamp","payload"}`
- Every mutation rewrites the entire JSONL file under a `FileLock`
- The `Index` provides in-memory lookup by id, by parent, and leaf entries
- Forking creates a new Tome by copying the ancestor chain up to a chosen entry
