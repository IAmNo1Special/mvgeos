"""Approval Rune GUI surfaces: popup modal, chat badge, permissions screen.

The popup presents one cast at a time (the AppState queue owns ordering).
Every model-controlled string renders as inert plain text via ``ui.label``:
never ``ui.markdown`` or ``ui.html``.

The permissions screen consumes the Approval Rune's frozen
``get_permissions_view()`` contract (keys ``session``, ``trusted_projects``,
``always_allowed``, ``never_allowed``, ``source_identity``,
``recent_activity``, ``warnings``) and revokes through the frozen
``revoke_grant(kind, id)`` action (kinds "allow_rule", "deny_rule",
"project", "session"). Constraint text comes from the rune's own
``constraint_labels``; the GUI never invents constraint vocabulary.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mvgeos_core.approval import (
    ApprovalOutcome,
    ApprovalReasonCode,
    ApprovalRequest,
    ApprovalScope,
)
from mvgeos_runes import list_installed_runes
from nicegui import ui

from mvgeos_gui.approval.types import (
    PermissionsView,
    describe_operation,
    is_approval_rune_name,
    is_mutating_request,
    spell_source_label,
)
from mvgeos_gui.components.rune_settings_dialog import render_rune_settings_dialog

if TYPE_CHECKING:
    from mvgeos_gui.approval.presenter import ApprovalPresenter
    from mvgeos_gui.state import AppState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Overlay mounting
# ---------------------------------------------------------------------------


def mount_approval_overlay(state: AppState) -> None:
    """Mount the approval modal overlay for this page.

    Called once per page construction (like the other shell overlays), so
    every connected client gets its own overlay and subscription.
    Re-renders when the active cast, the dialog step, or the permissions
    deep-link flag changes. Closing the dialog (X, Escape, click-away)
    denies the active request.
    """

    @ui.refreshable
    def approval_overlay_view() -> None:
        if state.take_approval_permissions_open_request():
            open_approval_permissions(state)
        req = state.approval_active_request
        if req is None:
            return
        _render_approval_dialog(state, req)

    approval_overlay_view()

    def _key() -> tuple[str | None, str, bool]:
        req = state.approval_active_request
        return (
            req.cast_id if req is not None else None,
            state._approval_dialog_step,
            state._approval_settings_requested,
        )

    last = [_key()]

    def _check() -> None:
        current = _key()
        if current != last[0]:
            last[0] = current
            approval_overlay_view.refresh()

    state.subscribe(_check)


# ---------------------------------------------------------------------------
# Popup modal
# ---------------------------------------------------------------------------


def _short_digest(digest: str | None) -> str:
    if not digest:
        return "none"
    return digest if len(digest) <= 18 else digest[:18] + "..."


def _render_approval_dialog(state: AppState, req: ApprovalRequest) -> None:
    step = state._approval_dialog_step
    with (
        ui.dialog().on(
            "close", lambda: state.deny_approval_if_active(req.cast_id)
        ) as dialog,
        ui.card().classes(
            "w-[560px] max-w-[92vw] bg-[#14121a] border border-[#2a2438] "
            "rounded-xl p-5 gap-3"
        ),
    ):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("shield", size="20px").classes("text-[#e879f9]")
                title = (
                    "Confirm persistent grant"
                    if step == "confirm"
                    else "Approval requested"
                )
                ui.label(title).classes("text-base font-semibold text-[#eceaf4]")
            ui.button(icon="close", on_click=dialog.close).props(
                "flat dense round text-color=grey-5 size=sm"
            ).mark("approval_dialog_close_btn")
        if step == "confirm":
            _render_confirm_step(state, req)
        else:
            _render_main_step(state, req)
    dialog.open()


def _format_arg_value(value: Any) -> str:
    """Render one frozen argument value as inert plain text."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(value)


