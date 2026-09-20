"""Unit tests for the Approval Rune GUI presenter."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from mvgeos_core.approval import (
    ApprovalOutcome,
    ApprovalReasonCode,
    ApprovalRequest,
    ApprovalScope,
)

from mvgeos_gui.approval.presenter import (
    ApprovalPresenter,
    bind_approval_presenter,
    unbind_approval_presenter,
)
from mvgeos_gui.approval.types import PermissionsView
from mvgeos_gui.state import AppState


def _make_state() -> AppState:
    state = AppState()
    state.project_path = Path("/proj/a")
    return state


def _make_request(cast_id: str = "call_1") -> ApprovalRequest:
    return ApprovalRequest(
        cast_id=cast_id,
        spell_name="write",
        spell_identity={
            "name": "write",
            "source_kind": "builtin",
            "source_id": "",
            "runner_origin": "false",
            "read_only": "false",
        },
        arguments={"path": "/proj/a/out.txt"},
        argument_digest="sha256:args",
        project_root="/proj/a",
        tome_id="",
        agent_name="coding_mvge",
    )


async def _answer_allow(state: AppState) -> None:
    """Let the presenter enqueue, then answer allow-once from the queue."""
    await asyncio.sleep(0)
    assert state.approval_active_request is not None
    state.resolve_active_approval(
        ApprovalOutcome.ALLOW, ApprovalScope.ONCE, ApprovalReasonCode.USER
    )


@pytest.mark.asyncio
async def test_call_invokes_presenter_contract() -> None:
    """The engine calls ``await presenter(request)``; it returns a decision."""
    state = _make_state()
    presenter = ApprovalPresenter(state)
    task = asyncio.ensure_future(presenter(_make_request()))
    await _answer_allow(state)
    decision = await task
    assert decision.outcome is ApprovalOutcome.ALLOW
    assert decision.scope is ApprovalScope.ONCE
    assert decision.request_digest == "sha256:args"


@pytest.mark.asyncio
async def test_request_approval_returns_summoner_decision() -> None:
    """request_approval awaits the queue and returns the given decision."""
    state = _make_state()
    presenter = ApprovalPresenter(state)
    task = asyncio.ensure_future(presenter.request_approval(_make_request()))
    await _answer_allow(state)
    decision = await task
    assert decision.outcome is ApprovalOutcome.ALLOW
    assert decision.scope is ApprovalScope.ONCE


@pytest.mark.asyncio
async def test_request_approval_denies_on_presenter_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any presenter-side failure resolves the cast as denied."""

    def _boom(request: Any) -> Any:
        raise RuntimeError("queue exploded")

    state = _make_state()
    monkeypatch.setattr(state, "enqueue_approval", _boom)
    presenter = ApprovalPresenter(state)
    decision = await presenter.request_approval(_make_request())
    assert decision.outcome is ApprovalOutcome.DENY
    assert decision.reason_code is ApprovalReasonCode.FAILURE


@pytest.mark.asyncio
async def test_session_scope_allow_toggles_badge() -> None:
    """A session-scope allow decision turns the chat badge on."""
    state = _make_state()
    presenter = ApprovalPresenter(state)

    async def _answer_session() -> None:
        await asyncio.sleep(0)
        state.resolve_active_approval(
            ApprovalOutcome.ALLOW, ApprovalScope.SESSION, ApprovalReasonCode.USER
        )

    task = asyncio.ensure_future(presenter.request_approval(_make_request()))
    await _answer_session()
    decision = await task
    assert decision.scope is ApprovalScope.SESSION
    assert state.approval_session_approve_all is True


def test_bind_attaches_to_engine_slot() -> None:
    """bind() installs the presenter on the runner's presenter slot."""
    state = _make_state()
    presenter = ApprovalPresenter(state)
    runner = MagicMock()
    assert presenter.bind(runner) is True
    runner.set_approval_presenter.assert_called_once_with(presenter)
    assert state._approval_presenter is presenter


