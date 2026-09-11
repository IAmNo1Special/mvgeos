from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from coding_mvge import root_mvge
from mvgeos_agent import Mvge
from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.protocol import AgentFactory, MvgeAgent
from mvgeos_core.constants import DEFAULT_AGENT_NAME

_global_default_factory: AgentFactory | None = None


def validate_api_key(api_key: str, model_id: str | None = None) -> None:
    """Validate API key format. Raises ValueError if invalid."""
    if model_id and model_id.startswith("ollama/"):
        return
    if api_key.startswith("sk-or-") or api_key.startswith("AIza"):
        return
    if model_id and model_id.startswith("google/") and api_key.strip():
        return
    if not api_key:
        raise ValueError("API key is required.")
    raise ValueError(
        "Invalid API key format. OpenRouter keys start with 'sk-or-', "
        "and Google keys start with 'AIza'."
    )


def default_agent_factory(
    *,
    api_key: str = "",
    name: str = DEFAULT_AGENT_NAME,
    custom_system_prompt: str = "",
    extension_dir: str | None = None,
    tome_dir: Path | None = None,
    tome_resume: str | None = None,
    provider_name: str | None = None,
    environment: MvgeEnvironment | None = None,
    strict_resume: bool = False,
    force_fork_resume: bool = False,
    **kwargs: Any,
) -> MvgeAgent:
    """Default agent factory using root_mvge."""
    if (
        tome_resume
        or environment
        or custom_system_prompt
        or extension_dir
        or tome_dir
        or provider_name
        or strict_resume
        or force_fork_resume
    ):
        return Mvge(
            api_key=api_key or None,
            name=name,
            spells=root_mvge._spells,
            custom_system_prompt=custom_system_prompt,
            extension_dir=extension_dir,
            tome_dir=tome_dir,
            tome_resume=tome_resume,
            provider_name=provider_name,
            environment=environment,
            strict_resume=strict_resume,
            force_fork_resume=force_fork_resume,
        )
    return root_mvge


def get_default_agent_factory() -> AgentFactory:
    """Return the currently registered default agent factory."""
    return _global_default_factory or default_agent_factory


def set_default_agent_factory(factory: AgentFactory | None) -> None:
    """Set or reset the global default agent factory."""
    global _global_default_factory
    _global_default_factory = factory


def resolve_agent_factory(agent_factory: AgentFactory | None = None) -> AgentFactory:
    """Resolve an agent factory, falling back to registered default."""
    return agent_factory or get_default_agent_factory()


async def create_agent(
    model: str = "",
    api_key: str = "",
    spells: str | Sequence[str] | None = None,
    extension_dir: str | None = None,
    tome_dir: str | None = None,
    resume: str | None = None,
    provider: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    contemplation: str = "medium",
    agent_name: str = DEFAULT_AGENT_NAME,
    agent_factory: AgentFactory | None = None,
    **kwargs: Any,
) -> MvgeAgent:
    """Resolve environment, create an agent via factory, and initialize it."""
    if api_key or (model and not model.startswith("ollama/")):
        validate_api_key(api_key, model_id=model)
    spells_list: list[str] | None = None
    if isinstance(spells, str):
        spells_list = [s.strip() for s in spells.split(",") if s.strip()]
    elif isinstance(spells, Sequence):
        spells_list = list(spells)

    overrides: dict[str, Any] = {}
    if model:
        overrides["model"] = model
    if temperature is not None:
        overrides["temperature"] = temperature
    if max_tokens is not None:
        overrides["max_tokens"] = max_tokens
    if contemplation:
        overrides["contemplation_level"] = contemplation

    env = MvgeEnvironment.resolve(
        agent_name,
        extension_dir=extension_dir,
        overrides=overrides if overrides else None,
    )
    factory = resolve_agent_factory(agent_factory)
    factory_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "name": agent_name,
        "model": model,
        "extension_dir": extension_dir,
        "tome_dir": Path(tome_dir) if tome_dir else None,
        "tome_resume": resume,
        "provider_name": provider,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "contemplation": contemplation,
        "environment": env,
        **kwargs,
    }
    if spells_list is not None:
        factory_kwargs["spells"] = spells_list

    agent = factory(**factory_kwargs)
    await agent.initialize()
    return agent
