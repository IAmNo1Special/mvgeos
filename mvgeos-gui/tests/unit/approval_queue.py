"""Unit tests for the approval request queue (AppState-owned)."""

from __future__ import annotations

import asyncio
import os

import pytest
from mvgeos_core.approval import (
    ApprovalOutcome,
    ApprovalReasonCode,
    ApprovalRequest,
    ApprovalScope,
)

from mvgeos_gui.approval.queue import ApprovalQueue, is_request_stale


def _req(
    cast_id: str = "call_1",
    project_root: str = "/proj",
    tome_id: str | None = "t1",
    argument_digest: str = "sha256:args",
) -> ApprovalRequest:
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
        arguments={"path": "/proj/a.txt"},
        argument_digest=argument_digest,
        project_root=project_root,
        tome_id=tome_id or "",
        agent_name="coding_mvge",
    )


@pytest.mark.asyncio
async def test_enqueue_returns_awaitable_future() -> None:
    """Enqueueing hands back a future the presenter can await."""
    queue = ApprovalQueue()
    future = queue.enqueue(_req())
    assert isinstance(future, asyncio.Future)
    assert not future.done()
    future.cancel()


@pytest.mark.asyncio
async def test_one_active_at_a_time_fifo_order() -> None:
    """Parallel batches queue; activation is strictly FIFO, one active."""
    queue = ApprovalQueue()
    first = queue.enqueue(_req("call_1"))
    second = queue.enqueue(_req("call_2"))
    assert queue.pending_count == 2
    assert queue.active_request is None

    active = queue.activate_next()
    assert active is not None
    assert active.cast_id == "call_1"
    assert queue.active_request is not None
    assert queue.pending_count == 1

    # Activating again while one is active is a no-op.
    assert queue.activate_next() is not None
    assert queue.activate_next().cast_id == "call_1"  # type: ignore[union-attr]

    queue.resolve_active(
        ApprovalOutcome.ALLOW,
        ApprovalScope.ONCE,
        ApprovalReasonCode.USER,
        project_root="/proj",
        tome_id="t1",
    )
    assert first.done()
    assert queue.active_request is None

    active = queue.activate_next()
    assert active is not None
    assert active.cast_id == "call_2"
    queue.resolve_active(
        ApprovalOutcome.DENY,
        ApprovalScope.ONCE,
        ApprovalReasonCode.USER,
        project_root="/proj",
        tome_id="t1",
    )
    assert second.done()
    assert second.result().outcome is ApprovalOutcome.DENY


@pytest.mark.asyncio
async def test_resolve_with_no_active_is_noop() -> None:
    """Resolving with nothing active does not explode."""
    queue = ApprovalQueue()
    assert queue.resolve_active(ApprovalOutcome.DENY) is None


@pytest.mark.asyncio
async def test_resolve_binds_decision_to_request_digest() -> None:
    """Every resolved decision carries the active request's argument digest."""
    queue = ApprovalQueue()
    future = queue.enqueue(_req("call_1", argument_digest="sha256:args"))
    queue.activate_next()
    queue.resolve_active(
        ApprovalOutcome.ALLOW,
        ApprovalScope.ONCE,
        ApprovalReasonCode.USER,
        project_root="/proj",
        tome_id="t1",
    )
    decision = future.result()
    assert decision.request_digest == "sha256:args"


@pytest.mark.asyncio
async def test_cancel_all_denies_active_and_pending() -> None:
    """cancel_all resolves every outstanding future as denied."""
    queue = ApprovalQueue()
    f1 = queue.enqueue(_req("call_1"))
    f2 = queue.enqueue(_req("call_2"))
    queue.activate_next()
    denied = queue.cancel_all()
    assert {r.cast_id for r in denied} == {"call_1", "call_2"}
    assert f1.done()
    assert f1.result().outcome is ApprovalOutcome.DENY
    assert f2.done()
    assert f2.result().outcome is ApprovalOutcome.DENY
    assert queue.active_request is None
    assert queue.pending_count == 0


