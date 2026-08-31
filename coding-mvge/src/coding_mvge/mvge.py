from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from mvgeos_agent.base_mvge import BaseMvge
from mvgeos_agent.constants import DEFAULT_AGENT_NAME
from mvgeos_agent.environment import MvgeEnvironment, PromptSource
from mvgeos_agent.types import MvgeSpell

from coding_mvge.spells import (
    DEFAULT_SPELL_MAP,
    _BuiltinSpell,
    create_builtin_spells,
)

logger = logging.getLogger(__name__)

__all__ = ["CodingMvge", "DEFAULT_SPELL_MAP", "_BuiltinSpell"]


class CodingMvge(BaseMvge):
    def __init__(
        self,
        api_key: str,
        *,
        name: str = DEFAULT_AGENT_NAME,
        spells: list[str] | None = None,
        custom_system_prompt: str = "",
        extension_dir: str | None = None,
        tome_dir: Path | None = None,
        tome_resume: str | None = None,
        provider_name: str | None = None,
        environment: MvgeEnvironment | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            name=name,
            extension_dir=extension_dir,
            tome_dir=tome_dir,
            tome_resume=tome_resume,
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
        # Rune spells are driven entirely by the runner's active-spell set
        # (seeded with all registered rune spells, narrowed/widened by runes
        # via set_active_spells). No rune spell names are hardcoded here.
        rune_spells: list[MvgeSpell] = []
        if self._runner is not None:
            active = set(self._runner.get_active_spells())
            for rs in self._runner.get_all_registered_spells():
                if rs.name in active:
                    rune_spells.append(cast(MvgeSpell, rs))

        # Builtin spells - only if explicitly enabled via self._spell_names
        workspace_root = getattr(self._config_manager, "_project_dir", None)
        timeout_ms = self._state.spell_timeout_ms if self._state is not None else None
        builtin_spells: list[MvgeSpell] = (
            create_builtin_spells(
                self._spell_names,
                workspace_root=workspace_root,
                timeout_ms=timeout_ms,
            )
            if self._spell_names
            else []
        )

        return rune_spells + builtin_spells

    def _render_prompt(
        self, body: str, spell_names: list[str], guidelines: list[str]
    ) -> str:
        """Render prompt with the runner's active rune spell names."""
        active = (
            list(self._runner.get_active_spells()) if self._runner is not None else []
        )
        return super()._render_prompt(body, active, guidelines)
