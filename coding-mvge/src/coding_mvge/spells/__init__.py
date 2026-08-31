from typing import Any

from coding_mvge.spells.bash import cast_bash
from coding_mvge.spells.edit import cast_edit
from coding_mvge.spells.find import cast_find
from coding_mvge.spells.grep import cast_grep
from coding_mvge.spells.list import cast_list
from coding_mvge.spells.read import cast_read
from coding_mvge.spells.write import cast_write

BUILTIN_SPELL_MAP: dict[str, Any] = {
    "bash": cast_bash,
    "read": cast_read,
    "write": cast_write,
    "edit": cast_edit,
    "find": cast_find,
    "list": cast_list,
    "grep": cast_grep,
}

__all__ = [
    "BUILTIN_SPELL_MAP",
    "cast_bash",
    "cast_edit",
    "cast_find",
    "cast_grep",
    "cast_list",
    "cast_read",
    "cast_write",
]
