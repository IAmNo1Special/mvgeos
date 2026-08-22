"""Unit tests for input_dock component."""

from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "mvgeos_gui"


def test_input_dock_renders_mention_chips_exactly_once() -> None:
    """render_input_dock must call _render_mention_chips exactly once.

    Regression test: a duplicate call caused chips to render twice in the
    same card, breaking click-to-remove behavior.
    """
    src = (_PACKAGE_ROOT / "components" / "input_dock.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func_node = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "render_input_dock"
    )
    calls = [
        n
        for n in ast.walk(func_node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_render_mention_chips"
    ]
    assert len(calls) == 1, (
        "_render_mention_chips must be called exactly once in render_input_dock; "
        f"found {len(calls)} call(s)"
    )
