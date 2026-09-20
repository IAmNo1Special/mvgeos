"""GUI presenter for the Approval Rune's spell-cast gate.

The host binds one ``ApprovalPresenter`` to the engine-owned runner's
presenter slot at startup (see :func:`bind_approval_presenter`) and unbinds
it on shutdown. The engine invokes the presenter as
``await presenter(request)`` with the canonical ``ApprovalRequest``; the
presenter drives the AppState-owned approval queue and returns the
Summoner's canonical ``ApprovalDecision``. With no presenter bound, the
engine denies (fail closed); every presenter-side failure also denies.

The rune owns policy matching, persistence, and audit; this module only
presents the request and returns the Summoner's decision.

Permissions data (the settings-cog screen) comes from the Approval Rune's
frozen ``get_permissions_view()`` / ``revoke_grant(kind, id)`` interface.
Resolution order: the bound runner's host-privileged ``get_rune`` accessor
(duck-typed; the engine owns that accessor), then an explicitly wired
source (:meth:`set_permissions_source`). Nothing presenter-related lives
on RuneAPI.
"""

from __future__ import annotations

import contextlib
import inspect
import logging
from typing import TYPE_CHECKING, Any

from mvgeos_core.approval import (
    ApprovalDecision,
    ApprovalOutcome,
    ApprovalReasonCode,
    ApprovalRequest,
    ApprovalScope,
    deny,
)

from mvgeos_gui.approval.types import APPROVAL_RUNE_NAME, PermissionsView

if TYPE_CHECKING:
    from mvgeos_gui.state import AppState

logger = logging.getLogger(__name__)


def _deny_unbound(request: Any) -> ApprovalDecision:
    """Fail-closed denial when the request itself is unusable."""
    try:
        return deny(request, ApprovalReasonCode.FAILURE)
    except Exception:
        return ApprovalDecision(
            outcome=ApprovalOutcome.DENY,
            scope=ApprovalScope.ONCE,
            reason_code=ApprovalReasonCode.FAILURE,
            request_digest="",
        )


class ApprovalPresenter:
    """Host-side presenter: queues modal prompts, returns decisions.

    Implements the engine's ``ApprovalPresenter`` contract
    (``mvgeos_core.approval``): the engine invokes the presenter as
    ``await presenter(request)``.
    """

    def __init__(self, state: AppState) -> None:
        self._state = state
        self._bound_runner: Any = None
        self._permissions_source: Any = None

    async def __call__(self, request: ApprovalRequest) -> ApprovalDecision:
        """The engine's presenter contract: ``await presenter(request)``."""
        return await self.request_approval(request)

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Await the Summoner's decision for one spell cast.

        Never raises: any failure denies.
        """
        try:
            future = self._state.enqueue_approval(request)
            decision = await future
        except Exception:
            logger.exception("Approval presenter failed; denying")
            decision = _deny_unbound(request)
        if (
            decision.outcome is ApprovalOutcome.ALLOW
            and decision.scope is ApprovalScope.SESSION
        ):
            self._state.set_approval_session_badge(True)
        return decision

    def bind(self, runner: Any) -> bool:
        """Install this presenter on the engine runner's presenter slot.

        Returns True when the engine exposes the slot; False when the
        engine contract has not landed yet (the gate then denies, per the
        spec's fail-closed rule). Moving the presenter to a different
        runner clears the old runner's slot first so a dead runner can
        never receive Summoner decisions.
        """
        setter = getattr(runner, "set_approval_presenter", None)
        if not callable(setter):
            logger.warning(
                "Engine runner has no approval presenter slot; "
                "approval prompts will deny until the engine contract lands."
            )
            return False
        old_runner = self._bound_runner
        if old_runner is not None and old_runner is not runner:
            old_clearer = getattr(old_runner, "clear_approval_presenter", None)
            if callable(old_clearer):
                with contextlib.suppress(Exception):
                    old_clearer()
        setter(self)
        self._bound_runner = runner
        self._state._approval_presenter = self
        return True

    def unbind(self) -> None:
        """Remove the presenter and deny every outstanding request."""
        runner = self._bound_runner
        self._bound_runner = None
        if runner is not None:
            clearer = getattr(runner, "clear_approval_presenter", None)
            if callable(clearer):
                with contextlib.suppress(Exception):
                    clearer()
        self._state.cancel_pending_approvals()
        self._state.set_approval_session_badge(False)
        self._state._approval_presenter = None

    def on_client_disconnect(self) -> None:
        """Web mode: disconnect/refresh/lost client denies pending casts."""
        self._state.cancel_pending_approvals()

    def set_permissions_source(self, source: Any) -> None:
        """Wire the Approval Rune's permissions interface explicitly."""
        self._permissions_source = source

    def _resolve_permissions_source(self) -> Any:
        """Find the Approval Rune's permissions interface, if reachable.

        Order: the bound runner's host-privileged ``get_rune`` accessor
        (duck-typed; the engine owns that accessor), then the explicitly
        wired source. Nothing presenter-related lives on RuneAPI.
        """
        runner = self._bound_runner
        getter = getattr(runner, "get_rune", None)
        if callable(getter):
            try:
                rune = getter(APPROVAL_RUNE_NAME)
            except Exception:
                logger.warning("Runner get_rune failed", exc_info=True)
                rune = None
            if rune is not None:
                return rune
        return self._permissions_source

    async def get_permissions_view(self) -> PermissionsView | None:
        """Return the parsed permissions view, or None when unavailable."""
        source = self._resolve_permissions_source()
        if source is None:
            return None
        getter = getattr(source, "get_permissions_view", None)
        if not callable(getter):
            return None
        try:
            result = getter()
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            logger.warning("Approval Rune get_permissions_view failed", exc_info=True)
            return None
        return PermissionsView.from_dict(result)

    async def revoke_grant(self, grant_kind: str, grant_id: str) -> bool:
        """Revoke one grant through the Approval Rune; True when confirmed.

        Uses the frozen ``revoke_grant(kind, id)`` action (kinds
        "allow_rule", "deny_rule", "project", "session"). Revocation
        persists immediately and takes effect before the next cast.
        """
        source = self._resolve_permissions_source()
        if source is None:
            return False
        action = getattr(source, "revoke_grant", None)
        if not callable(action):
            return False
        try:
            result = action(grant_kind, grant_id)
            if inspect.isawaitable(result):
                result = await result
            return bool(result)
        except Exception:
            logger.warning("Approval Rune revoke failed", exc_info=True)
            return False


def bind_approval_presenter(state: AppState, agent: Any) -> ApprovalPresenter | None:
    """Bind the GUI presenter to an agent's engine runner slot.

    Reuses the state's presenter across agent recreations (the agent is
    rebuilt on project/tome changes). Returns the presenter when bound,
    None when the agent exposes no runner or the engine slot is missing.
    """
    presenter: ApprovalPresenter | None = state._approval_presenter
    if presenter is None:
        presenter = ApprovalPresenter(state)
    runner = getattr(agent, "_runner", None)
    if runner is None:
        logger.debug("Agent exposes no engine runner; presenter not bound")
        return None
    if presenter.bind(runner):
        return presenter
    return None


def unbind_approval_presenter(state: AppState) -> None:
    """Unbind the GUI presenter (shutdown): pending casts deny."""
    presenter = state._approval_presenter
    if presenter is not None:
        presenter.unbind()
    else:
        state.cancel_pending_approvals()
        state.set_approval_session_badge(False)