def test_bind_fails_closed_without_engine_slot() -> None:
    """bind() returns False when the engine has no presenter slot yet."""
    state = _make_state()
    presenter = ApprovalPresenter(state)
    assert presenter.bind(object()) is False
    assert state._approval_presenter is None


@pytest.mark.asyncio
async def test_unbind_denies_pending_and_clears_slot() -> None:
    """unbind() resolves pending requests as denied and clears the slot."""
    state = _make_state()
    presenter = ApprovalPresenter(state)
    runner = MagicMock()
    presenter.bind(runner)

    future = state.enqueue_approval(_make_request())
    presenter.unbind()

    assert future.done()
    assert future.result().outcome is ApprovalOutcome.DENY
    runner.clear_approval_presenter.assert_called_once_with()
    assert state._approval_presenter is None
    assert state.approval_session_approve_all is False


@pytest.mark.asyncio
async def test_unbind_does_not_fall_back_to_setter() -> None:
    """Without the engine's clear method there is no legacy None-set fallback."""
    state = _make_state()
    presenter = ApprovalPresenter(state)

    class LegacyRunner:
        def __init__(self) -> None:
            self.calls: list[Any] = []

        def set_approval_presenter(self, presenter: Any) -> None:
            self.calls.append(presenter)

    runner = LegacyRunner()
    assert presenter.bind(runner) is True
    presenter.unbind()
    assert runner.calls == [presenter]
    assert state._approval_presenter is None


def test_bind_to_new_runner_clears_old_runner() -> None:
    """Rebinding detaches the old runner's slot before installing on the new."""
    state = _make_state()
    presenter = ApprovalPresenter(state)
    runner_a = MagicMock()
    runner_b = MagicMock()
    assert presenter.bind(runner_a) is True
    assert presenter.bind(runner_b) is True
    runner_a.clear_approval_presenter.assert_called_once_with()
    runner_b.set_approval_presenter.assert_called_once_with(presenter)


@pytest.mark.asyncio
async def test_on_client_disconnect_denies_pending() -> None:
    """Web disconnect / refresh resolves pending requests as denied."""
    state = _make_state()
    presenter = ApprovalPresenter(state)
    future = state.enqueue_approval(_make_request())
    presenter.on_client_disconnect()
    assert future.done()
    assert future.result().outcome is ApprovalOutcome.DENY


@pytest.mark.asyncio
async def test_permissions_view_from_explicit_source() -> None:
    """get_permissions_view parses the rune's frozen plain-data dict."""
    state = _make_state()
    presenter = ApprovalPresenter(state)

    class FakeRune:
        def get_permissions_view(self) -> dict[str, Any]:
            return {
                "session": {"session_id": "s1", "approve_all_active": True},
                "always_allowed": [],
            }

    presenter.set_permissions_source(FakeRune())
    view = await presenter.get_permissions_view()
    assert isinstance(view, PermissionsView)
    assert view.session_approve_all is True
    assert view.session_id == "s1"


@pytest.mark.asyncio
async def test_permissions_view_from_runner_get_rune() -> None:
    """The presenter resolves the rune via the runner's get_rune accessor."""

    class FakeRune:
        def get_permissions_view(self) -> dict[str, Any]:
            return {"session": {"approve_all_active": True}}

    class FakeRunner:
        def get_rune(self, name: str) -> Any:
            assert name == "approval-rune"
            return FakeRune()

    state = _make_state()
    presenter = ApprovalPresenter(state)
    presenter._bound_runner = FakeRunner()
    view = await presenter.get_permissions_view()
    assert view is not None
    assert view.session_approve_all is True


