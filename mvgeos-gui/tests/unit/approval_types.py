"""Unit tests for the approval GUI types module."""

from __future__ import annotations

from mvgeos_core.approval import (
    ApprovalDecision,
    ApprovalOutcome,
    ApprovalReasonCode,
    ApprovalRequest,
    ApprovalScope,
)

from mvgeos_gui.approval.types import (
    PermissionsView,
    describe_operation,
    is_approval_rune_name,
    is_mutating_request,
    spell_source_label,
)


def _request_kwargs() -> dict:
    return {
        "cast_id": "call_8b17",
        "spell_name": "write",
        "spell_identity": {
            "name": "write",
            "source_kind": "builtin",
            "source_id": "",
            "runner_origin": "false",
            "read_only": "false",
        },
        "arguments": {"path": "/tmp/x.txt", "content": "[redacted]"},
        "argument_digest": "sha256:def",
        "project_root": "/workspace/mvgeos",
        "tome_id": "7f24",
        "agent_name": "coding_mvge",
    }


def test_canonical_types_are_reexported() -> None:
    """The GUI uses the engine's canonical request/decision types."""
    req = ApprovalRequest(**_request_kwargs())
    assert req.cast_id == "call_8b17"
    assert req.arguments["path"] == "/tmp/x.txt"
    decision = ApprovalDecision(
        outcome=ApprovalOutcome.ALLOW,
        scope=ApprovalScope.ONCE,
        reason_code=ApprovalReasonCode.USER,
        request_digest=req.argument_digest,
    )
    assert decision.outcome is ApprovalOutcome.ALLOW
    assert decision.request_digest == req.argument_digest


def test_describe_operation_prefers_path_argument() -> None:
    """The one-line summary leads with a path-like argument."""
    req = ApprovalRequest(**_request_kwargs())
    assert describe_operation(req) == "write /tmp/x.txt"


def test_describe_operation_falls_back_to_arguments() -> None:
    """Without a path, the summary renders the frozen arguments."""
    kwargs = _request_kwargs()
    kwargs["spell_name"] = "shell"
    kwargs["arguments"] = {"command": "ls"}
    req = ApprovalRequest(**kwargs)
    assert describe_operation(req) == 'shell {"command": "ls"}'


def test_describe_operation_bare_spell() -> None:
    """A cast with no arguments renders as just the spell name."""
    kwargs = _request_kwargs()
    kwargs["arguments"] = {}
    req = ApprovalRequest(**kwargs)
    assert describe_operation(req) == "write"


def test_is_mutating_request_reads_engine_flag() -> None:
    """Mutating detection uses the engine's read_only identity flag."""
    req = ApprovalRequest(**_request_kwargs())
    assert is_mutating_request(req) is True
    kwargs = _request_kwargs()
    kwargs["spell_identity"] = {**kwargs["spell_identity"], "read_only": "true"}
    assert is_mutating_request(ApprovalRequest(**kwargs)) is False


def test_spell_source_label() -> None:
    """Source attribution renders from the engine-derived identity."""
    req = ApprovalRequest(**_request_kwargs())
    assert spell_source_label(req) == "builtin"
    kwargs = _request_kwargs()
    kwargs["spell_identity"] = {
        "name": "search",
        "source_kind": "rune",
        "source_id": "seeker",
        "runner_origin": "true",
        "read_only": "true",
    }
    assert spell_source_label(ApprovalRequest(**kwargs)) == "rune / seeker"


def test_is_approval_rune_name() -> None:
    """Approval rune detection is case-insensitive and dash/underscore tolerant."""
    assert is_approval_rune_name("approval-rune")
    assert is_approval_rune_name("Approval_Rune")
    assert is_approval_rune_name("mvgeos-approval-rune")
    assert not is_approval_rune_name("seeker")
    assert not is_approval_rune_name("")


def test_permissions_view_from_dict() -> None:
    """PermissionsView parses the rune's frozen plain-data dict shape."""
    view = PermissionsView.from_dict(
        {
            "session": {"session_id": "s1", "approve_all_active": True},
            "trusted_projects": [
                {
                    "id": "project:/workspace/mvgeos",
                    "root": "/workspace/mvgeos",
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
                    "spell": {"name": "deploy", "source_id": "ops"},
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
                    "project": "/workspace/mvgeos",
                }
            ],
            "warnings": ["policy file was reset"],
        }
    )
    assert view is not None
    assert view.session_approve_all is True
    assert view.session_id == "s1"
    assert len(view.trusted_projects) == 1
    assert view.trusted_projects[0].grant_id == "project:/workspace/mvgeos"
    assert view.trusted_projects[0].root == "/workspace/mvgeos"
    assert len(view.always_allowed) == 1
    grant = view.always_allowed[0]
    assert grant.grant_id == "g1"
    assert grant.spell_name == "write"
    assert grant.scope_label == "global"
    assert grant.constraints[0]["op"] == "path_within_project"
    assert grant.constraint_labels == ["path stays inside the project"]
    assert grant.last_used == "2026-09-20T12:00:00Z"
    assert len(view.never_allowed) == 1
    assert view.never_allowed[0].spell_name == "deploy"
    assert view.never_allowed[0].spell.code_digest is None
    assert view.source_identity.install_id == "uuid-1"
    assert view.source_identity.data_dir == "/home/user/.local/share/mvgeos/approval"
    assert len(view.recent_activity) == 1
    assert view.recent_activity[0].spell_name == "shell"
    assert view.recent_activity[0].decision == "allow"
    assert view.warnings == ["policy file was reset"]


def test_permissions_view_from_dict_rejects_garbage() -> None:
    """from_dict returns None for non-dict or empty payloads."""
    assert PermissionsView.from_dict(None) is None
    assert PermissionsView.from_dict({}) is None
    assert PermissionsView.from_dict("nope") is None


def test_permissions_view_tolerates_missing_sections() -> None:
    """Missing optional sections degrade to empty, not to errors."""
    view = PermissionsView.from_dict({"session": {"approve_all_active": False}})
    assert view is not None
    assert view.always_allowed == []
    assert view.never_allowed == []
    assert view.trusted_projects == []
    assert view.recent_activity == []
    assert view.warnings == []
    assert view.session_approve_all is False
    assert view.source_identity.data_dir == ""
