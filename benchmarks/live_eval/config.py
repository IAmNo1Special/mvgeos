"""Live evaluation configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvalConfig:
    model_id: str = "poolside/laguna-s-2.1:free"
    provider_name: str | None = "openrouter"
    temperature: float = 0.0
    max_tokens: int = 4096
    contemplation_level: str = "medium"
    max_turns: int = 20
    timeout_seconds: int = 120
    compaction_enabled: bool = False

    @classmethod
    def from_env(cls) -> EvalConfig:
        return cls(
            model_id=os.getenv("MVGEOS_EVAL_MODEL", "poolside/laguna-s-2.1:free"),
            provider_name=os.getenv("MVGEOS_EVAL_PROVIDER", "openrouter"),
            temperature=float(os.getenv("MVGEOS_EVAL_TEMPERATURE", "0.0")),
            max_tokens=int(os.getenv("MVGEOS_EVAL_MAX_TOKENS", "4096")),
            contemplation_level=os.getenv("MVGEOS_EVAL_CONTEMPLATION", "medium"),
            max_turns=int(os.getenv("MVGEOS_EVAL_MAX_TURNS", "20")),
            timeout_seconds=int(os.getenv("MVGEOS_EVAL_TIMEOUT", "120")),
        )

    def api_key(self) -> str:
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            auth_file = Path.home() / ".agents" / "auth" / "openrouter.json"
            if auth_file.exists():
                import json

                with auth_file.open() as f:
                    data = json.load(f)
                    key = data.get("api_key") or data.get("token")
        if not key:
            raise RuntimeError(
                "No OpenRouter API key. Set OPENROUTER_API_KEY env var "
                "or create ~/.agents/auth/openrouter.json with api_key field"
            )
        return key


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    mode: str
    success: bool
    error: str | None
    turns: int
    mana_used: int
    wall_time_seconds: float
    tools_called: list[str]
    tool_call_count: int
    final_output: str
    transcript: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class EvalRun:
    config: EvalConfig
    task_id: str
    baseline: TaskResult
    seeker: TaskResult
    timestamp: str


def load_tasks() -> list[dict[str, Any]]:
    import json
    from typing import cast

    tasks_file = Path(__file__).parent / "tasks.json"
    with tasks_file.open() as f:
        return cast(list[dict[str, Any]], json.load(f))