def _render_main_step(state: AppState, req: ApprovalRequest) -> None:
    ui.label(f'"{req.spell_name}" wants to cast:').classes("text-sm text-[#9c94b3]")
    ui.label(describe_operation(req)).classes("text-sm font-medium text-[#eceaf4]")
    if not req.schema_validated:
        with ui.row().classes(
            "w-full items-center gap-2 bg-[#2a1215] border "
            "border-[#f87171]/40 rounded-lg p-3"
        ):
            ui.icon("warning", size="16px").classes("text-[#f87171]")
            ui.label(
                "Unvalidated arguments: this spell has no parameter schema, "
                "so no persistent rule can cover it; every cast prompts."
            ).classes("text-xs text-[#fca5a5]").mark("approval_unvalidated_warning")
    with ui.row().classes("gap-2 flex-wrap"):
        ui.label(f"Source: {spell_source_label(req)}").classes("text-xs text-[#6e6584]")
        ui.label(f"Argument digest: {_short_digest(req.argument_digest)}").classes(
            "text-xs text-[#6e6584]"
        )
    if req.arguments:
        with ui.column().classes("w-full gap-0.5 bg-[#0e0c13] rounded-lg p-3"):
            for key, value in req.arguments.items():
                ui.label(f"{key}: {_format_arg_value(value)}").classes(
                    "text-xs font-mono text-[#b8b0cc]"
                )
    with ui.row().classes("w-full gap-2"):
        ui.button(
            "Allow once",
            on_click=lambda: state.resolve_active_approval(
                ApprovalOutcome.ALLOW,
                ApprovalScope.ONCE,
                ApprovalReasonCode.USER,
            ),
        ).props("unelevated").classes("flex-1 bg-[#7b6cf6] text-white").mark(
            "approval_allow_once_btn"
        )
        ui.button(
            "Deny once",
            on_click=lambda: state.deny_active_approval(ApprovalReasonCode.USER),
        ).props("outlined").classes("flex-1").mark("approval_deny_once_btn")
    with ui.column().classes("w-full gap-1"):
        ui.label("More options").classes(
            "text-[10px] uppercase tracking-wider text-[#6e6584]"
        )
        with ui.row().classes("w-full gap-2"):
            ui.button(
                "Always allow this spell...",
                on_click=lambda: state.set_approval_dialog_step(
                    "confirm", "spell-allow"
                ),
            ).props("outlined").classes("flex-1 text-xs").mark(
                "approval_always_allow_btn"
            )
            ui.button(
                "Always deny this spell...",
                on_click=lambda: state.set_approval_dialog_step(
                    "confirm", "spell-deny"
                ),
            ).props("outlined").classes("flex-1 text-xs").mark(
                "approval_always_deny_btn"
            )
        with ui.row().classes("w-full gap-2"):
            ui.button(
                "Approve all this session",
                on_click=lambda: state.set_approval_dialog_step("confirm", "session"),
            ).props("outlined").classes("flex-1 text-xs").mark("approval_session_btn")
            ui.button(
                "Approve all in this project",
                on_click=lambda: state.set_approval_dialog_step("confirm", "project"),
            ).props("outlined").classes("flex-1 text-xs").mark("approval_project_btn")
    with ui.row().classes("w-full justify-center"):
        ui.button(
            "manage permissions",
            on_click=lambda: state.request_approval_permissions_open(),
        ).props("flat dense no-caps").classes("text-xs text-[#7b6cf6]").mark(
            "approval_manage_permissions_btn"
        )


