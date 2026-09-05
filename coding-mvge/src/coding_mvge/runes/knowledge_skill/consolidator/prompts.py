from __future__ import annotations

from typing import Any

KNOWLEDGE_MAINTAINER_SYSTEM = """You are a Knowledge Maintainer for an AI agent's
persistent knowledge base.

Your job: Analyze raw execution traces from the agent's recent experience and
update the knowledge with learned patterns.

The knowledge has three components you maintain:
1. **Pattern pages** (knowledge/patterns/*.md): Individual learned patterns —
   root causes, exact command sequences, workarounds
2. **Index** (knowledge/index.md): Catalog linking to pattern pages
3. **Logs** (knowledge/logs.md): Chronological log of consolidation runs

You receive:
- The FULL current knowledge context (index, logs, skill-impact, all pattern pages)
- A sample of recent execution traces (stratified: failures + successes)

You output: JSON with incremental edits to the knowledge.

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

WIKI_MAINTAINER_SYSTEM = KNOWLEDGE_MAINTAINER_SYSTEM


def build_consolidation_user_prompt(
    wiki_context: str, traces: list[dict[str, Any]], current_turn: int
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
        f"CURRENT KNOWLEDGE CONTEXT:\n{wiki_context}\n\n"
        f"NEW TRACES TO ANALYZE (Turn {current_turn}):\n{traces_text}\n\n"
        "Analyze these traces against current knowledge. "
        "Identify new patterns, update existing ones, and produce JSON output."
    )


SKILL_PROPOSER_SYSTEM = """You are a Skill Proposer for an AI agent.
Your job: Propose improvements to the agent's skills based on persistent knowledge.

You have access to:
- knowledge/index.md: Catalog of all learned patterns
- knowledge/skill-impact.md: Full audit trail of past proposals with diffs
- knowledge/patterns/*.md: Individual pattern pages (via read_file tool)
- Execution traces for failed tasks (via read_file('traces/<task_id>'))

WORKFLOW:
1. Read knowledge/index.md to understand available patterns
2. Read knowledge/skill-impact.md to see what was tried/rejected before
3. Read relevant pattern pages for patterns that seem relevant
4. Read execution traces for failed tasks to understand root causes
5. Decide: Create new skill, Patch existing skill, or No action
6. Call finish() with your proposal

RULES:
- Target ONE skill per iteration (atomic proposals)
- Minimal edits — only change what's needed
- Use skill-impact.md to AVOID repeating rejected approaches
- purpose_md MUST link to specific knowledge patterns (Origin + Patterns Addressed)
- When to Apply / When NOT to Apply must be precise

PROPOSAL FORMATS:

Create new skill:
{
  "action": "create",
  "name": "skill-directory-name",
  "skill_md": "full SKILL.md (frontmatter + When to Apply + Instructions)",
  "purpose_md": "full PURPOSE.md with Origin + Patterns + History"
}

Patch existing skill:
{
  "action": "patch",
  "name": "existing-skill-name",
  "edits": [
    {"op": "append", "content": "text to add"},
    {"op": "replace", "target": "exact substring", "content": "replacement"},
    {"op": "insert_after", "target": "exact substring", "content": "text to insert"}
  ]
}

No action:
{"action": "no_action"}"""


def build_proposer_initial_context(
    wiki_index: str, skill_impact: str, training_summary: str
) -> str:
    return (
        f"KNOWLEDGE INDEX:\n{wiki_index}\n\n"
        f"SKILL IMPACT AUDIT TRAIL:\n{skill_impact}\n\n"
        f"TRAINING TASK OUTCOMES SUMMARY:\n{training_summary}\n\n"
        "Begin by reading the knowledge index and skill impact trail. "
        "Then read relevant pattern pages and failed traces as needed."
    )


SKILL_MD_TEMPLATE = """---
name: {skill_name}
description: {description}
---

# {skill_name}

## When to Apply
{when_to_apply}

## When NOT to Apply
{when_not_to_apply}

## Instructions
{instructions}
"""

PURPOSE_MD_TEMPLATE = """# Purpose: {skill_name}

## Origin
{origin}

## Patterns Addressed
{patterns_addressed}

## Evolution History
- v1.0.0: Initial creation based on knowledge patterns: {pattern_refs}
"""
