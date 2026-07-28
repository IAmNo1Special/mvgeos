from mvgeos_agent.types import (
    MvgeResponse,
    MvgeSpell,
    MvgeState,
    StopReason,
    SummonerRequest,
)


def test_summoner_request_defaults() -> None:
    request = SummonerRequest()
    assert request.role == "user"
    assert request.content is None


def test_mvge_response_defaults() -> None:
    response = MvgeResponse()
    assert response.role == "assistant"
    assert response.content == []
    assert response.stop_reason == StopReason.PENDING


def test_mvge_state_default_spells() -> None:
    state = MvgeState()
    assert state.spells == []


def test_mvge_spell_has_required_fields() -> None:
    spell = MvgeSpell(name="test_spell", description="A test spell", parameters={})
    assert spell.name == "test_spell"
    assert spell.description == "A test spell"
    assert spell.parameters == {}


def test_mvge_spell_execute_raises_not_implemented() -> None:
    import asyncio

    spell = MvgeSpell(name="test_spell", description="A test spell", parameters={})
    try:
        asyncio.run(spell.execute("cast-1", {}))
        raise AssertionError("Expected NotImplementedError")
    except NotImplementedError:
        pass
