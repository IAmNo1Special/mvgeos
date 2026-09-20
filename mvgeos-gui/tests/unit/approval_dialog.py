"""Unit tests for the approval popup, badge, and permissions screen."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from mvgeos_core.approval import (
    ApprovalOutcome,
    ApprovalRequest,
    ApprovalScope,
)
from nicegui import ui
from nicegui.testing import User

from mvgeos_gui.approval.presenter import ApprovalPresenter
from mvgeos_gui.approval.types import is_approval_rune_name
from mvgeos_gui.components import approval_dialog as approval_dialog_module
from mvgeos_gui.components.approval_dialog import (
    find_approval_rune_info,
    mount_approval_overlay,
    render_approval_badge,
    render_approval_permissions,
)
from mvgeos_gui.state import AppState


def _make_state() -> AppState:
    state = AppState()
    state.project_path = Path("/proj/a")
    return state


def _make_request(**overrides: Any) -> ApprovalRequest:
    kwargs: dict[str, Any] = {
        "cast_id": "call_8b17",
        "spell_name": "shell",
        "spell_identity": {
            "name": "shell",
            "source_kind": "builtin",
            "source_id": "",
            "runner_origin": "false",
            "read_only": "false",
        },
        "arguments": {"command": "git status"},
        "argument_digest": "sha256:def",
        "project_root": "/proj/a",
        "tome_id": "",
        "agent_name": "coding_mvge",
    }
    kwargs.update(overrides)
    return ApprovalRequest(**kwargs)


def _page_with_overlay(state: AppState, path: str) -> None:
    @ui.page(path)
    def page() -> None:
        mount_approval_overlay(state)


def test_approval_surfaces_render_no_markdown_or_html() -> None:
    """Guard: model-controlled strings must never hit ui.markdown/ui.html."""
    source = (
        Path(__file__).parent.parent.parent
        / "src"
        / "mvgeos_gui"
        / "components"
        / "approval_dialog.py"
    )
    text = source.read_text(encoding="utf-8")
    assert "ui.markdown(" not in text
    assert "ui.html(" not in text


@pytest.mark.asyncio
async def test_no_modal_without_active_request(user: User) -> None:
    """The overlay stays empty when the queue has no active request."""
    state = _make_state()
    _page_with_overlay(state, "/test_approval_empty")

    await user.open("/test_approval_empty")
    await user.should_not_see("Approval requested")


@pytest.mark.asyncio
async def test_popup_shows_operation_as_plain_text(user: User) -> None:
    """The popup shows the operation, source, and arguments inertly."""
    state = _make_state()
    state.enqueue_approval(_make_request())
    _page_with_overlay(state, "/test_approval_popup")

    await user.open("/test_approval_popup")
    await user.should_see("Approval requested")
    await user.should_see("shell")
    await user.should_see("git status")
    await user.should_see("builtin")


@pytest.mark.asyncio
async def test_allow_once_resolves_future(user: User) -> None:
    """Allow once is the primary action and resolves the pending cast."""
    state = _make_state()
    future = state.enqueue_approval(_make_request())
    _page_with_overlay(state, "/test_approval_allow")

    await user.open("/test_approval_allow")
    user.find("approval_allow_once_btn").click()
    decision = await asyncio.wait_for(asyncio.ensure_future(future), timeout=5)
    assert decision.outcome is ApprovalOutcome.ALLOW
    assert decision.scope is ApprovalScope.ONCE
    assert decision.request_digest == "sha256:def"


@pytest.mark.asyncio
async def test_deny_once_resolves_future(user: User) -> None:
    """Deny once resolves the pending cast as denied (not a rule)."""
    state = _make_state()
    future = state.enqueue_approval(_make_request())
    _page_with_overlay(state, "/test_approval_deny")

    await user.open("/test_approval_deny")
    user.find("approval_deny_once_btn").click()
    decision = await asyncio.wait_for(asyncio.ensure_future(future), timeout=5)
    assert decision.outcome is ApprovalOutcome.DENY
    assert decision.scope is ApprovalScope.ONCE


@pytest.mark.asyncio
async def test_always_allow_shows_confirmation_with_warning(user: User) -> None:
    """Persistent grants need the confirmation screen stating scope."""
    state = _make_state()
    state.enqueue_approval(_make_request())
    _page_with_overlay(state, "/test_approval_confirm")

    await user.open("/test_approval_confirm")
    user.find("approval_always_allow_btn").click()
    await user.should_see("Always allow")
    await user.should_see("global (all projects)")
    await user.should_see("authorizes every future argument")


@pytest.mark.asyncio
async def test_confirm_grant_resolves_spell_scope(user: User) -> None:
    """Confirming the grant resolves with spell scope bound to the digest."""
    state = _make_state()
    future = state.enqueue_approval(_make_request())
    _page_with_overlay(state, "/test_approval_confirm_grant")

    await user.open("/test_approval_confirm_grant")
    user.find("approval_always_allow_btn").click()
    await user.should_see("global (all projects)")
    user.find("approval_confirm_grant_btn").click()
    decision = await asyncio.wait_for(asyncio.ensure_future(future), timeout=5)
    assert decision.outcome is ApprovalOutcome.ALLOW
    assert decision.scope is ApprovalScope.SPELL
    assert decision.request_digest == "sha256:def"


@pytest.mark.asyncio
async def test_session_approval_confirmation(user: User) -> None:
    """Approve-all-session confirms the temporary scope before resolving."""
    state = _make_state()
    future = state.enqueue_approval(_make_request())
    _page_with_overlay(state, "/test_approval_session")

    await user.open("/test_approval_session")
    user.find("approval_session_btn").click()
    await user.should_see("mutating casts this session")
    user.find("approval_confirm_grant_btn").click()
    decision = await asyncio.wait_for(asyncio.ensure_future(future), timeout=5)
    assert decision.outcome is ApprovalOutcome.ALLOW
    assert decision.scope is ApprovalScope.SESSION


@pytest.mark.asyncio
async def test_project_approval_confirmation_shows_scope_warning(user: User) -> None:
    """Project approval states the not-a-sandbox scope warning."""
    state = _make_state()
    future = state.enqueue_approval(_make_request())
    _page_with_overlay(state, "/test_approval_project")

    await user.open("/test_approval_project")
    user.find("approval_project_btn").click()
    await user.should_see("not a filesystem sandbox")
    user.find("approval_confirm_grant_btn").click()
    decision = await asyncio.wait_for(asyncio.ensure_future(future), timeout=5)
    assert decision.outcome is ApprovalOutcome.ALLOW
    assert decision.scope is ApprovalScope.PROJECT


@pytest.mark.asyncio
async def test_always_deny_confirmation(user: User) -> None:
    """Always-deny confirms that deny outranks every approval scope."""
    state = _make_state()
    future = state.enqueue_approval(_make_request())
    _page_with_overlay(state, "/test_approval_always_deny")

    await user.open("/test_approval_always_deny")
    user.find("approval_always_deny_btn").click()
    await user.should_see("overrides every approval")
    user.find("approval_confirm_grant_btn").click()
    decision = await asyncio.wait_for(asyncio.ensure_future(future), timeout=5)
    assert decision.outcome is ApprovalOutcome.DENY
    assert decision.scope is ApprovalScope.SPELL


@pytest.mark.asyncio
async def test_manage_permissions_deep_link(
    user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The popup deep-links straight to the rune's settings dialog."""
    monkeypatch.setattr(
        approval_dialog_module,
        "find_approval_rune_info",
        lambda target_dir=None: {
            "name": "approval-rune",
            "version": "0.1.0",
            "description": "Test approval rune",
            "path": "/tmp/approval-rune",
        },
    )
    state = _make_state()
    state.enqueue_approval(_make_request())
    _page_with_overlay(state, "/test_approval_deeplink")

    await user.open("/test_approval_deeplink")
    user.find("approval_manage_permissions_btn").click()
    await user.should_see("approval-rune Settings")
    await user.should_see("Approval permissions")


