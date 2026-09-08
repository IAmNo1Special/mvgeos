- Target ONE skill per iteration (atomic proposals)
- Minimal edits — only change what is needed
- Use skill-impact.md to avoid repeating rejected approaches
- purpose_md MUST link to specific patterns (Origin + Patterns Addressed)
- When to Apply / When NOT to Apply must be precise
- Skill names must be 1-64 characters matching ^[a-z0-9]+(-[a-z0-9]+)*$

## Scope Boundary Rules
1. **Project Scope (`project`)**:
   - Location: `.agents/skills/<name>/`
   - Focus: Repository-specific idioms, local build scripts, monorepo paths, and project test setups.
   - MUST NOT strip or generalize away project-critical constraints.
2. **Agent Scope (`agent`)**:
   - Location: `~/.agents/.mvgeos/{agent}/skills/<name>/`
   - Focus: Cross-project agent reasoning, spell sequencing heuristics, and general persona strategies.
   - STRICTLY FORBIDDEN: Hardcoded repo paths, project-specific credentials, branch names, or one-off framework configs.
3. **User Scope (`user`)**:
   - Location: `~/.agents/skills/<name>/`
   - Focus: Universal tool and language specifications usable across any agent and any project.
   - **Project Specialization**: If a learned insight on a user-scoped skill is project-specific, DO NOT mutate the machine-wide user skill. Instead, set `"fork_to_project": true` or `"scope": "project"` in your proposal so the skill is specialized under `.agents/skills/` (Project Scope), overriding user scope for this project only.
