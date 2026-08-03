from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from mvgeos_provider.types import ChannelConfig, Model, RealmResponse
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import SigilHook, SpellDefinition

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.errors import (
    AuthenticationError,
    MvgeError,
    RateLimitError,
    SpellNotFoundError,
    SpellTimeoutError,
    to_error,
)
from mvgeos_agent.types import (
    ContemplationLevel,
    ContentType,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    MvgeResponse,
    MvgeSpell,
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
                    c.get("text", "")
                    for c in content
                    if c.get("type") == ContentType.TEXT
                ]
                tool_calls = [
                    c.get("tool_call")
                    for c in content
                    if c.get("type") == ContentType.TOOL_CALL
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


def _get_rune_runner(state: MvgeState) -> RuneRunner | None:
    runner = state.rune_runner
    if runner is None:
        return None
    return runner


def _get_agent_session(state: MvgeState) -> MvgeTome | None:
    session = state.agent_session
    if session is None:
        return None
    return session


async def _safe_emit(
    runner: RuneRunner | None,
    hook: SigilHook,
    data: Any,
) -> None:
    if runner is None:
        return
    await runner.emit_async(hook, data)


async def _safe_emit_chain(
    runner: RuneRunner | None,
    hook: SigilHook,
    initial: Any,
) -> Any:
    if runner is None:
        return initial
    try:
        return await runner.emit_chain(hook, initial)
    except Exception:
        return initial


async def _safe_emit_block(
    runner: RuneRunner | None,
    hook: SigilHook,
    data: Any,
) -> dict[str, Any] | None:
    if runner is None:
        return None
    try:
        return await runner.emit_block(hook, data)
    except Exception:
        return None


def _safe_record_message(
    agent_session: MvgeTome | None,
    role: str,
    content: Any,
    model: str | None = None,
    provider: str | None = None,
) -> None:
    if agent_session is None:
        return
    agent_session.record_message(
        role=role,
        content=content,
        model=model,
        provider=provider,
    )


class _RuneSpellWrapper(MvgeSpell):
    def __init__(self, spell_def: SpellDefinition) -> None:
        super().__init__(
            name=spell_def.name,
            description=spell_def.description,
            parameters=spell_def.parameters,
        )
        self._spell_def = spell_def

    async def execute(
        self,
        spell_cast_id: str,
        params: dict[str, Any],
        signal: Any | None = None,
        on_update: Any | None = None,
    ) -> dict[str, Any]:
        return await self._spell_def.execute(spell_cast_id, params, signal, on_update)


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
        contemplation_level: str = "medium",
    ) -> MvgeInvocation:
        self._state.is_streaming = True
        self._state.model = model
        self._state.contemplation_level = ContemplationLevel(contemplation_level)
        runner = _get_rune_runner(self._state)
        agent_session = _get_agent_session(self._state)

        try:
            invocation = (
                self._state.invocations[-1] if self._state.invocations else None
            )
            if invocation is None:
                raise RuntimeError("No invocations to process")

            self._emit_event(MvgeEventType.AGENT_START, {"model": model})
            await _safe_emit(runner, SigilHook.AGENT_START, {"model": model})

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
                mana_limit=self._state.mana_budget,
                contemplation_level=self._state.contemplation_level.value,
                contemplation_budget=self._state.contemplation_budget,
                exclude_contemplation=self._state.exclude_contemplation,
            )

            transformed_invocations = await _safe_emit_chain(
                runner, SigilHook.CONTEXT_TRANSFORM, self._state.invocations
            )
            if transformed_invocations is not None:
                self._state.invocations = transformed_invocations

            initial_invocation = next(
                (
                    inv
                    for inv in self._state.invocations
                    if isinstance(inv, SummonerRequest)
                ),
                None,
            )
            if initial_invocation:
                await _safe_emit(
                    runner, SigilHook.INPUT, {"content": initial_invocation.content}
                )
                _safe_record_message(
                    agent_session,
                    role="user",
                    content=initial_invocation.content,
                )

            _ = _build_messages(self._state.system_prompt, self._state.invocations)
            accumulated_content: list[dict[str, Any]] = []
            tool_calls_pending: dict[str, dict[str, Any]] = {}

            provider_headers = await _safe_emit_chain(
                runner, SigilHook.BEFORE_PROVIDER_HEADERS, {}
            )
            if provider_headers and isinstance(provider_headers, dict):
                merged_headers = {**model.get("headers", {}), **provider_headers}
                model = {**model, "headers": merged_headers}
                self._state.model = model

            await _safe_emit(
                runner, SigilHook.BEFORE_PROVIDER_REQUEST, {"model": model}
            )

            await _safe_emit(runner, SigilHook.TURN_START, {"model": model})

            async for response in stream_fn:
                if response.error_message:
                    error_code = getattr(response, "error_code", None)
                    if error_code == "rate_limited":
                        raise RateLimitError(response.error_message)
                    if error_code == "auth_failed":
                        raise AuthenticationError(response.error_message)
                    raise RuntimeError(response.error_message)

                # Track mana usage and check budget
                self._state.mana_used += response.mana_used
                budget = self._state.mana_budget
                used = self._state.mana_used
                if budget is not None and used >= budget:
                    self._emit_event(
                        MvgeEventType.TURN_END,
                        {
                            "reason": "mana_exhausted",
                            "mana_used": used,
                            "mana_budget": budget,
                        },
                    )
                    return MvgeResponse(
                        role="assistant",
                        content=[
                            {
                                "type": "text",
                                "text": f"Mana budget exhausted: {used}/{budget}",
                            }
                        ],
                        stop_reason=StopReason.MANA_EXHAUSTED,
                        mana_usage={"total": used},
                    )

                await _safe_emit(
                    runner,
                    SigilHook.AFTER_PROVIDER_RESPONSE,
                    {"response": response},
                )

                self._handle_realm_response(
                    response, accumulated_content, tool_calls_pending
                )

                if response.invocation is not None:
                    inv: MvgeResponse = response.invocation
                    await _safe_emit(
                        runner,
                        SigilHook.BEFORE_INVOCATION,
                        {"invocation": inv},
                    )

                    if inv.stop_reason == StopReason.SPELL_USE and inv.content:
                        for item in inv.content:
                            if item.get("type") == "tool_call":
                                block_result = await _safe_emit_block(
                                    runner,
                                    SigilHook.BEFORE_SPELL_CAST,
                                    {
                                        "tool_call": item["tool_call"],
                                        "spell_name": item["tool_call"]["name"],
                                    },
                                )
                                if not block_result:
                                    await self._execute_spell(
                                        item["tool_call"],
                                        channel_config,
                                        runner,
                                        agent_session,
                                    )

                    await _safe_emit(
                        runner,
                        SigilHook.AFTER_INVOCATION,
                        {"invocation": inv, "stop_reason": inv.stop_reason},
                    )

                    if inv.stop_reason in (
                        StopReason.STOP,
                        StopReason.LENGTH,
                        StopReason.ERROR,
                        StopReason.SPELL_USE,
                    ):
                        self._state.invocations.append(inv)
                        self._emit_event(MvgeEventType.MESSAGE_END, {"invocation": inv})
                        _safe_record_message(
                            agent_session,
                            role="assistant",
                            content=inv.content,
                            model=model.get("id", ""),
                            provider=model.get("provider", ""),
                        )
                        await _safe_emit(
                            runner,
                            SigilHook.TURN_END,
                            {"stop_reason": inv.stop_reason},
                        )
                        if inv.stop_reason != StopReason.SPELL_USE:
                            await _safe_emit(
                                runner,
                                SigilHook.AGENT_END,
                                {
                                    "stop_reason": inv.stop_reason,
                                    "invocation": inv,
                                },
                            )
                            self._emit_event(
                                MvgeEventType.AGENT_END,
                                {"stop_reason": inv.stop_reason},
                            )
                            return inv

            await _safe_emit(runner, SigilHook.TURN_END, {"reason": "exhausted"})

            if self._state.invocations:
                return self._state.invocations[-1]
            raise RuntimeError("No invocations to return")

        finally:
            self._state.is_streaming = False

    def _emit_event(self, event_type: MvgeEventType, data: dict[str, Any]) -> None:
        event = MvgeEvent(type=event_type, data=data)
        if len(self._state.events) >= self._state.max_events:
            self._state.events = self._state.events[-self._state.max_events // 2 :]
        self._state.events.append(event)
        bus = self._state.event_bus
        if bus is not None:
            bus.emit(event_type, data)

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
                if item.get("type") == ContentType.TEXT:
                    accumulated_content.append(item)
                    self._emit_event(
                        MvgeEventType.MESSAGE_UPDATE, {"text": item.get("text", "")}
                    )
                elif item.get("type") == ContentType.TOOL_CALL:
                    tool_calls_pending[item["tool_call"]["id"]] = item["tool_call"]

    async def _execute_spell(
        self,
        tool_call: dict[str, Any],
        channel_config: ChannelConfig,
        runner: RuneRunner | None = None,
        agent_session: MvgeTome | None = None,
    ) -> None:
        spell_name = tool_call["name"]
        spell = next((s for s in self._state.spells if s.name == spell_name), None)
        if spell is None and runner is not None:
            rune_spells = runner.get_all_registered_spells()
            rune_spell = next((rs for rs in rune_spells if rs.name == spell_name), None)
            if rune_spell is not None:
                spell = _RuneSpellWrapper(rune_spell)

        if spell is None:
            err: MvgeError = SpellNotFoundError(spell_name)
            self._emit_event(
                MvgeEventType.SPELL_CASTING_END,
                {
                    "spellCastId": tool_call["id"],
                    "error": err.code,
                    "message": str(err),
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
            timeout_s = self._state.spell_timeout_ms / 1000
            result = await asyncio.wait_for(
                spell.execute(
                    tool_call["id"],
                    tool_call.get("arguments", {}),
                ),
                timeout=timeout_s,
            )
            result_content = result
            chain_result = await _safe_emit_chain(
                runner,
                SigilHook.AFTER_SPELL_RESULT,
                {
                    "spell_name": spell_name,
                    "spell_cast_id": tool_call["id"],
                    "result": result,
                },
            )
            if chain_result is not None and isinstance(chain_result, dict):
                result_content = chain_result.get("result", result)

            spell_result = SpellResultMessage(
                spell_cast_id=tool_call["id"],
                spell_name=spell_name,
                content=[{"type": "text", "text": str(result_content)}],
                is_error=False,
            )
            self._state.invocations.append(spell_result)
            self._emit_event(
                MvgeEventType.SPELL_CASTING_END,
                {
                    "spellCastId": tool_call["id"],
                    "result": result_content,
                },
            )
            _safe_record_message(
                agent_session,
                role="tool",
                content=str(result_content),
            )
        except TimeoutError:
            err = SpellTimeoutError(spell_name, self._state.spell_timeout_ms)
            spell_result = SpellResultMessage(
                spell_cast_id=tool_call["id"],
                spell_name=spell_name,
                content=[{"type": "text", "text": str(err)}],
                is_error=True,
            )
            self._state.invocations.append(spell_result)
            self._emit_event(
                MvgeEventType.SPELL_CASTING_END,
                {
                    "spellCastId": tool_call["id"],
                    "error": str(err),
                },
            )
            _safe_record_message(
                agent_session,
                role="tool",
                content=str(err),
            )
        except Exception as e:
            err = to_error(e)
            spell_result = SpellResultMessage(
                spell_cast_id=tool_call["id"],
                spell_name=spell_name,
                content=[{"type": "text", "text": str(err)}],
                is_error=True,
            )
            self._state.invocations.append(spell_result)
            self._emit_event(
                MvgeEventType.SPELL_CASTING_END,
                {
                    "spellCastId": tool_call["id"],
                    "error": str(err),
                },
            )
            _safe_record_message(
                agent_session,
                role="tool",
                content=str(err),
            )