def _render_confirm_step(state: AppState, req: ApprovalRequest) -> None:
    kind = state._approval_confirm_kind
    if kind == "spell-allow":
        ui.label(f'Always allow "{req.spell_name}"?').classes(
            "text-base font-semibold text-[#eceaf4]"
        )
        ui.label("Scope: global (all projects).").classes("text-xs text-[#9c94b3]")
        ui.label(
            "The Approval Rune records the grant from this cast's engine-derived "
            f"spell identity ({spell_source_label(req)})."
        ).classes("text-xs text-[#9c94b3]")
        if is_mutating_request(req):
            ui.label(
                "WARNING: this spell can mutate state. An always-allow grant "
                "authorizes every future argument for this spell identity. "
                "Only confirm if you mean full trust."
            ).classes("text-xs text-[#f87171]")
    elif kind == "spell-deny":
        ui.label(f'Always deny "{req.spell_name}"?').classes(
            "text-base font-semibold text-[#eceaf4]"
        )
        ui.label(
            "This denial overrides every approval scope: session, project, "
            "and spell grants. You will not be asked again for this spell."
        ).classes("text-xs text-[#9c94b3]")
    elif kind == "session":
        ui.label("Approve all mutating casts this session?").classes(
            "text-base font-semibold text-[#eceaf4]"
        )
        ui.label(
            "Temporary: clears on tome switch, fork, new tome, project "
            "change, or exit. Deny rules still win."
        ).classes("text-xs text-[#9c94b3]")
    elif kind == "project":
        ui.label(
            f'Approve all mutating casts in "{req.project_root or "this project"}"?'
        ).classes("text-base font-semibold text-[#eceaf4]")
        ui.label("Persistent for this project only.").classes("text-xs text-[#9c94b3]")
        ui.label(
            "This is not a filesystem sandbox: a shell spell could still "
            "address paths outside the project."
        ).classes("text-xs text-[#fbbf24]")
    else:
        ui.label("Unknown grant kind.").classes("text-xs text-[#f87171]")
    with ui.row().classes("w-full gap-2 justify-end"):
        ui.button(
            "Back", on_click=lambda: state.set_approval_dialog_step("main")
        ).props("flat").mark("approval_back_btn")
        ui.button(
            "Confirm grant",
            on_click=lambda: _confirm_grant(state, req, kind),
        ).props("unelevated").classes("bg-[#7b6cf6] text-white").mark(
            "approval_confirm_grant_btn"
        )


def _confirm_grant(state: AppState, req: ApprovalRequest, kind: str) -> None:
    """Build the persistent decision from the confirmation screen.

    The engine request carries no grant metadata: the Approval Rune owns
    policy matching and records the grant from the decision's outcome and
    scope plus the request's engine-derived spell identity.
    """
    if kind == "spell-allow":
        state.resolve_active_approval(
            ApprovalOutcome.ALLOW, ApprovalScope.SPELL, ApprovalReasonCode.USER
        )
    elif kind == "spell-deny":
        state.resolve_active_approval(
            ApprovalOutcome.DENY, ApprovalScope.SPELL, ApprovalReasonCode.USER
        )
    elif kind == "session":
        state.resolve_active_approval(
            ApprovalOutcome.ALLOW, ApprovalScope.SESSION, ApprovalReasonCode.USER
        )
    elif kind == "project":
        state.resolve_active_approval(
            ApprovalOutcome.ALLOW, ApprovalScope.PROJECT, ApprovalReasonCode.USER
        )


# ---------------------------------------------------------------------------
# Chat badge
# ---------------------------------------------------------------------------


def render_approval_badge(state: AppState) -> None:
    """Persistent session approve-all indicator for the chat panel."""

    @ui.refreshable
    def approval_badge_view() -> None:
        if not state.approval_session_approve_all:
            return
        with ui.row().classes(
            "w-full items-center gap-2 px-4 py-1.5 "
            "bg-[#2a1030] border-b border-[#e879f9]/40"
        ):
            ui.icon("verified_user", size="14px").classes("text-[#e879f9]")
            ui.label(
                "Session approval active: mutating casts run without "
                "prompting until the session ends."
            ).classes("text-[11px] text-[#f5d0fe] flex-1")
            ui.button(
                "Details",
                on_click=lambda: state.request_approval_permissions_open(),
            ).props("flat dense no-caps").classes("text-[11px] text-[#e879f9]").mark(
                "approval_badge_details_btn"
            )

            async def _revoke_session() -> None:
                presenter = state._approval_presenter
                if presenter is None:
                    ui.notify("Approval Rune is not available", type="warning")
                    return
                view = await presenter.get_permissions_view()
                session_id = view.session_id if view is not None else None
                ok = await presenter.revoke_grant("session", session_id or "session")
                if ok:
                    state.set_approval_session_badge(False)
                    ui.notify("Session approval revoked", type="positive")
                else:
                    ui.notify("Could not revoke session approval", type="negative")

            ui.button("Revoke", on_click=_revoke_session).props(
                "flat dense no-caps"
            ).classes("text-[11px] text-[#f87171]").mark("approval_badge_revoke_btn")

    approval_badge_view()

    last = [state.approval_session_approve_all]

    def _check() -> None:
        if state.approval_session_approve_all != last[0]:
            last[0] = state.approval_session_approve_all
            approval_badge_view.refresh()

    state.subscribe_view("approval_badge", _check)


