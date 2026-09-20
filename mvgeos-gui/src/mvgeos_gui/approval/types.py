"""Approval Rune GUI types.

The approval flow uses the canonical ``mvgeos_core.approval`` types
end-to-end: the engine invokes the presenter as ``await presenter(request)``
with a canonical ``ApprovalRequest`` and isinstance-checks the returned
``ApprovalDecision``. This module re-exports those canonical types and
adds GUI-only helpers: display text derived from the engine-provided
request (the GUI never invents grant/constraint vocabulary), the
approval-rune name predicate, and the frozen permissions-view contract
used by the settings-cog screen.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from mvgeos_core.approval import (
    ApprovalDecision,
    ApprovalOutcome,
    ApprovalPresenter,
    ApprovalReasonCode,
    ApprovalRequest,
    ApprovalScope,
)

__all__ = [
    "APPROVAL_RUNE_NAME",
    "ApprovalDecision",
    "ApprovalOutcome",
    "ApprovalPresenter",
    "ApprovalReasonCode",
    "ApprovalRequest",
    "ApprovalScope",
    "ActivityRecord",
    "PermissionsView",
    "SourceIdentity",
    "SpellGrant",
    "SpellIdentity",
    "TrustedProject",
    "describe_operation",
    "is_approval_rune_name",
    "is_mutating_request",
    "spell_source_label",
]

#: Canonical marketplace name of the Approval Rune.
APPROVAL_RUNE_NAME = "approval-rune"


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read *name* from a dict or an attribute-style object."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def describe_operation(request: ApprovalRequest) -> str:
    """One-line human summary of the cast, derived from engine fields.

    Prefers a path-like argument; otherwise renders the frozen arguments
    compactly. Display only: the rune owns policy matching.
    """
    args = request.arguments
    path = args.get("path") or args.get("file") or args.get("target")
    if isinstance(path, str) and path:
        return f"{request.spell_name} {path}"
    if args:
        rendered = json.dumps(dict(args), sort_keys=True, default=str)
        if len(rendered) > 120:
            rendered = rendered[:117] + "..."
        return f"{request.spell_name} {rendered}"
    return request.spell_name


def is_mutating_request(request: ApprovalRequest) -> bool:
    """Whether the cast may mutate state (engine-derived read_only flag)."""
    return request.spell_identity.get("read_only", "") != "true"


def spell_source_label(request: ApprovalRequest) -> str:
    """Engine-derived spell attribution for display (never policy)."""
    identity = request.spell_identity
    source_kind = identity.get("source_kind", "")
    source_id = identity.get("source_id", "")
    if source_kind == "rune" and source_id:
        return f"{source_kind} / {source_id}"
    return source_kind or "unknown"


def is_approval_rune_name(name: str | None) -> bool:
    """Detect the Approval Rune by manifest name, tolerantly."""
    if not name:
        return False
    normalized = name.lower().replace("_", "-")
    return "approval" in normalized


@dataclass
class SpellIdentity:
    """Engine-derived spell identity for one grant or denial rule."""

    name: str = ""
    source_kind: str = ""
    source_id: str = ""
    source_scope: str | None = None
    code_digest: str | None = None

    @classmethod
    def from_any(cls, obj: Any) -> SpellIdentity:
        """Parse from a dict or attribute-style object."""
        if obj is None:
            return cls()
        return cls(
            name=str(_get(obj, "name", "") or ""),
            source_kind=str(_get(obj, "source_kind", "") or ""),
            source_id=str(_get(obj, "source_id", "") or ""),
            source_scope=_get(obj, "source_scope"),
            code_digest=_get(obj, "code_digest"),
        )


@dataclass
class SpellGrant:
    """One always-allowed or never-allowed rule shown on the permissions screen.

    Mirrors the Approval Rune's frozen permissions-view contract: the rune
    supplies human-readable ``constraint_labels`` and ``scope_label``; the
    GUI never invents its own constraint vocabulary.
    """

    grant_id: str = ""
    spell: SpellIdentity = field(default_factory=SpellIdentity)
    project: str | None = None
    scope_label: str = ""
    constraints: list[Mapping[str, Any]] = field(default_factory=list)
    constraint_labels: list[str] = field(default_factory=list)
    last_used: str | None = None

    @property
    def spell_name(self) -> str:
        """Convenience accessor for the granted spell's display name."""
        return self.spell.name

    @classmethod
    def from_any(cls, obj: Any) -> SpellGrant:
        """Parse from a dict or attribute-style object."""
        if obj is None:
            return cls()
        constraints = _get(obj, "constraints", []) or []
        labels = _get(obj, "constraint_labels", []) or []
        return cls(
            grant_id=str(_get(obj, "id", "") or ""),
            spell=SpellIdentity.from_any(_get(obj, "spell")),
            project=_get(obj, "project"),
            scope_label=str(_get(obj, "scope_label", "") or ""),
            constraints=[dict(c) for c in constraints],
            constraint_labels=[str(label) for label in labels],
            last_used=_get(obj, "last_used"),
        )


