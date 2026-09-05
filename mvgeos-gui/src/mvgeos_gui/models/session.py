"""Session models for authenticated user sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Session:
    """An authenticated user session."""

    token: str
    user_id: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_activity_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