@pytest.mark.asyncio
async def test_badge_visible_while_session_active(user: User) -> None:
    """The persistent badge shows while session approve-all is active."""

    @ui.page("/test_approval_badge_on")
    def page_on() -> None:
        state = _make_state()
        state.set_approval_session_badge(True)
        render_approval_badge(state)

    @ui.page("/test_approval_badge_off")
    def page_off() -> None:
        render_approval_badge(_make_state())

    await user.open("/test_approval_badge_on")
    await user.should_see("Session approval active")
    await user.open("/test_approval_badge_off")
    await user.should_not_see("Session approval active")


class _FakeApprovalRune:
    """Test double for the rune's frozen permissions interface."""

    def __init__(self, warnings: list[str] | None = None) -> None:
        self.revoked: list[tuple[str, str]] = []
        self._warnings = warnings or []

    def get_permissions_view(self) -> dict[str, Any]:
        return {
            "session": {"session_id": "s1", "approve_all_active": True},
            "trusted_projects": [
                {
                    "id": "project:/proj/a",
                    "root": "/proj/a",
                    "enabled": True,
                }
            ],
            "always_allowed": [
                {
                    "id": "g1",
                    "spell": {
                        "name": "write",
                        "source_kind": "builtin",
                        "source_id": "coding_mvge",
                        "source_scope": "agent",
                        "code_digest": "sha256:abc",
                    },
                    "project": None,
                    "scope_label": "global",
                    "constraints": [{"field": "path", "op": "path_within_project"}],
                    "constraint_labels": ["path stays inside the project"],
                    "last_used": "2026-09-20T12:00:00Z",
                }
            ],
            "never_allowed": [
                {
                    "id": "d1",
                    "spell": {
                        "name": "deploy",
                        "source_kind": "builtin",
                        "source_id": "ops",
                        "source_scope": "agent",
                    },
                    "project": None,
                    "last_used": None,
                }
            ],
            "source_identity": {
                "install_id": "uuid-1",
                "data_dir": "/home/user/.local/share/mvgeos/approval",
            },
            "recent_activity": [
                {
                    "timestamp": "2026-09-20T12:01:00Z",
                    "cast_id": "call_1",
                    "spell_name": "shell",
                    "decision": "allow",
                    "scope": "once",
                    "reason_code": "user",
                    "project": "/proj/a",
                }
            ],
            "warnings": self._warnings,
        }

    def revoke_grant(self, kind: str, grant_id: str) -> bool:
        self.revoked.append((kind, grant_id))
        return True