@pytest.mark.asyncio
async def test_cancel_all_empty_is_noop() -> None:
    """Cancelling an empty queue returns nothing and stays quiet."""
    assert ApprovalQueue().cancel_all() == []


def test_is_request_stale_detects_context_change() -> None:
    """A late response is stale when the tome or project changed."""
    req = _req()
    assert not is_request_stale(req, project_root="/proj", tome_id="t1")
    assert is_request_stale(req, project_root="/proj", tome_id="t2")
    assert is_request_stale(req, project_root="/other", tome_id="t1")


def test_is_request_stale_ignores_none_tome_on_both_sides() -> None:
    """No active tome on both sides is not a mismatch."""
    req = _req(tome_id=None)
    assert not is_request_stale(req, project_root="/proj", tome_id=None)
    assert is_request_stale(req, project_root="/proj", tome_id="t1")


def test_is_request_stale_ignores_trailing_slash_spelling() -> None:
    """A trailing slash does not make the same directory look moved."""
    req = _req(project_root="/proj/a")
    assert not is_request_stale(req, project_root="/proj/a/", tome_id="t1")


@pytest.mark.skipif(
    os.name != "nt",
    reason=(
        "Separator-insensitive project-root comparison only differs on "
        "Windows, where str(Path) uses backslashes."
    ),
)
def test_is_request_stale_ignores_windows_separator_spelling() -> None:
    """The same directory spelled with / vs \\ is not a context change."""
    req = _req(project_root="C:/proj/a")
    assert not is_request_stale(req, project_root="C:\\proj\\a", tome_id="t1")
    # A genuinely different directory is still stale (fail-closed).
    assert is_request_stale(req, project_root="C:\\proj\\b", tome_id="t1")


@pytest.mark.asyncio
async def test_resolve_active_applies_stale_check() -> None:
    """resolve_active forces deny when the context moved under the popup."""
    queue = ApprovalQueue()
    future = queue.enqueue(_req("call_1"))
    queue.activate_next()
    effective = queue.resolve_active(
        ApprovalOutcome.ALLOW,
        ApprovalScope.ONCE,
        ApprovalReasonCode.USER,
        project_root="/proj",
        tome_id="t2",  # tome switched while the popup was open
    )
    assert effective is not None
    assert effective.outcome is ApprovalOutcome.DENY
    assert effective.reason_code is ApprovalReasonCode.FAILURE
    assert future.result().outcome is ApprovalOutcome.DENY


@pytest.mark.asyncio
async def test_future_awaitable_from_event_loop() -> None:
    """The presenter can await the future and get the decision back."""
    queue = ApprovalQueue()
    future = queue.enqueue(_req("call_9"))
    queue.activate_next()

    async def _resolve() -> None:
        await asyncio.sleep(0)
        queue.resolve_active(
            ApprovalOutcome.ALLOW,
            ApprovalScope.ONCE,
            ApprovalReasonCode.USER,
            project_root="/proj",
            tome_id="t1",
        )

    await asyncio.gather(_resolve(), future)
    assert future.result().outcome is ApprovalOutcome.ALLOW
    assert future.result().scope is ApprovalScope.ONCE


@pytest.mark.asyncio
async def test_rapid_casts_serialize_fifo_with_no_lost_decisions() -> None:
    """Stress: 50 rapid casts serialize strictly FIFO; every future resolves."""
    queue = ApprovalQueue()
    count = 50
    futures = [queue.enqueue(_req(f"call_{i}")) for i in range(count)]
    assert queue.pending_count == count

    for i in range(count):
        active = queue.activate_next()
        assert active is not None
        assert active.cast_id == f"call_{i}"
        outcome = ApprovalOutcome.ALLOW if i % 2 == 0 else ApprovalOutcome.DENY
        queue.resolve_active(
            outcome,
            ApprovalScope.ONCE,
            ApprovalReasonCode.USER,
            project_root="/proj",
            tome_id="t1",
        )

    assert queue.pending_count == 0
    assert queue.active_request is None
    for i, future in enumerate(futures):
        assert future.done()
        expected = ApprovalOutcome.ALLOW if i % 2 == 0 else ApprovalOutcome.DENY
        assert future.result().outcome is expected
