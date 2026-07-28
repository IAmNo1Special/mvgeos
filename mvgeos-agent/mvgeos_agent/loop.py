from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from mvgeos_provider.types import ChannelConfig, Model, RealmResponse

from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    MvgeResponse,
    MvgeState,
    SpellResultMessage,
    StopReason,
    SummonerRequest,
)


def _build_messages(
    system_prompt: str,
    invocations: list[MvgeInvocation],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for inv in invocations:
        if isinstance(inv, SummonerRequest):
            messages.append({"role": inv.role, "content": inv.content})
        elif isinstance(inv, MvgeResponse):
            content = inv.content
            if isinstance(content, list):
                text_parts = [
                    c.get("text", "") for c in content if c.get("type") == "text"
                ]
                tool_calls = [
                    c.get("tool_call") for c in content if c.get("type") == "tool_call"
                ]
                if tool_calls:
                    messages.append(
                        {"role": "assistant", "content": "", "tool_calls": tool_calls}
                    )
                else:
                    messages.append(
                        {"role": "assistant", "content": "".join(text_parts)}
                    )
        elif isinstance(inv, SpellResultMessage):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": inv.spell_cast_id,
                    "content": str(inv.content),
                }
            )
    return messages


class MvgeLoop:
    def __init__(self, state: MvgeState) -> None:
        self._state = state

    @property
    def state(self) -> MvgeState:
        return self._state

    async def run(
        self,
        stream_fn: AsyncIterator[RealmResponse],
        model: dict[str, Any],
        contemplation_level: str = "off",
    ) -> MvgeInvocation:
        self._state.is_streaming = True
        self._state.model = model
        self._state.contemplation_level = ContemplationLevel(contemplation_level)

        try:
            invocation = (
                self._state.invocations[-1] if self._state.invocations else None
            )
            if invocation is None:
                raise RuntimeError("No invocations to process")

            self._emit_event(MvgeEventType.AGENT_START, {"model": model})

            channel_config = ChannelConfig(
                model=Model(
                    id=model.get("id", ""),
                    name=model.get("name", ""),
                    realm=model.get("realm", ""),
                    provider=model.get("provider", ""),
                    base_url=model.get("base_url", ""),
                    api_key=model.get("api_key", ""),
                ),
                temperature=self._state.temperature or 0.7,
                max_tokens=self._state.max_tokens or 4096,
                mana_limit=self._state.mana_budget or 1000,
            )

            _ = _build_messages(self._state.system_prompt, self._state.invocations)
            accumulated_content: list[dict[str, Any]] = []
            tool_calls_pending: dict[str, dict[str, Any]] = {}

            async for response in stream_fn:
                self._handle_realm_response(
                    response, accumulated_content, tool_calls_pending
                )

                if response.invocation is not None:
                    inv: MvgeResponse = response.invocation
                    if inv.stop_reason == StopReason.SPELL_USE and inv.content:
                        for item in inv.content:
                            if item.get("type") == "tool_call":
                                await self._execute_spell(
                                    item["tool_call"], channel_config
                                )

                    if inv.stop_reason in (
                        StopReason.STOP,
                        StopReason.LENGTH,
                        StopReason.ERROR,
                    ):
                        self._state.invocations.append(inv)
                        self._emit_event(MvgeEventType.MESSAGE_END, {"invocation": inv})
                        self._emit_event(
                            MvgeEventType.AGENT_END, {"stop_reason": inv.stop_reason}
                        )
                        return inv

            if self._state.invocations:
                return self._state.invocations[-1]
            # Should not happen since we checked at the start, but mypy needs it
            raise RuntimeError("No invocations to return")

        finally:
            self._state.is_streaming = False

    def _emit_event(self, event_type: MvgeEventType, data: dict[str, Any]) -> None:
        MvgeEvent(type=event_type, data=data)
        # In a real implementation, this would be sent to a callback/stream
        pass

    def _handle_realm_response(
        self,
        response: RealmResponse,
        accumulated_content: list[dict[str, Any]],
        tool_calls_pending: dict[str, dict[str, Any]],
    ) -> None:
        if response.invocation is None:
            return

        inv = response.invocation
        if inv.content:
            for item in inv.content:
                if item.get("type") == "text":
                    accumulated_content.append(item)
                    self._emit_event(
                        MvgeEventType.MESSAGE_UPDATE, {"text": item.get("text", "")}
                    )
                elif item.get("type") == "tool_call":
                    tool_calls_pending[item["tool_call"]["id"]] = item["tool_call"]

    async def _execute_spell(
        self,
        tool_call: dict[str, Any],
        channel_config: ChannelConfig,
    ) -> None:
        spell_name = tool_call["name"]
        spell = next((s for s in self._state.spells if s.name == spell_name), None)
        if spell is None:
            self._emit_event(
                MvgeEventType.SPELL_CASTING_END,
                {
                    "spellCastId": tool_call["id"],
                    "error": f"Spell not found: {spell_name}",
                },
            )
            return

        self._emit_event(
            MvgeEventType.SPELL_CASTING_START,
            {
                "spellCastId": tool_call["id"],
                "spellName": spell_name,
            },
        )

        try:
            result = await spell.execute(
                tool_call["id"],
                tool_call.get("arguments", {}),
            )
            spell_result = SpellResultMessage(
                spell_cast_id=tool_call["id"],
                spell_name=spell_name,
                content=[{"type": "text", "text": str(result)}],
                is_error=False,
            )
            self._state.invocations.append(spell_result)
            self._emit_event(
                MvgeEventType.SPELL_CASTING_END,
                {
                    "spellCastId": tool_call["id"],
                    "result": result,
                },
            )
        except Exception as e:
            spell_result = SpellResultMessage(
                spell_cast_id=tool_call["id"],
                spell_name=spell_name,
                content=[{"type": "text", "text": str(e)}],
                is_error=True,
            )
            self._state.invocations.append(spell_result)
            self._emit_event(
                MvgeEventType.SPELL_CASTING_END,
                {
                    "spellCastId": tool_call["id"],
                    "error": str(e),
                },
            )
