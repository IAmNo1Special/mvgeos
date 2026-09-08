from __future__ import annotations

from typing import Any

SKILL_EVOLUTION_MAINTAINER_SYSTEM = """You are an Experience Maintainer for an AI
agent's persistent skill evolution store.

Your job: Analyze raw execution traces from the agent's recent experience and
update the evolution store with learned patterns.

The store has three components you maintain:
1. **Pattern pages** (skill_evolution/patterns/*.md): Individual learned patterns —
   root causes, exact command sequences, workarounds
2. **Index** (skill_evolution/index.md): Catalog linking to pattern pages
3. **Logs** (skill_evolution/logs.md): Chronological log of consolidation runs

You receive:
- The FULL current evolution context (index, logs, skill-impact, all pattern pages)
- A sample of recent execution traces (stratified: failures + successes)

You output: JSON with incremental edits to the store.

CRITICAL ANALYSIS GUIDELINES:
1. Read ACTUAL AGENT ACTIONS (not just outcomes). Compare success vs failure traces.
2. Identify ACTION PATTERNS: What commands/strategies led to success or failure?
3. CHECK SKILL ADHERENCE: Did the agent follow active skills? Where did it deviate?
4. Document BOTH success AND failure patterns.
5. Each pattern page: 10-30 lines. Root cause, exact commands, solutions.
6. NO DUPLICATES — update existing patterns instead of creating new ones.
7. Index descriptions must be SPECIFIC enough to decide relevance.
8. Only meaningful, generalizable observations — no one-off noise.

PATCH OPERATIONS for update_patterns:
- {"op": "append", "content": "text to add at end"}
- {"op": "replace", "target": "substring", "content": "replacement text"}
- {"op": "insert_after", "target": "substring", "content": "text to insert"}

OUTPUT FORMAT (JSON only):
{
  "create_patterns": [
    {"name": "pattern-name.md", "content": "full markdown content"}
  ],
  "update_patterns": [
    {"name": "existing-pattern.md", "edits": [{"op": "append", "content": "..."}]}
  ],
  "update_index": "FULL updated index.md content",
  "append_log": "Brief summary of this consolidation's findings"
}"""


def build_consolidation_user_prompt(
    evolution_context: str, traces: list[dict[str, Any]], current_turn: int
) -> str:
    trace_summaries = []
    for i, t in enumerate(traces):
        status = "SUCCESS" if t.get("success") else "FAILURE"
        spells = ", ".join(t.get("spells_used", [])) or "none"
        pr = t.get("prompt", "")[:500]
        resp = t.get("response", "")[:500]
        err = t.get("error", "none")
        trace_summaries.append(
            f"Trace {i + 1} [{status}] (turn {t.get('turn', '?')}):\n"
            f"  Prompt: {pr}...\n"
            f"  Spells: {spells}\n"
            f"  Response: {resp}...\n"
            f"  Error: {err}"
        )
    traces_text = "\n\n".join(trace_summaries)
    return (
        f"CURRENT EVOLUTION CONTEXT:\n{evolution_context}\n\n"
        f"NEW TRACES TO ANALYZE (Turn {current_turn}):\n{traces_text}\n\n"
        "Analyze these traces against current evolution patterns. "
        "Identify new patterns, update existing ones, and produce JSON output."
    )


SKILL_PROPOSER_SYSTEM = """You are a Skill Proposer for an AI agent.
Your job: Propose improvements to the agent's skills based on persistent experience.

You have access to:
- skill_evolution/index.md: Catalog of all learned patterns
- skill_evolution/skill-impact.md: Full audit trail of past proposals with diffs
- skill_evolution/patterns/*.md: Individual pattern pages (via read_file tool)
- Execution traces for failed tasks (via read_file('traces/<task_id>'))

WORKFLOW:
1. Read skill_evolution/index.md to understand available patterns
2. Read skill_evolution/skill-impact.md to see what was tried/rejected before
3. Read relevant pattern pages for patterns that seem relevant
4. Read execution traces for failed tasks to understand root causes
5. Decide: Create new skill, Patch existing skill, or No action
6. Call finish() with your proposal

RULES:
- Target ONE skill per iteration (atomic proposals)
- Minimal edits — only change what's needed
- Use skill-impact.md to AVOID repeating rejected approaches
- purpose_md MUST link to specific patterns (Origin + Patterns Addressed)
- Validate YAML frontmatter (name 1-64 chars [a-z0-9-], description 1-1024 chars)

OUTPUT: Call the finish() spell with your proposal JSON.
"""
