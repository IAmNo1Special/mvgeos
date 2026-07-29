# ADR 0007: ZeroContext as Optional Rune (Not Core)

## Status
Accepted

## Context
ZeroContext provides active capability discovery (search → activate → execute) with ephemeral pruning and budget enforcement. Originally prototyped in WyzvrdOS at `C:\Users\ivmno\Desktop\WyzvrdOS\core\src\wyzvrd_core\zerocontext\`.

## Decision
ZeroContext will be implemented as a **MvgeOS rune/extension**, not core architecture.

- Core mvgeos uses direct tool calling + manifest in system prompt
- ZeroContext rune provides opt-in discovery workflow for agents with 50+ capabilities
- No auto-switching based on capability count

## Consequences

### Positive
- Core stays simple, tested, reliable
- ZeroContext iterates independently
- Agents opt in explicitly (config-driven)
- Removable without breaking changes

### Negative
- Two tool-calling patterns exist in ecosystem
- Documentation must clarify when to use which

## Open Decisions (Track in This ADR)

| # | Decision | Owner | Target |
|---|----------|-------|--------|
| 1 | Finalize `ZEROCONTEXT_DISCOVERY_INSTRUCTION` wording | | v0.1 |
| 2 | Fix pruning key mismatch (`tool_name` vs `spell_name`) | | v0.1 |
| 3 | Replace keyword scoring with [dual-match](https://arxiv.org/abs/2506.01056) (name + desc embeddings) | | v0.2 |
| 4 | Add [DCI-style](https://arxiv.org/abs/2605.05242) `grep`/`read` tools for skill drilling | | v0.2 |
| 5 | Define rune config schema (`capability_threshold`, `core_tools`) | | v0.1 |
| 6 | Write integration tests: rune load → toolset → harness | | v0.1 |

## Rejected Alternatives
- Auto-switch at capability threshold (ADR 0007.1)
- Core built-in with `zerocontext=True` flag (ADR 0007.2)
- Full MCP-Zero embedding-based routing (overkill for mvgeos scale)

## References
- [MCP-Zero: Active Tool Discovery for Autonomous LLM Agents](https://arxiv.org/abs/2506.01056) (arXiv:2506.01056)
- [Beyond Semantic Similarity: Rethinking Retrieval for Agentic Search via Direct Corpus Interaction](https://arxiv.org/abs/2605.05242) (arXiv:2605.05242)
- WyzvrdOS `zerocontext/` implementation at `C:\Users\ivmno\Desktop\WyzvrdOS\core\src\wyzvrd_core\zerocontext\`