def _state_with_rune(
    warnings: list[str] | None = None,
) -> tuple[AppState, _FakeApprovalRune]:
    state = _make_state()
    presenter = ApprovalPresenter(state)
    rune = _FakeApprovalRune(warnings=warnings)
    presenter.set_permissions_source(rune)
    state._approval_presenter = presenter
    return state, rune


@pytest.mark.asyncio
async def test_permissions_screen_shows_grants(user: User) -> None:
    """The permissions screen lists session state, projects, and grants."""
    state, _ = _state_with_rune()

    @ui.page("/test_approval_permissions")
    def page() -> None:
        render_approval_permissions(state)

    await user.open("/test_approval_permissions")
    await user.should_see("Approval permissions")
    await user.should_see("/proj/a")
    await user.should_see("write")
    await user.should_see("deploy")
    await user.should_see("path stays inside the project")
    await user.should_see("2026-09-20T12:00:00Z")
    await user.should_see("Recent activity")
    await user.should_see("shell")


@pytest.mark.asyncio
async def test_permissions_revoke_calls_rune(user: User) -> None:
    """One-click revoke forwards kind and grant id to the rune."""
    state, rune = _state_with_rune()

    @ui.page("/test_approval_revoke")
    def page() -> None:
        render_approval_permissions(state)

    await user.open("/test_approval_revoke")
    await user.should_see("write")
    user.find("approval_revoke_allow_rule_g1").click()
    await asyncio.sleep(0.2)
    assert ("allow_rule", "g1") in rune.revoked


@pytest.mark.asyncio
async def test_permissions_unavailable_without_rune(user: User) -> None:
    """Without a rune attached the screen degrades to unavailable."""
    state = _make_state()

    @ui.page("/test_approval_permissions_missing")
    def page() -> None:
        render_approval_permissions(state)

    await user.open("/test_approval_permissions_missing")
    await user.should_see("unavailable")


@pytest.mark.asyncio
async def test_permissions_screen_shows_warnings(user: User) -> None:
    """Rune warnings surface loudly at the top of the permissions screen."""
    state, _ = _state_with_rune(warnings=["policy file was reset"])

    @ui.page("/test_approval_warnings")
    def page() -> None:
        render_approval_permissions(state)

    await user.open("/test_approval_warnings")
    await user.should_see("policy file was reset")


def test_find_approval_rune_info_missing() -> None:
    """find_approval_rune_info returns None when no approval rune exists."""
    assert find_approval_rune_info(target_dir=Path("/nonexistent")) is None


def test_find_approval_rune_info_from_manifest(tmp_path: Path) -> None:
    """find_approval_rune_info reads the rune name from manifest.json."""
    import json

    rune_dir = tmp_path / "approval-rune"
    rune_dir.mkdir()
    (rune_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "approval-rune",
                "type": "Rune",
                "version": "0.1.0",
                "description": "Test rune",
            }
        ),
        encoding="utf-8",
    )
    info = find_approval_rune_info(target_dir=tmp_path)
    assert info is not None
    assert info["name"] == "approval-rune"
    assert info["version"] == "0.1.0"


def test_is_approval_rune_name_detection() -> None:
    """The name detector tolerates case and separators."""
    assert is_approval_rune_name("approval-rune")
    assert is_approval_rune_name("Approval_Rune")
    assert not is_approval_rune_name("session-title")
    assert not is_approval_rune_name(None)


@pytest.mark.asyncio
async def test_popup_warns_on_unvalidated_arguments(user: User) -> None:
    """A schemaless cast shows the unvalidated-arguments warning banner."""
    state = _make_state()
    state.enqueue_approval(_make_request(schema_validated=False))
    _page_with_overlay(state, "/test_approval_unvalidated")

    await user.open("/test_approval_unvalidated")
    await user.should_see("Approval requested")
    await user.should_see("Unvalidated arguments")


@pytest.mark.asyncio
async def test_popup_hides_warning_for_validated_cast(user: User) -> None:
    """A schema-validated cast shows no unvalidated-arguments warning."""
    state = _make_state()
    state.enqueue_approval(_make_request(schema_validated=True))
    _page_with_overlay(state, "/test_approval_validated")

    await user.open("/test_approval_validated")
    await user.should_see("Approval requested")
    await user.should_not_see("Unvalidated arguments")
