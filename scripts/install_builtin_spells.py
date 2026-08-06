#!/usr/bin/env python
"""Install builtin spells as discoverable global spells.

Generates MvgeSpell subclass files from coding_mvge builtin spells
and installs them to ~/.agents/.mvgeos/spells/builtin/
"""
from __future__ import annotations

from pathlib import Path

from coding_mvge.spells import (
    cast_bash,
    cast_edit,
    cast_find,
    cast_grep,
    cast_list,
    cast_read,
    cast_write,
)
from mvgeos_agent.spell_schema import generate_spell_schema

BUILTIN_SPELLS = {
    "bash": cast_bash,
    "read": cast_read,
    "write": cast_write,
    "edit": cast_edit,
    "find": cast_find,
    "list": cast_list,
    "grep": cast_grep,
}

SPELL_TEMPLATE = '''from __future__ import annotations

from mvgeos_agent.types import MvgeSpell, SpellExecutionMode


class {class_name}(MvgeSpell):
    """Builtin {name} spell - auto-generated from coding_mvge."""
    name = "{name}"
    description = "{description}"
    parameters = {parameters}
    execution_mode = SpellExecutionMode.SEQUENTIAL

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        # Delegate to the actual builtin implementation
        from coding_mvge.spells import {func_name}
        from mvgeos_agent.types import SpellResult

        validated = self.prepare_arguments(params)
        args = {{k: v for k, v in validated.items() if v is not None}}
        result: SpellResult = await {func_name}(**args)
        if result.error_message:
            return {{"error": result.error_message}}
        return {{"content": result.content or f"{{self.name}} completed"}}

'''

DESCRIPTIONS = {
    "bash": "Execute bash commands in the workspace",
    "read": "Read file contents",
    "write": "Write content to a file",
    "edit": "Edit file contents with find/replace",
    "find": "Find files matching a pattern",
    "list": "List directory contents",
    "grep": "Search file contents with regex",
}


def generate_spell_file(name: str, func) -> str:
    """Generate spell file content from builtin function."""
    class_name = "".join(word.capitalize() for word in name.split("_")) + "Spell"
    schema = generate_spell_schema(func)
    func_name = f"cast_{name}"

    return SPELL_TEMPLATE.format(
        class_name=class_name,
        name=name,
        description=DESCRIPTIONS.get(name, f"Builtin {name} spell"),
        parameters=schema,
        func_name=func_name,
    )


def install_builtin_spells(target_dir: Path | None = None) -> None:
    """Install builtin spells as discoverable global spells."""
    if target_dir is None:
        target_dir = Path.home() / ".agents" / ".mvgeos" / "spells" / "builtin"

    target_dir.mkdir(parents=True, exist_ok=True)

    # Remove old builtin spells
    for old_file in target_dir.glob("*_spell.py"):
        old_file.unlink()

    # Generate new spell files
    for name, func in BUILTIN_SPELLS.items():
        content = generate_spell_file(name, func)
        file_path = target_dir / f"{name}_spell.py"
        file_path.write_text(content, encoding="utf-8")
        print(f"Generated: {file_path}")

    # Create __init__.py
    init_content = "# Builtin spells package\n"
    (target_dir / "__init__.py").write_text(init_content, encoding="utf-8")
    print(f"Generated: {target_dir / '__init__.py'}")

    print(f"\nInstalled {len(BUILTIN_SPELLS)} builtin spells to {target_dir}")
    print("Run 'mvgeos tool_search' to discover them.")


if __name__ == "__main__":
    install_builtin_spells()
