"""Protocol-facing constants for the ``.agents`` layer scheme.

Four names, all of them contract: the ones that describe the ``.agents``
layer scheme itself. Nothing here *derives* a path -- resolution lives in
:mod:`mvgeos_core.layers`, which is the single place a search path comes
from.

``GLOBAL_DIR_ENV`` and ``PROJECT_RUNE_PATH`` are the protocol-facing names
and must not be renamed; ``Scope`` lives with the ranking rule it feeds, in
``layers``. A feature-scoped environment variable -- the CLI's
``MVGEOS_EXTENSION_DIR``, say -- belongs to the feature that reads it, not
here: this module is the layer scheme, not every literal in the engine.

See ADR-0014.
"""

from __future__ import annotations

DEFAULT_AGENT_NAME = "default-mvge"

#: System-wide default Realm model. ``openrouter/free`` is OpenRouter's Free
#: Models Router: it only ever routes to a free endpoint and picks a different
#: one when one saturates. A concrete free slug cannot do that -- it just moves
#: the outage to whichever endpoint is saturated next. Kept free by
#: construction; never point this at a paid id.
DEFAULT_MODEL = "openrouter/free"

#: Environment variable that relocates the global ``.agents`` layer. The
#: default is ``~/.agents``; setting this moves every global-layer read and
#: write, which is what makes an isolated run possible. Honoured by every
#: resolver in :mod:`mvgeos_core.layers`, on every call.
GLOBAL_DIR_ENV = "MVGEOS_GLOBAL_DIR"

#: Project-layer rune directory, relative to an anchored project directory.
#: Always the standard protocol name -- never a proprietary subdirectory.
PROJECT_RUNE_PATH = ".agents/extensions"
