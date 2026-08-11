from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Any, cast

from mvgeos_agent.base_mvge import BaseMvge
from mvgeos_agent.constants import DEFAULT_AGENT_NAME
from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.prompt_loader import PromptSource
from mvgeos_agent.spell_schema import generate_spell_schema
from mvgeos_agent.types import MvgeInvocation, MvgeSpell, SpellResult

from coding_mvge.spells import (
    cast_bash,
    cast_edit,
    cast_find,
    cast_grep,
    cast_list,
    cast_read,
    cast_write,
)

logger = logging.getLogger(__name__)


DEFAULT_SPELL_MAP: dict[str, Any] = {
    "bash": cast_bash,
    "read": cast_read,
    "write": cast_write,
    "edit": cast_edit,
    "find": cast_find,
    "list": cast_list,
    "grep": cast_grep,
}


class _BuiltinSpell(MvgeSpell):
    def __init__(self, name: str, func: Any) -> None:
        super().__init__(
            name=name,
            description=f"Run the {name} tool.",
            parameters=generate_spell_schema(func),
        )
        self._func = func

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> str:
        validated = self.prepare_arguments(params)
        args = {k: v for k, v in validated.items() if v is not None}
        result: SpellResult = await self._func(**args)
        if result.error_message:
            return f"[error] {result.error_message}"
        return result.content or f"{self.name} completed"


class CodingMvge(BaseMvge):
    def __init__(
        self,
        api_key: str,
        *,
        name: str = DEFAULT_AGENT_NAME,
        spells: list[str] | None = None,
        custom_system_prompt: str = "",
        extension_dir: str | None = None,
        session_dir: Path | None = None,
        session_resume: str | None = None,
        provider_name: str | None = None,
        environment: MvgeEnvironment | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            name=name,
            extension_dir=extension_dir,
            session_dir=session_dir,
            session_resume=session_resume,
            provider_name=provider_name,
            environment=environment,
        )
        # Use spells from config if not explicitly provided, otherwise
        # default to all builtin spells
        if spells is not None:
            self._spell_names = spells
        elif self._spell_names is None:
            self._spell_names = list(DEFAULT_SPELL_MAP.keys())
        self._custom_system_prompt = custom_system_prompt
        self._prompt_source = PromptSource.BUILTIN

    @property
    def enabled_spells(self) -> list[str]:
        return list(self._spell_names or [])

    def _build_spells(self) -> list[MvgeSpell]:
        # Seekers (meta-tools) - always included
        seeker_spells: list[MvgeSpell] = []
        if self._runner is not None:
            for rs in self._runner.get_all_registered_spells():
                if rs.name in (
                    "tool_search",
                    "skill_search",
                    "skill_execute",
                    "mcp_search",
                ):
                    seeker_spells.append(cast(MvgeSpell, rs))

        # Rune spells (non-seeker) - all other rune-registered spells
        rune_spells: list[MvgeSpell] = []
        if self._runner is not None:
            for rs in self._runner.get_all_registered_spells():
                if rs.name not in (
                    "tool_search",
                    "skill_search",
                    "skill_execute",
                    "mcp_search",
                ):
                    rune_spells.append(cast(MvgeSpell, rs))

        # Builtin spells - only if explicitly enabled via self._spell_names
        builtin_spells: list[MvgeSpell] = []
        if self._spell_names:
            for name in self._spell_names:
                if name in DEFAULT_SPELL_MAP:
                    builtin_spells.append(_BuiltinSpell(name, DEFAULT_SPELL_MAP[name]))

        return seeker_spells + rune_spells + builtin_spells

    def _render_prompt(
        self, body: str, spell_names: list[str], guidelines: list[str]
    ) -> str:
        """Render prompt with only seeker spell names."""
        seeker_names = ["tool_search", "skill_search", "skill_execute", "mcp_search"]
        return super()._render_prompt(body, seeker_names, guidelines)

    async def _run_impl(self) -> MvgeInvocation:
        assert self._model is not None
        assert self._realm is not None
        assert self._state is not None
        assert self._loop is not None

        # The loop owns the turn cycle, including max_turns and draining the
        # steer/followup queues, so this is a single call.
        stream_fn = self._make_stream_fn(
            self._model,
            self._realm,
            self._state,
            self._temperature,
            self._max_tokens,
        )

        return await self._loop.run(
            stream_fn,
            model=dataclasses.asdict(self._model),
            contemplation_level=self._contemplation_level,
        )
