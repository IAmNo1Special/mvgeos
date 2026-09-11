from __future__ import annotations

import sys
from pathlib import Path

_UNIT_DIR = str(Path(__file__).parent / "unit")
if _UNIT_DIR not in sys.path:
    sys.path.insert(0, _UNIT_DIR)