@dataclass
class TrustedProject:
    """One project carrying a persistent approve-all grant."""

    grant_id: str = ""
    root: str = ""
    enabled: bool = True

    @classmethod
    def from_any(cls, obj: Any) -> TrustedProject:
        """Parse from a dict or attribute-style object."""
        if obj is None:
            return cls()
        root = str(_get(obj, "root", "") or "")
        grant_id = str(_get(obj, "id", "") or "") or f"project:{root}"
        return cls(
            grant_id=grant_id,
            root=root,
            enabled=bool(_get(obj, "enabled", True)),
        )


@dataclass
class SourceIdentity:
    """Which rune installation and data directory own the policy."""

    install_id: str | None = None
    data_dir: str = ""

    @classmethod
    def from_any(cls, obj: Any) -> SourceIdentity:
        """Parse from a dict or attribute-style object."""
        if obj is None:
            return cls()
        return cls(
            install_id=_get(obj, "install_id"),
            data_dir=str(_get(obj, "data_dir", "") or ""),
        )


@dataclass
class ActivityRecord:
    """One audited gate decision for the recent-activity section."""

    timestamp: str | None = None
    cast_id: str = ""
    spell_name: str = ""
    decision: str = ""
    scope: str = ""
    reason_code: str = ""
    project: str | None = None

    @classmethod
    def from_any(cls, obj: Any) -> ActivityRecord:
        """Parse from a dict or attribute-style object."""
        if obj is None:
            return cls()
        return cls(
            timestamp=_get(obj, "timestamp"),
            cast_id=str(_get(obj, "cast_id", "") or ""),
            spell_name=str(_get(obj, "spell_name", "") or ""),
            decision=str(_get(obj, "decision", "") or ""),
            scope=str(_get(obj, "scope", "") or ""),
            reason_code=str(_get(obj, "reason_code", "") or ""),
            project=_get(obj, "project"),
        )


@dataclass
class PermissionsView:
    """Parsed form of the Approval Rune's frozen ``get_permissions_view()``.

    Contract (frozen by the Approval Rune package; any change goes through
    the coordinator, never silently): keys ``session`` (``session_id``,
    ``approve_all_active``), ``trusted_projects`` (``id``/``root``/
    ``enabled``), ``always_allowed`` (``id``/``spell``/``project``/
    ``scope_label``/``constraints``/``constraint_labels``/``last_used``),
    ``never_allowed`` (``id``/``spell``/``project``/``last_used``),
    ``source_identity`` (``install_id``/``data_dir``), ``recent_activity``,
    and ``warnings``. Missing sections degrade to empties; a non-dict or
    empty payload yields None so the screen shows its unavailable state.
    """

    session_id: str | None = None
    session_approve_all: bool = False
    trusted_projects: list[TrustedProject] = field(default_factory=list)
    always_allowed: list[SpellGrant] = field(default_factory=list)
    never_allowed: list[SpellGrant] = field(default_factory=list)
    source_identity: SourceIdentity = field(default_factory=SourceIdentity)
    recent_activity: list[ActivityRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> PermissionsView | None:
        """Parse the rune's plain-data dict; None when unusable."""
        if not isinstance(data, Mapping) or not data:
            return None
        session = data.get("session") or {}
        if not isinstance(session, Mapping):
            session = {}
        return cls(
            session_id=session.get("session_id"),
            session_approve_all=bool(session.get("approve_all_active", False)),
            trusted_projects=[
                TrustedProject.from_any(p) for p in (data.get("trusted_projects") or [])
            ],
            always_allowed=[
                SpellGrant.from_any(g) for g in (data.get("always_allowed") or [])
            ],
            never_allowed=[
                SpellGrant.from_any(g) for g in (data.get("never_allowed") or [])
            ],
            source_identity=SourceIdentity.from_any(data.get("source_identity")),
            recent_activity=[
                ActivityRecord.from_any(r) for r in (data.get("recent_activity") or [])
            ],
            warnings=[str(w) for w in (data.get("warnings") or [])],
        )
