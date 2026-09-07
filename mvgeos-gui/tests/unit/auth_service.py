"""Unit tests for AuthService."""

from __future__ import annotations

from pathlib import Path

import pytest

from mvgeos_gui.core.database import init_db
from mvgeos_gui.core.security import login_limiter
from mvgeos_gui.models.user import UserRole
from mvgeos_gui.services.auth_service import AuthService


@pytest.fixture(autouse=True)
def setup_isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "test_auth_service.db"
    monkeypatch.setenv("MVGEOS_DB_PATH", str(db_file))
    init_db()
    login_limiter._attempts.clear()
    login_limiter._locked_until.clear()


def test_auth_service_login_and_logout() -> None:
    service = AuthService()
    assert service.is_authenticated() is False
    assert service.get_current_user() is None
    assert service.get_current_session() is None

    # Failed login
    assert service.login("admin", "wrong-password") is None
    assert service.is_authenticated() is False

    # Successful login
    user = service.login("admin", "admin")
    assert user is not None
    assert user.username == "admin"
    assert service.is_authenticated() is True
    assert service.get_current_user() == user
    assert service.get_current_session() is not None

    # Logout
    service.logout()
    assert service.is_authenticated() is False
    assert service.get_current_user() is None
    assert service.get_current_session() is None


def test_auth_service_rate_limiting() -> None:
    service = AuthService()
    for _ in range(5):
        service.login("admin", "wrong")

    # 6th attempt is locked
    assert service.login("admin", "wrong") is None


def test_auth_service_require_admin() -> None:
    service = AuthService()
    assert service.require_admin() is None

    service.register("normal_user", "pass123")
    service.login("normal_user", "pass123")
    assert service.require_admin() is None

    service.login("admin", "admin")
    assert service.require_admin() is not None


def test_auth_service_user_management() -> None:
    service = AuthService()
    service.login("admin", "admin")

    # Create user account
    user = service.create_user_account(
        "carol", "carolpass", role=UserRole.USER, must_change_password=True
    )
    assert user.username == "carol"

    # List all users
    users = service.list_all_users()
    assert any(u.username == "carol" for u in users)

    # Change password
    updated = service.change_password(user.id, "newcarolpass")
    assert updated is not None

    # Update account
    updated2 = service.update_user_account(
        user.id, role=UserRole.ADMIN, is_active=True, must_change_password=False
    )
    assert updated2 is not None
    assert updated2.role == UserRole.ADMIN

    # Cannot delete self
    admin_user = service.get_current_user()
    assert admin_user is not None
    assert service.delete_user_account(admin_user.id) is False

    # Can delete other user
    assert service.delete_user_account(user.id) is True


def test_auth_service_auto_initializes_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh_db = tmp_path / "fresh_uninitialized.db"
    monkeypatch.setenv("MVGEOS_DB_PATH", str(fresh_db))
    # Note: init_db is NOT called here
    service = AuthService()
    user = service.login("admin", "admin")
    assert user is not None
    assert user.username == "admin"
