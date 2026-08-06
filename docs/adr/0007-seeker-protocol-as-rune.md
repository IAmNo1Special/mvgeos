# ADR 0007: Seeker Protocol as Rune

## Status

Accepted

## Context

The Seeker Protocol provides DCI-based (ripgrep) discovery with NLT (YES/NO grid) selection across three domains: spells (tools), skills (agent instructions), and MCP servers (external capabilities). After 5 rounds of adversarial review, all three architectures are clean — zero CRITICAL/HIGH issues remain.

On-demand search via the three Seekers replaces the need for an active capability set manager with budget enforcement and ephemeral pruning. The agent's own context window serves as the budget.

## Decision

The Seeker Protocol (three `MvgeSpell` subclasses: `ToolSearchSpell`, `SkillSearchSpell`, `MCPSearchSpell`) is packaged as an **external global rune** (`mvgeos-runes-seeker`). Agents find capabilities on demand via the three Seekers rather than pre-loading an active toolset. The rune is installed globally via the rune manifest at `~/.agents/.mvgeos/runes/manifest.json` and loaded by the RuneWatcher at startup.

## Consequences

### Positive

- No budget/pruning infrastructure needed — the agent's context window is the budget
- Three battle-tested architectures with zero CRITICAL/HIGH after adversarial review
- Simpler mental model: "search for what you need, use what you find"

### Negative

- Agents must emit explicit search queries rather than pre-declaring capabilities
- Slightly more tokens per turn for discovery (mitigated by exact-match fast path)

## References

- `docs/architecture/ARCHITECTURE_TOOL_SEARCH.md`
- `docs/architecture/ARCHITECTURE_SKILL_SEARCH.md`
- `docs/architecture/ARCHITECTURE_MCP_SEARCH.md`
