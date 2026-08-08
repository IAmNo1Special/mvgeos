from __future__ import annotations

import pytest

from mvgeos_agent.compaction import (
    DEFAULT_COMPACTION_SETTINGS,
    SUMMARIZATION_SYSTEM_PROMPT,
    CompactionSettings,
    calculate_context_mana,
    estimate_context_mana,
    estimate_invocation_mana,
    find_cut_point,
    generate_summary,
    prepare_compaction,
    should_compact,
)
from mvgeos_agent.types import (
    MvgeResponse,
    SpellResultMessage,
    StopReason,
    SummonerRequest,
)


class TestCompactionSettings:
    def test_defaults_mirror_pi(self) -> None:
        assert DEFAULT_COMPACTION_SETTINGS.enabled is True
        assert DEFAULT_COMPACTION_SETTINGS.reserve_mana == 16384
        assert DEFAULT_COMPACTION_SETTINGS.keep_recent_mana == 20000


class TestCalculateContextMana:
    def test_prefers_total(self) -> None:
        assert calculate_context_mana({"total": 500, "input": 1, "output": 2}) == 500

    def test_falls_back_to_sum(self) -> None:
        assert calculate_context_mana({"input": 300, "output": 200}) == 500

    def test_empty_usage_is_zero(self) -> None:
        assert calculate_context_mana({}) == 0


class TestShouldCompact:
    def test_false_when_disabled(self) -> None:
        settings = CompactionSettings(enabled=False)
        assert should_compact(999_999, 128_000, settings) is False

    def test_false_below_threshold(self) -> None:
        assert should_compact(1000, 128_000, DEFAULT_COMPACTION_SETTINGS) is False

    def test_true_above_threshold(self) -> None:
        contested = 128_000 - DEFAULT_COMPACTION_SETTINGS.reserve_mana + 1
        assert should_compact(contested, 128_000, DEFAULT_COMPACTION_SETTINGS) is True


class TestEstimateInvocationMana:
    def test_summoner_request_from_text(self) -> None:
        request = SummonerRequest(role="user", content="a" * 40)
        assert estimate_invocation_mana(request) == 10

    def test_mvge_response_counts_text_blocks(self) -> None:
        response = MvgeResponse(
            role="assistant",
            content=[{"type": "text", "text": "b" * 20}],
        )
        assert estimate_invocation_mana(response) == 5

    def test_mvge_response_counts_spell_calls(self) -> None:
        response = MvgeResponse(
            role="assistant",
            content=[
                {
                    "type": "tool_call",
                    "tool_call": {"id": "1", "name": "bash", "arguments": {}},
                }
            ],
        )
        assert estimate_invocation_mana(response) > 0

    def test_spell_result_from_text(self) -> None:
        result = SpellResultMessage(
            spell_cast_id="1",
            spell_name="bash",
            content=[{"type": "text", "text": "c" * 400}],
        )
        assert estimate_invocation_mana(result) == 100


class TestEstimateContextMana:
    def test_uses_last_assistant_usage_when_present(self) -> None:
        invocations = [
            SummonerRequest(role="user", content="hello"),
            MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": "hi"}],
                stop_reason=StopReason.STOP,
                mana_usage={"total": 5000},
            ),
        ]
        estimate = estimate_context_mana(invocations)
        assert estimate.usage_mana == 5000
        assert estimate.last_usage_index == 1
        assert estimate.mana == 5000

    def test_adds_trailing_invocations_after_usage(self) -> None:
        invocations = [
            MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": "hi"}],
                stop_reason=StopReason.STOP,
                mana_usage={"total": 1000},
            ),
            SummonerRequest(role="user", content="d" * 40),
        ]
        estimate = estimate_context_mana(invocations)
        assert estimate.usage_mana == 1000
        assert estimate.trailing_mana == 10
        assert estimate.mana == 1010

    def test_falls_back_to_heuristic_without_usage(self) -> None:
        invocations = [SummonerRequest(role="user", content="e" * 40)]
        estimate = estimate_context_mana(invocations)
        assert estimate.last_usage_index is None
        assert estimate.mana == 10

    def test_ignores_usage_from_errored_response(self) -> None:
        invocations = [
            MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": "boom"}],
                stop_reason=StopReason.ERROR,
                mana_usage={"total": 9999},
            )
        ]
        estimate = estimate_context_mana(invocations)
        assert estimate.last_usage_index is None


