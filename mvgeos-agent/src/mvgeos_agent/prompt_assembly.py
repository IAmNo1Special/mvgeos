"""Standalone prompt assembly for the system prompt pipeline.

Owns every path that turns a Mvge's inputs into its final system prompt:
the ``BEFORE_MVGE_START`` sigil chain (rune prompt injection), skill
catalog attachment, and the shared rendering used by sync callers.

Inputs are deliberately plain values — agent name, config directory,
custom prompt, cwd, and an optional :class:`RuneRunner` — so the module
is testable without constructing a full agent.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import BeforeMvgeStartData, SigilHook

from mvgeos_agent.constants import DEFAULT_AGENT_NAME
from mvgeos_agent.prompt_config import _render_prompt


class PromptAssembly:
    """Assembles the final system prompt from agent inputs and runner sigils."""

    def __init__(
        self,
        *,
        base_prompt: str = "",
        agent_name: str = DEFAULT_AGENT_NAME,
        config_dir: str | Path | None = None,
        custom_prompt: str = "",
        spell_names: Sequence[str] | None = None,
        cwd: str | Path | None = None,
        runner: RuneRunner | None = None,
    ) -> None:
        self._base_prompt = base_prompt
        self._agent_name = agent_name
        self._config_dir = config_dir
        self._custom_prompt = custom_prompt
        self._spell_names = list(spell_names) if spell_names else []
        self._cwd = str(cwd) if cwd else str(Path.cwd())
        self._runner = runner

    async def assemble(self) -> str:
        """Return the final system prompt string.

        With a runner, emits ``BEFORE_MVGE_START`` exactly once so runes can
        rewrite the base prompt, then appends the skill catalog unless a rune
        suppressed it. Without a runner the base prompt passes through
        unchanged.
        """
        base_prompt = self._base_prompt

        if self._runner is not None:
            prompt_data = BeforeMvgeStartData(
                base_prompt=base_prompt,
                spell_names=list(self._spell_names),
                config_dir=self._config_dir_str(),
                custom_prompt=self._custom_prompt,
                agent_name=self._agent_name,
                cwd=self._cwd,
            )
            prompt_data = await self._runner.emit_chain(
                SigilHook.BEFORE_MVGE_START, prompt_data
            )
            base_prompt = str(prompt_data.get("base_prompt", base_prompt))

            if not self._runner.is_skill_catalog_suppressed():
                skill_catalog = self._runner.get_skill_catalog()
                if skill_catalog:
                    base_prompt = f"{base_prompt}\n\n{skill_catalog}"

        return base_prompt

    def render(
        self, body: str, spell_names: Sequence[str], guidelines: Sequence[str]
    ) -> str:
        """Render a prompt with body, spells, guidelines, and environment."""
        return _render_prompt(
            body=body,
            spells=list(spell_names),
            guidelines=list(guidelines),
            cwd=self._cwd,
        )

    def _config_dir_str(self) -> str:
        return str(self._config_dir) if self._config_dir else ""
