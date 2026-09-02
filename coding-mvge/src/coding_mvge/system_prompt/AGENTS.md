# System Prompt & Guidelines Specification

Layer 1 persona instructions and behavioral guidelines are defined in plain Markdown files in this directory.

## Structure
- `SYSTEM.md`: Contains the agent's core identity, mission, and tool expectations.
- `GUIDELINES.md`: Contains bulleted behavioral guidelines and execution rules.

## Conventions
- Guidelines should be bulleted lists (starting with `-` or `*`).
- Invariant operational scaffolding (active spells, OS/environment details, PowerShell syntax, `<project_context>`, and self-modification pointers) is dynamically rendered by the engine at runtime and should not be duplicated here.