class TestFindCutPoint:
    def test_no_candidates_keeps_everything(self) -> None:
        result = find_cut_point([], 0, 0, 20000)
        assert result.first_kept_index == 0
        assert result.is_split_turn is False

    def test_cuts_at_summoner_request_boundary(self) -> None:
        invocations = [
            SummonerRequest(role="user", content="f" * 400),
            MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": "g" * 400}],
                stop_reason=StopReason.STOP,
            ),
            SummonerRequest(role="user", content="h" * 400),
            MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": "i" * 400}],
                stop_reason=StopReason.STOP,
            ),
        ]
        result = find_cut_point(invocations, 0, len(invocations), keep_recent_mana=150)
        assert 0 <= result.first_kept_index < len(invocations)

    def test_never_cuts_before_start(self) -> None:
        invocations = [SummonerRequest(role="user", content="j" * 40)]
        result = find_cut_point(invocations, 0, 1, keep_recent_mana=999_999)
        assert result.first_kept_index == 0

    def test_spell_result_is_not_a_cut_point(self) -> None:
        invocations = [
            SummonerRequest(role="user", content="k" * 40),
            SpellResultMessage(
                spell_cast_id="1",
                spell_name="bash",
                content=[{"type": "text", "text": "l" * 4000}],
            ),
        ]
        result = find_cut_point(invocations, 0, 2, keep_recent_mana=10)
        cut = invocations[result.first_kept_index]
        assert not isinstance(cut, SpellResultMessage)


def _long_transcript() -> list[SummonerRequest | MvgeResponse]:
    invocations: list[SummonerRequest | MvgeResponse] = []
    for index in range(6):
        invocations.append(SummonerRequest(role="user", content=f"ask {index} " * 60))
        invocations.append(
            MvgeResponse(
                role="assistant",
                content=[{"type": "text", "text": f"reply {index} " * 60}],
                stop_reason=StopReason.STOP,
            )
        )
    return invocations


class TestPrepareCompaction:
    def test_returns_none_for_empty_transcript(self) -> None:
        assert prepare_compaction([], DEFAULT_COMPACTION_SETTINGS) is None

    def test_splits_transcript_into_summarize_and_retain(self) -> None:
        invocations = _long_transcript()

        prepared = prepare_compaction(
            invocations, CompactionSettings(keep_recent_mana=100)
        )

        assert prepared is not None
        assert prepared.to_summarize
        assert prepared.retained_tail
        total = len(prepared.to_summarize) + len(prepared.retained_tail)
        assert total == len(invocations)

    def test_records_mana_before(self) -> None:
        invocations = _long_transcript()

        prepared = prepare_compaction(
            invocations, CompactionSettings(keep_recent_mana=100)
        )

        assert prepared is not None
        assert prepared.mana_before > 0

    def test_carries_previous_summary_forward(self) -> None:
        invocations = _long_transcript()

        prepared = prepare_compaction(
            invocations,
            CompactionSettings(keep_recent_mana=100),
            previous_summary="earlier work",
        )

        assert prepared is not None
        assert prepared.previous_summary == "earlier work"

    def test_returns_none_when_nothing_to_summarize(self) -> None:
        invocations = [SummonerRequest(role="user", content="short")]

        prepared = prepare_compaction(
            invocations, CompactionSettings(keep_recent_mana=999_999)
        )

        assert prepared is None


class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_calls_summarize_with_system_prompt(self) -> None:
        captured: dict[str, object] = {}

        async def summarize(messages: list[dict[str, str]]) -> str:
            captured["messages"] = messages
            return "the summary"

        result = await generate_summary(
            [SummonerRequest(role="user", content="hello")], summarize
        )

        assert result == "the summary"
        messages = captured["messages"]
        assert isinstance(messages, list)
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SUMMARIZATION_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_includes_transcript_text(self) -> None:
        captured: dict[str, object] = {}

        async def summarize(messages: list[dict[str, str]]) -> str:
            captured["messages"] = messages
            return "s"

        await generate_summary(
            [SummonerRequest(role="user", content="find the bug")], summarize
        )

        messages = captured["messages"]
        assert isinstance(messages, list)
        joined = " ".join(m["content"] for m in messages)
        assert "find the bug" in joined

    @pytest.mark.asyncio
    async def test_previous_summary_switches_to_update_prompt(self) -> None:
        captured: dict[str, object] = {}

        async def summarize(messages: list[dict[str, str]]) -> str:
            captured["messages"] = messages
            return "s"

        await generate_summary(
            [SummonerRequest(role="user", content="more work")],
            summarize,
            previous_summary="what came before",
        )

        messages = captured["messages"]
        assert isinstance(messages, list)
        joined = " ".join(m["content"] for m in messages)
        assert "what came before" in joined

    @pytest.mark.asyncio
    async def test_returns_none_when_summarize_fails(self) -> None:
        async def summarize(messages: list[dict[str, str]]) -> str:
            raise RuntimeError("realm exploded")

        result = await generate_summary(
            [SummonerRequest(role="user", content="hello")], summarize
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_blank_summary(self) -> None:
        async def summarize(messages: list[dict[str, str]]) -> str:
            return "   "

        result = await generate_summary(
            [SummonerRequest(role="user", content="hello")], summarize
        )

        assert result is None
