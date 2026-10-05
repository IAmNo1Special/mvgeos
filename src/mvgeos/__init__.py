"""The `mvgeos` distribution -- the one name behind `uvx mvgeos`.

The CLI implementation lives in `mvgeos_cli`; this module is what the root
distribution ships so the published `mvgeos` name resolves `uvx mvgeos`
straight to the same entry point `mvgeos-cli` installs. Both console
scripts run identical code, so the `mvgeos` command behaves the same
whichever distribution an installer wrote it from.
"""

from __future__ import annotations

from mvgeos_cli.main import main

__all__ = ["main"]