# ---------------------------------------------------------------------------
# Permissions screen (settings cog)
# ---------------------------------------------------------------------------


def render_approval_permissions(state: AppState) -> None:
    """Render the permissions screen inside the rune's settings dialog."""
    ui.label("Approval permissions").classes("text-sm font-semibold text-[#eceaf4]")
    with ui.column().classes("w-full gap-3") as body:
        ui.spinner("dots", size="sm").classes("self-center text-[#7b6cf6]")

    async def _load() -> None:
        presenter = state._approval_presenter
        view = await presenter.get_permissions_view() if presenter is not None else None
        body.clear()
        with body:
            if view is None or presenter is None:
                _render_permissions_unavailable()
            else:
                state.sync_approval_session_badge(view)
                _render_permissions_view(state, presenter, view, _load)

    ui.timer(0.05, _load, once=True)


def _render_permissions_unavailable() -> None:
    ui.label(
        "Permissions are unavailable: the Approval Rune did not return a "
        "permissions view. The rune may not be loaded."
    ).classes("text-xs text-[#9c94b3]")


def _render_permissions_view(
    state: AppState,
    presenter: ApprovalPresenter,
    view: PermissionsView,
    reload: Callable[[], Awaitable[None]],
) -> None:
    async def _revoke(kind: str, grant_id: str) -> None:
        ok = await presenter.revoke_grant(kind, grant_id)
        if ok:
            ui.notify("Grant revoked", type="positive")
            await reload()
        else:
            ui.notify("Revoke failed", type="negative")

    if view.warnings:
        with ui.column().classes(
            "w-full gap-1 bg-[#2a1215] border border-[#f87171]/40 rounded-lg p-3"
        ):
            with ui.row().classes("items-center gap-1.5"):
                ui.icon("warning", size="14px").classes("text-[#f87171]")
                ui.label("Warnings").classes("text-xs font-semibold text-[#fca5a5]")
            for warning in view.warnings:
                ui.label(warning).classes("text-xs text-[#fca5a5]")

    with ui.row().classes("w-full items-center gap-2"):
        ui.label("Session approve-all").classes("text-xs font-semibold text-[#eceaf4]")
        if view.session_approve_all:
            ui.badge("ON", color="pink").props("rounded dense").classes("text-[10px]")
            if view.session_id:
                ui.label(f"session {view.session_id}").classes(
                    "text-[11px] text-[#6e6584] font-mono"
                )
            ui.button(
                "Revoke",
                on_click=lambda: _revoke("session", view.session_id or "session"),
            ).props("flat dense").classes("text-xs text-[#f87171]").mark(
                "approval_revoke_session"
            )
        else:
            ui.label("off").classes("text-xs text-[#6e6584]")

    ui.separator().classes("bg-[#292335]")
    ui.label("Trusted projects").classes("text-xs font-semibold text-[#eceaf4]")
    if view.trusted_projects:
        for index, project in enumerate(view.trusted_projects):
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(project.root).classes(
                    "text-xs font-mono text-[#b8b0cc] flex-1 break-all"
                )
                ui.label("enabled" if project.enabled else "disabled").classes(
                    "text-[10px] text-[#6e6584]"
                )
                ui.button(
                    "Revoke",
                    on_click=lambda p=project: _revoke("project", p.grant_id),
                ).props("flat dense").classes("text-xs text-[#f87171]").mark(
                    f"approval_revoke_project_{index}"
                )
    else:
        ui.label("No trusted projects.").classes("text-xs text-[#6e6584]")

    ui.separator().classes("bg-[#292335]")
    ui.label("Always allowed").classes("text-xs font-semibold text-[#eceaf4]")
    if view.always_allowed:
        for grant in view.always_allowed:
            _render_grant_card(grant, "allow_rule", _revoke)
    else:
        ui.label("No always-allowed rules.").classes("text-xs text-[#6e6584]")

    ui.separator().classes("bg-[#292335]")
    ui.label("Never allowed").classes("text-xs font-semibold text-[#eceaf4]")
    if view.never_allowed:
        for grant in view.never_allowed:
            _render_grant_card(grant, "deny_rule", _revoke)
    else:
        ui.label("No never-allowed rules.").classes("text-xs text-[#6e6584]")

    if view.recent_activity:
        ui.separator().classes("bg-[#292335]")
        ui.label("Recent activity").classes("text-xs font-semibold text-[#eceaf4]")
        with ui.column().classes(
            "w-full gap-1 max-h-40 overflow-y-auto bg-[#0e0c13] rounded-lg p-2"
        ):
            for record in view.recent_activity:
                ui.label(
                    f"{record.timestamp or '?'}  {record.spell_name}  "
                    f"{record.decision}/{record.scope}  ({record.reason_code})"
                ).classes("text-[11px] font-mono text-[#9c94b3]")

    ui.separator().classes("bg-[#292335]")
    ui.label("Policy source").classes("text-xs font-semibold text-[#eceaf4]")
    ui.label(f"Install: {view.source_identity.install_id or 'unknown'}").classes(
        "text-[11px] text-[#6e6584] font-mono break-all"
    )
    ui.label(f"Data dir: {view.source_identity.data_dir or 'unknown'}").classes(
        "text-[11px] text-[#6e6584] font-mono break-all"
    )