@pytest.mark.asyncio
async def test_runner_get_rune_wins_over_explicit_source() -> None:
    """The host accessor resolves first; explicit wiring is the fallback."""

    class RunnerRune:
        def get_permissions_view(self) -> dict[str, Any]:
            return {"session": {"approve_all_active": True}}

    class ExplicitRune:
        def get_permissions_view(self) -> dict[str, Any]:
            return {"session": {"approve_all_active": False}}

    class FakeRunner:
        def get_rune(self, name: str) -> Any:
            return RunnerRune()

    state = _make_state()
    presenter = ApprovalPresenter(state)
    presenter._bound_runner = FakeRunner()
    presenter.set_permissions_source(ExplicitRune())
    view = await presenter.get_permissions_view()
    assert view is not None
    assert view.session_approve_all is True


@pytest.mark.asyncio
async def test_explicit_source_fallback_when_get_rune_empty() -> None:
    """Explicit wiring still works when the runner has no loaded rune."""

    class FakeRune:
        def get_permissions_view(self) -> dict[str, Any]:
            return {"session": {"approve_all_active": True}}

    class FakeRunner:
        def get_rune(self, name: str) -> Any:
            return None

    state = _make_state()
    presenter = ApprovalPresenter(state)
    presenter._bound_runner = FakeRunner()
    presenter.set_permissions_source(FakeRune())
    view = await presenter.get_permissions_view()
    assert view is not None
    assert view.session_approve_all is True


@pytest.mark.asyncio
async def test_permissions_view_none_without_source() -> None:
    """No rune attached means the permissions screen shows unavailable."""
    state = _make_state()
    presenter = ApprovalPresenter(state)
    assert await presenter.get_permissions_view() is None


@pytest.mark.asyncio
async def test_permissions_view_none_on_rune_error() -> None:
    """A failing rune never breaks the presenter."""

    class BadRune:
        def get_permissions_view(self) -> dict[str, Any]:
            raise RuntimeError("policy unreadable")

    state = _make_state()
    presenter = ApprovalPresenter(state)
    presenter.set_permissions_source(BadRune())
    assert await presenter.get_permissions_view() is None


@pytest.mark.asyncio
async def test_revoke_grant_delegates_to_rune() -> None:
    """revoke_grant forwards kind+id to the rune's frozen revoke_grant."""
    calls: list[tuple[str, str]] = []

    class FakeRune:
        def revoke_grant(self, kind: str, grant_id: str) -> bool:
            calls.append((kind, grant_id))
            return True

    state = _make_state()
    presenter = ApprovalPresenter(state)
    presenter.set_permissions_source(FakeRune())
    assert await presenter.revoke_grant("allow_rule", "g1") is True
    assert calls == [("allow_rule", "g1")]


@pytest.mark.asyncio
async def test_revoke_grant_false_without_source() -> None:
    """Revoke without a rune attached reports failure."""
    state = _make_state()
    presenter = ApprovalPresenter(state)
    assert await presenter.revoke_grant("allow_rule", "g1") is False


def test_bind_approval_presenter_helper_binds_agent_runner() -> None:
    """The helper binds one presenter to the agent's runner slot."""
    state = _make_state()
    agent = MagicMock()
    presenter = bind_approval_presenter(state, agent)
    assert presenter is not None
    agent._runner.set_approval_presenter.assert_called_once_with(presenter)
    # Rebinding reuses the same presenter instance.
    assert bind_approval_presenter(state, agent) is presenter


def test_bind_approval_presenter_helper_no_runner() -> None:
    """The helper returns None when the agent exposes no runner."""
    state = _make_state()
    assert bind_approval_presenter(state, MagicMock(_runner=None)) is None
    assert bind_approval_presenter(state, object()) is None


def test_unbind_approval_presenter_helper_clears_state() -> None:
    """The helper unbinds the presenter's slot and drops the state ref."""
    state = _make_state()
    agent = MagicMock()
    presenter = bind_approval_presenter(state, agent)
    assert presenter is not None
    unbind_approval_presenter(state)
    assert state._approval_presenter is None
    agent._runner.clear_approval_presenter.assert_called_once_with()


def test_unbind_approval_presenter_helper_without_presenter() -> None:
    """Unbinding with nothing bound is a quiet no-op."""
    state = _make_state()
    unbind_approval_presenter(state)
