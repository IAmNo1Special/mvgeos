from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mvgeos_core.channel import MvgeResponse
from mvgeos_core.spells import SpellResultMessage


@dataclass
class SummonerRequest:
    role: str = "user"
    content: str | list[dict[str, Any]] | None = None
    timestamp: float = 0.0


MvgeInvocation = SummonerRequest | MvgeResponse | SpellResultMessage


__all__ = [
    "MvgeInvocation",
    "SummonerRequest",
]
