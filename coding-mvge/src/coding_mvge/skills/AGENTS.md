# Skills Specification & Authoring Guide

Skills are on-demand workflows, standard operating procedures, and domain knowledge packages defined in Markdown.

## Structure & Conventions
- Each skill lives in its own directory: `skills/<skill-name>/SKILL.md`.
- Must start with strict YAML frontmatter containing `name` and `description`.
- The `description` is indexed into the `<skills>` prompt catalog and acts as the trigger. Write clear trigger conditions explaining *when* to load the skill.

## Example `SKILL.md` Template
```markdown
---
name: my-skill
description: Use this skill when performing specific operations on X or needing guidance for Y.
---

# My Skill Title

## Overview
Detailed instructions for executing this procedure...

## Step-by-Step Instructions
1. First inspect the environment...
2. Run command Z...
```
