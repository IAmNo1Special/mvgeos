#!/usr/bin/env python3
"""Verify a marketplace checkout only imports API this engine actually provides.

The marketplace clones this repository and imports its internals from
``main``. When ``DEFAULT_TOME_DIR`` was replaced by the ``sessions_dir()``
resolver, ``pi-codec`` and ``session-search`` broke on the marketplace's
``main`` with ten import errors, and nothing here failed: the marketplace
only runs when someone pushes to it.

Two classes of problem are reported, and both fail the check:

``missing``
    The symbol does not exist. The marketplace's collection will break.

``undeclared``
    The symbol exists but is absent from the package's ``__all__``. The
    import works today and can be renamed or removed with no signal here,
    which is how ``selfmod-bridge`` came to depend on ``AuditError``.

Declaration is only meaningful for imports from a package root, since
``__all__`` describes a namespace rather than a submodule.

Usage::

    uv run python mvgeos-core/scripts/check_marketplace_contract.py <path>
"""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
from pathlib import Path

#: Packages this engine publishes. Matched on the first dotted segment so a
#: rune's own package (``mvgeos_runes_pi_codec``) is not mistaken for the
#: engine's (``mvgeos_runes``).
ENGINE_PACKAGES = frozenset(
    {
        "mvgeos_core",
        "mvgeos_agent",
        "mvgeos_provider",
        "mvgeos_runes",
        "mvgeos_tome",
        "mvgeos_cli",
        "mvgeos_gui",
    }
)

_SCAN_DIRS = ("runes", "mvges")


class Violation:
    """One bad import, located in the marketplace source."""

    __slots__ = ("kind", "location", "module", "name")

    def __init__(self, kind: str, location: str, module: str, name: str) -> None:
        self.kind = kind
        self.location = location
        self.module = module
        self.name = name

    def __str__(self) -> str:
        if self.kind == "unimportable":
            return (
                f"{self.location}: {self.module} could not be imported "
                f"({self.name}) -- the marketplace import will fail"
            )
        if self.kind == "missing":
            return (
                f"{self.location}: {self.module} has no '{self.name}' "
                f"-- the marketplace import will fail"
            )
        return (
            f"{self.location}: '{self.name}' is not declared in "
            f"{self.module}.__all__ -- undeclared dependency, can vanish "
            f"without warning"
        )


def _imported_symbols(tree: ast.AST) -> list[tuple[str, list[str], int]]:
    """Return ``(module, names, lineno)`` for every engine import in a module.

    Walks the whole tree rather than only module-level statements, so imports
    inside ``try``/``TYPE_CHECKING`` blocks are covered too: a type-only
    import that no longer resolves still breaks the marketplace's typecheck.
    """
    found: list[tuple[str, list[str], int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level:
            continue
        module = node.module or ""
        if module.split(".", 1)[0] not in ENGINE_PACKAGES:
            continue
        names = [alias.name for alias in node.names if alias.name != "*"]
        if names:
            found.append((module, names, node.lineno))
    return found


def _check_source(path: Path, root: Path) -> list[Violation]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return [Violation("missing", f"{path.relative_to(root)}", "<parse>", str(exc))]

    violations: list[Violation] = []
    for module, names, lineno in _imported_symbols(tree):
        location = f"{path.relative_to(root)}:{lineno}"
        try:
            imported = importlib.import_module(module)
        except ImportError as exc:
            # The module itself is broken, typically because one of its own
            # imports was removed upstream. Report that once, rather than
            # blaming every symbol for a failure they did not cause.
            violations.append(Violation("unimportable", location, module, str(exc)))
            continue
        declared = getattr(imported, "__all__", None)
        is_package_root = module in ENGINE_PACKAGES
        for name in names:
            if not hasattr(imported, name):
                violations.append(Violation("missing", location, module, name))
            elif is_package_root and declared is not None and name not in declared:
                violations.append(Violation("undeclared", location, module, name))
    return violations


def check(marketplace: Path) -> list[Violation]:
    """Return every contract violation found in a marketplace checkout."""
    sources = [
        source
        for directory in _SCAN_DIRS
        for source in sorted((marketplace / directory).rglob("*.py"))
    ]
    if not sources:
        return [
            Violation(
                "missing",
                str(marketplace),
                "<layout>",
                f"no {' or '.join(_SCAN_DIRS)} directory found; is this a "
                f"marketplace checkout?",
            )
        ]
    violations: list[Violation] = []
    for source in sources:
        violations.extend(_check_source(source, marketplace))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("marketplace", type=Path, help="path to a marketplace checkout")
    args = parser.parse_args(argv)

    root = args.marketplace.resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)  # noqa: T201
        return 2

    violations = check(root)
    if not violations:
        print("marketplace contract OK: every engine import resolves and is declared")  # noqa: T201
        return 0

    by_kind: dict[str, list[Violation]] = {}
    for violation in violations:
        by_kind.setdefault(violation.kind, []).append(violation)

    for kind in ("unimportable", "missing", "undeclared"):
        for violation in by_kind.get(kind, []):
            print(f"{kind}: {violation}", file=sys.stderr)  # noqa: T201

    print(  # noqa: T201
        f"\n{len(by_kind.get('unimportable', []))} unimportable, "
        f"{len(by_kind.get('missing', []))} missing, "
        f"{len(by_kind.get('undeclared', []))} undeclared",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
