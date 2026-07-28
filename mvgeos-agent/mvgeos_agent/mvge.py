from __future__ import annotations

from typing import Any, Protocol

from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeInvocation,
    MvgeResponse,
    MvgeSpell,
    MvgeState,
    SummonerRequest,
)


class MvgeConfig(Protocol):
    system_prompt: str
    contemplation_level: ContemplationLevel
    mana_budget: int | None


class Mvge:
    def __init__(self, config: MvgeConfig) -> None:
        self._state = MvgeState(
            system_prompt=config.system_prompt,
            contemplation_level=config.contemplation_level,
        )
        self._config = config

    @property
    def state(self) -> MvgeState:
        return self._state

    @property
    def config(self) -> MvgeConfig:
        return self._config

    def get_spells(self) -> list[MvgeSpell]:
        return self._state.spells[:]

    def set_spells(self, spells: list[MvgeSpell]) -> None:
        self._state.spells = spells[:]

    def add_spell(self, spell: MvgeSpell) -> None:
        self._state.spells.append(spell)

    def invoke(self, incantation: str) -> MvgeInvocation:
        invocation = SummonerRequest(
            role="user",
            content=incantation,
            timestamp=0.0,
        )
        self._state.invocations.append(invocation)
        return invocation

    async def respond(self, response: MvgeResponse, stream_fn: Any) -> Any:
        self._state.invocations.append(response)
        return response