def _render_grant_card(
    grant: Any, kind: str, revoke: Callable[[str, str], Awaitable[None]]
) -> None:
    """One grant card with a one-click revoke button."""
    with ui.column().classes(
        "w-full gap-1 bg-[#0e0c13] border border-[#292335] rounded-lg p-3"
    ):
        with ui.row().classes("w-full items-center gap-2"):
            ui.label(grant.spell_name).classes(
                "text-xs font-semibold text-[#eceaf4] font-mono flex-1"
            )
            if grant.scope_label:
                ui.badge(grant.scope_label, color="grey-9").props(
                    "rounded dense"
                ).classes("text-[10px] text-[#9c94b3]")
            ui.button("Revoke", on_click=lambda: revoke(kind, grant.grant_id)).props(
                "flat dense"
            ).classes("text-xs text-[#f87171]").mark(
                f"approval_revoke_{kind}_{grant.grant_id}"
            )
        source = grant.spell
        ui.label(
            f"{source.source_kind or 'unknown'} / {source.source_id or 'unknown'}"
            + (f" ({source.source_scope})" if source.source_scope else "")
        ).classes("text-[11px] text-[#6e6584]")
        if source.code_digest:
            ui.label(f"digest {source.code_digest}").classes(
                "text-[11px] text-[#6e6584] font-mono break-all"
            )
        if grant.project:
            ui.label(f"project {grant.project}").classes(
                "text-[11px] text-[#6e6584] font-mono break-all"
            )
        for label in grant.constraint_labels:
            ui.label(label).classes("text-[11px] text-[#9c94b3]")
        ui.label(f"Last used: {grant.last_used or 'never'}").classes(
            "text-[11px] text-[#6e6584]"
        )


# ---------------------------------------------------------------------------
# Deep link: popup/badge -> the rune's settings dialog
# ---------------------------------------------------------------------------


def find_approval_rune_info(target_dir: Path | None = None) -> dict[str, Any] | None:
    """Find the installed Approval Rune's card dict, if installed."""
    try:
        installed = (
            list_installed_runes(target_dir)
            if target_dir is not None
            else list_installed_runes()
        )
    except Exception:
        logger.warning("Could not list installed runes", exc_info=True)
        return None
    for info in installed:
        if is_approval_rune_name(str(info.get("name", ""))):
            return info
    return None


async def _no_refresh() -> None:
    """No-op on_saved for the deep-linked settings dialog."""


def open_approval_permissions(state: AppState) -> None:
    """Open the Approval Rune's installed-card settings dialog directly."""
    info = find_approval_rune_info()
    if info is None:
        ui.notify("Approval Rune is not installed", type="warning")
        return
    render_rune_settings_dialog(
        state,
        info,
        _no_refresh,
        extra_section=lambda: render_approval_permissions(state),
        wide=True,
    )
