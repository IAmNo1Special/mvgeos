from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Any, cast

from mvgeos_agent.base_mvge import BaseMvge
from mvgeos_agent.prompt_config import load_system_prompt
from mvgeos_agent.spell_schema import generate_spell_schema
from mvgeos_agent.types import MvgeInvocation, MvgeSpell, SpellResult
from mvgeos_runes.types import SigilHook

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
        name: str = "coding-mvge",
        model: str = "nvidia/nemotron-3-ultra-550b-a55b:free",
        spells: list[str] | None = None,
        custom_system_prompt: str = "",
        extension_dir: str | None = None,
        session_dir: Path | None = None,
        session_resume: str | None = None,
        provider_name: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        contemplation_level: str = "medium",
        contemplation_budget: int | None = None,
        exclude_contemplation: bool = False,
    ) -> None:
        super().__init__(
            api_key=api_key,
            name=name,
            model=model,
            extension_dir=extension_dir,
            session_dir=session_dir,
            session_resume=session_resume,
            provider_name=provider_name,
            temperature=temperature,
            max_tokens=max_tokens,
            contemplation_level=contemplation_level,
            contemplation_budget=contemplation_budget,
            exclude_contemplation=exclude_contemplation,
        )
        self._spell_names = spells if spells is not None else list(DEFAULT_SPELL_MAP)
        self._custom_system_prompt = custom_system_prompt

    @property
    def enabled_spells(self) -> list[str]:
        return list(self._spell_names)

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

    async def _build_system_prompt_async(self) -> str:
        # Build base prompt with seeker spell names for display
        seeker_names = ["tool_search", "skill_search", "skill_execute", "mcp_search"]
        base_prompt = load_system_prompt(
            name=self._name,
            custom=self._custom_system_prompt,
            config_dir=self.config_dir,
            spells=seeker_names,
        )

        # Allow runes to inject additional prompt content
        if self._runner is not None:
            prompt_data = {
                "base_prompt": base_prompt,
                "seeker_names": [
                    "tool_search",
                    "skill_search",
                    "skill_execute",
                    "mcp_search",
                ],
                "config_dir": str(self.config_dir) if self.config_dir else "",
                "custom_prompt": self._custom_system_prompt,
                "agent_name": self._name,
                "cwd": str(Path.cwd()),
            }
            prompt_data = await self._runner.emit_chain(
                SigilHook.BEFORE_MVGE_START, prompt_data
            )
            base_prompt = prompt_data.get("base_prompt", base_prompt)

        return f"{base_prompt}\n\nCurrent working directory: {Path.cwd()}"

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
