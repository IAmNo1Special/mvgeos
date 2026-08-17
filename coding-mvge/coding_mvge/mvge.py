from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import Any, cast

from mvgeos_agent.base_mvge import BaseMvge
from mvgeos_agent.constants import DEFAULT_AGENT_NAME
from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.prompt_loader import PromptSource
from mvgeos_agent.spell_schema import generate_spell_schema
from mvgeos_agent.types import MvgeSpell, SpellResult

from coding_mvge.spells import (
    BUILTIN_SPELL_MAP as DEFAULT_SPELL_MAP,
)

logger = logging.getLogger(__name__)


class _BuiltinSpell(MvgeSpell):
    def __init__(
        self,
        name: str,
        func: Any,
        workspace_root: Path | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        super().__init__(
            name=name,
            description=f"Run the {name} tool.",
            parameters=generate_spell_schema(func),
        )
        self._func = func
        self._workspace_root = workspace_root
        self._timeout_ms = timeout_ms

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> str:
        if signal is not None and getattr(signal, "aborted", False):
            from mvgeos_agent.types import AbortError

            raise AbortError("Operation aborted")
        validated = self.prepare_arguments(params)
        args = {k: v for k, v in validated.items() if v is not None}
        sig = inspect.signature(self._func)
        if self._workspace_root is not None and "workspace_root" in sig.parameters:
            args["workspace_root"] = self._workspace_root
        if (
            self._timeout_ms is not None
            and "timeout_ms" in sig.parameters
            and "timeout_ms" not in args
        ):
            args["timeout_ms"] = self._timeout_ms

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
        # such as the Seeker Rune via set_active_spells). No rune spell names
        # are hardcoded here.
        rune_spells: list[MvgeSpell] = []
        if self._runner is not None:
            active = set(self._runner.get_active_spells())
            for rs in self._runner.get_all_registered_spells():
                if rs.name in active:
                    rune_spells.append(cast(MvgeSpell, rs))

        # Builtin spells - only if explicitly enabled via self._spell_names
        builtin_spells: list[MvgeSpell] = []
        workspace_root = getattr(self._config_manager, "_project_dir", None)
        timeout_ms = self._state.spell_timeout_ms if self._state is not None else None
        if self._spell_names:
            for name in self._spell_names:
                if name in DEFAULT_SPELL_MAP:
                    builtin_spells.append(
                        _BuiltinSpell(
                            name,
                            DEFAULT_SPELL_MAP[name],
                            workspace_root=workspace_root,
                            timeout_ms=timeout_ms,
                        )
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
