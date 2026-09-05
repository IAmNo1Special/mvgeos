"""User account models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class UserRole(StrEnum):
    """RBAC role for a user account."""

    ADMIN = "admin"
    USER = "user"


@dataclass
class User:
    """Framework-free user account record."""

    id: str
    username: str
    password_hash: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    must_change_password: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_login_at: str | None = None
