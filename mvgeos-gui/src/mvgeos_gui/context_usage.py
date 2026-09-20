"""Context window usage accounting: real provider tokens vs a verified window.

The gauge shows BOTH the percentage and the raw token counts, e.g.
``38% · 76,204 / 200,000 tokens``. A gauge is only built when two things are
true at once:

1. The provider reported real token usage (input/output tokens from the
   latest provider response). No usage, no gauge -- never estimated.
2. The selected model resolves to a registry entry with a verified context
   window. The registry silently substitutes 4096 when an entry has no
   ``context_length``, so exactly 4096 is treated as "unknown" rather than
   displayed as fact.

Reasoning/contemplation tokens are already inside completion tokens and are
never added again: used = input + output.

This module is UI-free on purpose: agent_service records usage from engine
events, and the components package renders it. Keeping the pure logic here
avoids a circular import (state -> agent_service -> components package).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mvgeos_gui.state import AppState


@dataclass(frozen=True)
class ContextGauge:
    """Snapshot of context window consumption."""

    used_tokens: int
    window_tokens: int

    @property
    def used_ratio(self) -> float:
        return self.used_tokens / self.window_tokens

    def format(self) -> str:
        percent = round(self.used_ratio * 100)
        return f"{percent}% · {self.used_tokens:,} / {self.window_tokens:,} tokens"


def extract_token_usage(response: Any) -> tuple[int, int] | None:
    """Pull (input, output) token counts off a provider RealmResponse.

    Returns None when the provider reported no real usage.
    """
    invocation = getattr(response, "invocation", None)
    mana_usage = getattr(invocation, "mana_usage", None) or {}
    if not isinstance(mana_usage, dict):
        return None
    try:
        input_tokens = int(mana_usage.get("input", 0))
        output_tokens = int(mana_usage.get("output", 0))
    except (TypeError, ValueError):
        return None
    if input_tokens <= 0 and output_tokens <= 0:
        return None
    return (input_tokens, output_tokens)


def build_context_gauge(state: AppState) -> ContextGauge | None:
    """Build the gauge, or None when usage or a verified window is missing."""
    if state.context_input_tokens is None or state.context_output_tokens is None:
        return None
    window = state.get_verified_context_window()
    if window is None:
        return None
    used = state.context_input_tokens + state.context_output_tokens
    return ContextGauge(used_tokens=used, window_tokens=window)
