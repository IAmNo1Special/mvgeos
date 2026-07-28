from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Model:
    id: str
    name: str
    realm: str
    provider: str
    base_url: str
    api_key: str
    mana_limit: int = 0
    context_window: int = 128000
    max_tokens: int = 4096
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class ChannelConfig:
    model: Model
    temperature: float = 0.7
    max_tokens: int = 4096
    mana_limit: int | None = None
    timeout_ms: int = 60000
    max_retries: int = 3
    meta_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RealmResponse:
    model: Model
    invocation: Any | None = None
    mana_used: int = 0
    stop_reason: str = "stop"
    error_message: str | None = None
