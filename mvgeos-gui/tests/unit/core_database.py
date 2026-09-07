"""Unit tests for SQLite database operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from mvgeos_gui.core.database import (
    authenticate_user,
    cleanup_expired_sessions,
    create_session,
    create_user,
    delete_session,
    delete_user,
    get_session,
    get_user_by_id,
    get_user_by_username,
    init_db,
    list_users,
    record_login,
    refresh_session,
    update_user,
)
from mvgeos_gui.models.user import UserRole


@pytest.fixture(autouse=True)
def setup_isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "test_mvgeos.db"
    monkeypatch.setenv("MVGEOS_DB_PATH", str(db_file))
    init_db()


def test_init_db_seeds_admin() -> None:
    admin = get_user_by_username("admin")
    assert admin is not None
    assert admin.username == "admin"
    assert admin.role == UserRole.ADMIN
    # Calling init_db again is idempotent
    init_db()


def test_user_crud() -> None:
    user = create_user("alice", "alice-pass", role=UserRole.USER)
    assert user.username == "alice"
    assert user.role == UserRole.USER

    by_name = get_user_by_username("alice")
    assert by_name is not None
    assert by_name.id == user.id

    by_id = get_user_by_id(user.id)
    assert by_id is not None
    assert by_id.username == "alice"

    assert get_user_by_username("nonexistent") is None
    assert get_user_by_id("nonexistent-id") is None

    # List users
    users = list_users()
    assert len(users) >= 2
    assert any(u.username == "alice" for u in users)

    # Update user
    updated = update_user(
        user.id,
        password="new-password",
        role=UserRole.ADMIN,
        is_active=False,
        must_change_password=True,
    )
    assert updated is not None
    assert updated.role == UserRole.ADMIN
    assert updated.is_active is False
    assert updated.must_change_password is True

    # Update non-existent user
    assert update_user("fake-id", password="p") is None

    # Record login
    record_login(user.id)
    refetched = get_user_by_id(user.id)
    assert refetched is not None
    assert refetched.last_login_at is not None

    # Delete user
    assert delete_user(user.id) is True
    assert delete_user("fake-id") is False
    assert get_user_by_id(user.id) is None


def test_authenticate_user() -> None:
    create_user("bob", "bob-pass")
    auth_success = authenticate_user("bob", "bob-pass")
    assert auth_success is not None
    assert auth_success.username == "bob"

    assert authenticate_user("bob", "wrong-pass") is None
    assert authenticate_user("nonexistent", "pass") is None

    # Deactivated user cannot authenticate
    user = get_user_by_username("bob")
    assert user is not None
    update_user(user.id, is_active=False)
    assert authenticate_user("bob", "bob-pass") is None


def test_session_lifecycle() -> None:
    admin = get_user_by_username("admin")
    assert admin is not None

    session = create_session(admin.id, ttl=3600)
    assert session.user_id == admin.id

    fetched = get_session(session.token)
    assert fetched is not None
    assert fetched.token == session.token

    assert get_session("nonexistent-token") is None

    refreshed = refresh_session(session.token, ttl=7200)
    assert refreshed is not None
    assert refreshed.expires_at >= session.expires_at

    assert refresh_session("fake-token") is None

    assert delete_session(session.token) is True
    assert delete_session("fake-token") is False
    assert get_session(session.token) is None


def test_cleanup_expired_sessions() -> None:
    admin = get_user_by_username("admin")
    assert admin is not None

    # Create expired session
    create_session(admin.id, ttl=-100)
    # Create active session
    active = create_session(admin.id, ttl=3600)

    cleaned = cleanup_expired_sessions()
    assert cleaned >= 1
    assert get_session(active.token) is not None
