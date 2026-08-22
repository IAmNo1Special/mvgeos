from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Model:
    id: str
    name: str
    realm: str
    base_url: str
    api_key: str
    max_completion_mana: int = 0
    context_window: int = 128000
    max_tokens: int = 4096
    headers: dict[str, str] = field(default_factory=dict)
    supported_parameters: list[str] = field(default_factory=list)
    is_free: bool = False

    @property
    def free(self) -> bool:
        """Return True if the model is free of charge."""
        return self.is_free or self.id.endswith(":free") or self.id == "openrouter/free"

    @property
    def provider(self) -> str:
        """The organization that provides this model (derived from the model ID)."""
        return self.id.split("/")[0] if "/" in self.id else self.realm


@dataclass
class ChannelConfig:
    model: Model
    temperature: float = 0.7
    max_tokens: int = 4096
    max_output_mana: int | None = None
    timeout_ms: int = 60000
    max_retries: int = 3
    contemplation_level: str = "medium"
    contemplation_budget: int | None = None
    exclude_contemplation: bool = False
    tools: list[dict[str, Any]] = field(default_factory=list)
    meta_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RealmResponse:
    model: Model
    invocation: Any | None = None
    mana_used: int = 0
    stop_reason: str = "stop"
    error_message: str | None = None
    error_code: str | None = None
