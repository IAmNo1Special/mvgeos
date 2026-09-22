"""Unit tests for the ``python -m mvgeos_gui`` entry point."""

from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import patch

import mvgeos_gui


def test_main_module_calls_main() -> None:
    """Running the package as __main__ delegates to main()."""
    main_py = Path(mvgeos_gui.__file__).parent / "__main__.py"
    with patch("mvgeos_gui.main.main") as mock_main:
        runpy.run_path(str(main_py), run_name="__main__")
    mock_main.assert_called_once_with()
