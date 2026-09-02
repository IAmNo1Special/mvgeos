# Runes Specification & Authoring Guide

Runes are executable extension packages that add dynamic spells, sidecars, lifecycle hooks, and shortcuts.

## Structure & Conventions
- Each rune lives in its own directory: `runes/<rune-name>/`.
- Must contain a `manifest.json` describing the extension.
- Can declare sigil hooks (`BEFORE_MVGE_START`, `AFTER_SPELL_CAST`, etc.) and registered spells.

## Example `manifest.json` Template
```json
{
  "name": "my-rune",
  "version": "1.0.0",
  "description": "Provides custom integrations and sigil hooks.",
  "author": "Summoner",
  "spells": [],
  "hooks": {
    "BEFORE_MVGE_START": "hooks.py:on_start"
  }
}
```
