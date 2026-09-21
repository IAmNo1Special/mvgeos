"""AppState-owned approval queue: one modal, one cast.

Parallel spell-cast batches queue here and are presented strictly one at a
time: the active request holds the single future the presenter awaits, and
only when it resolves does the next queued request become active. Every
lost decision surface (dialog close, Escape, disconnect, shutdown, context
change) resolves outstanding futures as denied.

The queue stores the canonical ``mvgeos_core.approval`` types: the engine
isinstance-checks the returned ``ApprovalDecision``, and every decision is
bound to the active request's ``argument_digest``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from dataclasses import dataclass

from mvgeos_core.approval import (
    ApprovalDecision,
    ApprovalOutcome,
    ApprovalReasonCode,
    ApprovalRequest,
    ApprovalScope,
)

logger = logging.getLogger(__name__)


def _normalize_project_root(value: str) -> str:
    """Platform-normalized form of a project root for comparison.

    The engine hands ``project_root`` over as a raw string while the GUI
    passes ``str(Path)``; on Windows those spell the same directory with
    different separators (``/`` vs ``\\``), which a naive string compare
    reads as a context change and force-denies the decision. Normalizing
    both sides keeps the stale check fail-closed on genuinely different
    directories while accepting identical ones.
    """
    return os.path.normcase(os.path.normpath(value))


def is_request_stale(
    request: ApprovalRequest,
    *,
    project_root: str | None,
    tome_id: str | None,
) -> bool:
    """Check whether a response arrived for a moved-on context.

    The stale-response rule: if the active tome or project no longer
    matches the frozen request, the response is discarded and the cast
    denied. Cast identity and the argument digest are structural: the
    queue always binds the decision to the active request, so they need
    no separate check. An empty tome id counts as "no active tome".
    """
    if project_root is not None and _normalize_project_root(
        request.project_root
    ) != _normalize_project_root(project_root):
        return True
    live_tome = tome_id or None
    request_tome = request.tome_id or None
    if live_tome is None and request_tome is None:
        return False
    return request_tome != live_tome


def deny_request(
    request: ApprovalRequest,
    reason_code: ApprovalReasonCode = ApprovalReasonCode.FAILURE,
) -> ApprovalDecision:
    """Build a denial decision bound to one request's argument digest."""
    return ApprovalDecision(
        outcome=ApprovalOutcome.DENY,
        scope=ApprovalScope.ONCE,
        reason_code=reason_code,
        request_digest=request.argument_digest,
    )


@dataclass
class _ActiveApproval:
    request: ApprovalRequest
    future: asyncio.Future[ApprovalDecision]


class ApprovalQueue:
    """FIFO queue of pending approval requests with a single active slot."""

    def __init__(self) -> None:
        self._pending: deque[_ActiveApproval] = deque()
        self._active: _ActiveApproval | None = None

    @property
    def pending_count(self) -> int:
        """Number of requests waiting behind the active one."""
        return len(self._pending)

    @property
    def active_request(self) -> ApprovalRequest | None:
        """The request currently shown in the modal, if any."""
        return self._active.request if self._active is not None else None

    def enqueue(self, request: ApprovalRequest) -> asyncio.Future[ApprovalDecision]:
        """Queue a request; returns the future the presenter awaits."""
        future: asyncio.Future[ApprovalDecision] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending.append(_ActiveApproval(request=request, future=future))
        return future

    def activate_next(self) -> ApprovalRequest | None:
        """Move the queue head into the active slot (one modal at a time)."""
        if self._active is not None or not self._pending:
            return self.active_request
        self._active = self._pending.popleft()
        return self._active.request

    def resolve_active(
        self,
        outcome: ApprovalOutcome,
        scope: ApprovalScope = ApprovalScope.ONCE,
        reason_code: ApprovalReasonCode = ApprovalReasonCode.USER,
        *,
        project_root: str | None = None,
        tome_id: str | None = None,
    ) -> ApprovalDecision | None:
        """Resolve the active request, applying the stale-response rule.

        Builds the decision bound to the active request's argument digest.
        Returns the effective decision (forced deny when stale), or None
        when no request is active.
        """
        active = self._active
        if active is None:
            return None
        if is_request_stale(active.request, project_root=project_root, tome_id=tome_id):
            logger.warning(
                "Approval decision for cast %s arrived stale; denying",
                active.request.cast_id,
            )
            outcome = ApprovalOutcome.DENY
            scope = ApprovalScope.ONCE
            reason_code = ApprovalReasonCode.FAILURE
        effective = ApprovalDecision(
            outcome=outcome,
            scope=scope,
            reason_code=reason_code,
            request_digest=active.request.argument_digest,
        )
        self._active = None
        if not active.future.done():
            active.future.set_result(effective)
        return effective

    def deny_active(
        self, reason_code: ApprovalReasonCode = ApprovalReasonCode.FAILURE
    ) -> ApprovalDecision | None:
        """Deny the active request (dialog closed, Escape, disconnect)."""
        active = self._active
        if active is None:
            return None
        return self.resolve_active(
            ApprovalOutcome.DENY,
            ApprovalScope.ONCE,
            reason_code,
            project_root=active.request.project_root,
            tome_id=active.request.tome_id,
        )

    def cancel_all(self) -> list[ApprovalRequest]:
        """Deny every outstanding request; returns the denied requests."""
        denied: list[ApprovalRequest] = []
        if self._active is not None:
            denied.append(self._active.request)
            if not self._active.future.done():
                self._active.future.set_result(deny_request(self._active.request))
            self._active = None
        while self._pending:
            item = self._pending.popleft()
            denied.append(item.request)
            if not item.future.done():
                item.future.set_result(deny_request(item.request))
        return denied
