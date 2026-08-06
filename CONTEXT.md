# MvgeOS

MvgeOS is an operating system for AI agents: a Mvge (agent) casts Spells (tools) against models served by Realms (model providers), conversations persist as Tomes, and capabilities extend through Runes.

## Language

**Mvge** (pronounced "Mage"):
An autonomous agent that acts on behalf of a Summoner by casting Spells against models served by Realms.
_Avoid_: Agent (as a spoken term), assistant, bot

**Spell**:
A tool a Mvge can cast during a run.
_Avoid_: Tool (as a spoken term), function, action

**Realm**:
A model provider — a service that serves models to Mvges. OpenRouter is a Realm that routes requests onward to many upstream providers. For a direct Realm (e.g., Google), the Realm and the upstream provider are the same organization; the distinction only matters for router Realms.
_Avoid_: Backend, endpoint

**Provider** (plain English):
The organization that provides a model (e.g., Google, Anthropic, NVIDIA). Derived from the model-ID prefix (`google/gemini...` → provider = "google"). Not a stored field on `Model` — computed from the ID.
_Avoid_: Realm (do not conflate with the abstraction)

**Mana**:
Tokens — the unit in which model usage is measured and budgeted.
_Avoid_: Tokens (as a spoken term), credits, units

**Mana Pool**:
The model's context window — the maximum number of Mana (tokens) that fit in a single request context. Renamed from `context_window` in code.
_Avoid_: Context window (as a spoken term)

**Mana Budget**:
The cap on total Mana the Mvge can spend during a single run. Renamed from `mana_budget` in code.

**Tome**:
A single persisted conversation between a Summoner and a Mvge, recorded as an append-only sequence of Invocations. The on-disk format is a tree of entries (Pi-compatible JSONL v3).
_Avoid_: Session (except inside the Pi-compatible JSONL wire format), conversation, chat

**Invocation**:
Any single message in a Tome's transcript — a SummonerRequest, an MvgeResponse, or a SpellResultMessage.
_Avoid_: Message (as a spoken term), turn, event

**Leaf**:
The active position marker in a Tome — an explicit entry pointing to the current tip of a conversation branch. The "current position" is the entry the Leaf points to.
_Avoid_: Head, cursor, pointer

**Fork**:
A new Tome created by branching from an entry in a parent Tome. The child Tome's header stores a reference to the parent Tome (`parentSession`). The branch path (ancestors up to the chosen entry) is copied into the child.
_Avoid_: Branch (as a noun — the branch is implicit in the tree; Fork is the action and result)

**Summoner**:
The user on whose behalf a Mvge acts. A SummonerRequest is the Summoner's input to a run.
_Avoid_: User (as a spoken term), human, operator

**Rune**:
An extension: a packaged unit that hooks into a Mvge's lifecycle and can register Spells, commands, shortcuts, and Realms. Runes are user-installed (not built-in) and live in `~/.agents/.mvgeos/runes/`.
_Avoid_: Extension (as a spoken term), plugin, addon

**Seeker**:
A Rune (not built-in) that routes tool/skill/MCP discovery through meta-tools (`tool_search`, `skill_search`, `mcp_search`, `skill_execute`) instead of loading them directly into context. By default (like Pi), capabilities are loaded directly into the Mvge's context window at session start; the Seeker Rune is a user-installed download that changes this behavior to on-demand discovery.
_Avoid_: Discovery (as a spoken term)

**Skill**:
A capability pack discovered and loaded per the agentskills.io specification: a directory containing `SKILL.md` with YAML frontmatter (name, description) and markdown instructions. Skills are distinct from Spells — a Skill may yield Spell-like executions via `skill_execute` but is never loaded wholesale; it is disclosed progressively (catalog → full instructions → resources).
_Avoid_: Tool, Spell, plugin

**Channeling**:
Streaming a response from a Realm — the act of receiving tokens incrementally. The protocol method is `channel()` (formerly `stream()`); the renderer is `ChannelRenderer`.
_Avoid_: Streaming, stream (as a spoken term)

**Sigil**:
A callback a Rune registers on a lifecycle hook. The hook points themselves are `SigilHook` enum values (e.g., `BEFORE_SPELL_CAST`, `AFTER_PROVIDER_RESPONSE`).
_Avoid_: Callback (as a spoken term), hook (for the callback — the hook is the lifecycle point)

**Contemplation**:
The depth of reasoning the Mvge applies during a run, requested by the Summoner (or set by the Mvge's defaults) and conveyed to the Realm as reasoning effort. Optionally capped by a reasoning Mana budget (`contemplation_budget`).
_Avoid_: Reasoning (as a spoken term), thinking (for the concept)