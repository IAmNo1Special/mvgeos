"""Unit tests for the context window gauge (real usage vs verified window)."""

from __future__ import annotations

import pytest
from mvgeos_core.channel import Model, MvgeResponse, RealmResponse
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.components.context_gauge import (
    build_context_gauge,
    render_context_gauge,
)
from mvgeos_gui.components.status_bar import render_status_bar
from mvgeos_gui.context_usage import ContextGauge, extract_token_usage
from mvgeos_gui.state import AppState

MALCOM_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"


def _realm_response(mana_usage: dict[str, float]) -> RealmResponse:
    model = Model(
        id="test/model",
        name="Test",
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="<redacted>",
    )
    return RealmResponse(
        model=model,
        invocation=MvgeResponse(mana_usage=mana_usage),
    )


def test_extract_token_usage_reads_mana_breakdown() -> None:
    """Provider usage arrives as the mana breakdown; reasoning stays inside output."""
    resp = _realm_response(
        {"input": 44.0, "output": 1048.0, "total": 1092.0, "contemplation": 898.0}
    )
    # 44 + 1048 = 1092: reasoning tokens are already inside completion.
    assert extract_token_usage(resp) == (44, 1048)


def test_extract_token_usage_none_when_missing() -> None:
    assert extract_token_usage(_realm_response({})) is None
    assert extract_token_usage(RealmResponse(model=_realm_response({}).model)) is None
    assert extract_token_usage(None) is None
    assert extract_token_usage("not-a-response") is None


def test_gauge_format_shows_percent_and_raw_counts() -> None:
    gauge = ContextGauge(used_tokens=76204, window_tokens=200000)
    assert gauge.format() == "38% · 76,204 / 200,000 tokens"


def test_build_gauge_none_without_usage() -> None:
    state = AppState()
    state.selected_model = MALCOM_MODEL
    assert build_context_gauge(state) is None


def test_build_gauge_none_without_registry_entry() -> None:
    state = AppState()
    state.selected_model = "nope/not-a-model"
    state.context_input_tokens = 100
    state.context_output_tokens = 50
    assert build_context_gauge(state) is None


def test_genuine_small_window_models_still_verify() -> None:
    """4095-window entries are genuine (from models.json), not the 4096 fallback.

    This pins why the unverified rule is `== 4096` and not `<= 4096`: the
    registry's silent fallback is exactly 4096 (see model_registry.py), while
    real small-window models carry their true value.
    """
    state = AppState()
    state.selected_model = "openai/gpt-3.5-turbo-0613"
    assert state.get_verified_context_window() == 4095

    state.context_input_tokens = 100
    state.context_output_tokens = 50
    gauge = build_context_gauge(state)
    assert gauge is not None
    assert gauge.window_tokens == 4095


def test_build_gauge_uses_verified_window() -> None:
    state = AppState()
    state.selected_model = MALCOM_MODEL
    state.context_input_tokens = 76204
    state.context_output_tokens = 1000
    gauge = build_context_gauge(state)
    assert gauge is not None
    assert gauge.window_tokens == 1_000_000
    assert gauge.used_tokens == 77204
    assert gauge.format() == "8% · 77,204 / 1,000,000 tokens"


def test_record_and_reset_context_usage() -> None:
    state = AppState()
    state.record_context_usage(44, 1048)
    assert (state.context_input_tokens, state.context_output_tokens) == (44, 1048)
    state.new_conversation()
    assert state.context_input_tokens is None
    assert state.context_output_tokens is None


@pytest.mark.asyncio
async def test_status_bar_hides_gauge_without_usage(user: User) -> None:
    """No usage yet: the gauge renders nothing, not a 0% placeholder."""
    state = AppState()
    state.selected_model = MALCOM_MODEL

    @ui.page("/test_gauge_hidden")
    def page() -> None:
        render_status_bar(state)

    await user.open("/test_gauge_hidden")
    with pytest.raises(AssertionError):
        user.find(marker="context_gauge")


@pytest.mark.asyncio
async def test_status_bar_shows_gauge_with_usage(user: User) -> None:
    state = AppState()
    state.selected_model = MALCOM_MODEL
    state.record_context_usage(76204, 1000)

    @ui.page("/test_gauge_shown")
    def page() -> None:
        render_status_bar(state)

    await user.open("/test_gauge_shown")
    await user.should_see("8% · 77,204 / 1,000,000 tokens")


@pytest.mark.asyncio
async def test_render_context_gauge_renders_nothing_when_hidden(user: User) -> None:
    state = AppState()
    state.selected_model = MALCOM_MODEL

    @ui.page("/test_gauge_render_hidden")
    def page() -> None:
        render_context_gauge(state)

    await user.open("/test_gauge_render_hidden")
    with pytest.raises(AssertionError):
        user.find(marker="context_gauge")
