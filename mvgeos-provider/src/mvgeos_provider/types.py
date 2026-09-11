"""Deprecated compatibility facade over :mod:`mvgeos_core`.

Canonical definitions live in :mod:`mvgeos_core.abort` and
:mod:`mvgeos_core.channel`. Third-party runes importing this module keep
working, but new code must import from ``mvgeos_core`` directly.
"""

from __future__ import annotations

from mvgeos_core.abort import (
    AbortController as AbortController,
)
from mvgeos_core.abort import (
    AbortError as AbortError,
)
from mvgeos_core.abort import (
    AbortSignal as AbortSignal,
)
from mvgeos_core.channel import (
    ChannelConfig as ChannelConfig,
)
from mvgeos_core.channel import (
    Model as Model,
)
from mvgeos_core.channel import (
    MvgeResponse as MvgeResponse,
)
from mvgeos_core.channel import (
    RealmResponse as RealmResponse,
)
from mvgeos_core.channel import (
    StopReason as StopReason,
)

__all__ = [
    "AbortController",
    "AbortError",
    "AbortSignal",
    "ChannelConfig",
    "Model",
    "MvgeResponse",
    "RealmResponse",
    "StopReason",
]
