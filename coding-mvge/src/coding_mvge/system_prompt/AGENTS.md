# System Prompt Specification

Layer 1 persona instructions and behavioral guidelines are defined in plain Markdown files in this directory.

## Structure
- `SYSTEM.md`: Contains the agent's core identity, persona instructions, behavioral guidelines, and tool expectations.
- `APPEND_SYSTEM.md` (optional): Contains additional additive system prompt instructions appended to the base persona.

## Conventions
- Repository operational rules belong in the repository's `AGENTS.md` per the `.agents` protocol.
- Invariant operational scaffolding (active spells, OS/environment details, PowerShell syntax, `<project_context>`, and self-modification pointers) is dynamically rendered by the engine at runtime and should not be duplicated here.

