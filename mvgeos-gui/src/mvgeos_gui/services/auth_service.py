"""User and session management service."""

from __future__ import annotations

import logging

from mvgeos_gui.core.database import (
    authenticate_user,
    create_session,
    create_user,
    delete_session,
    delete_user,
    get_session,
    list_users,
    record_login,
    update_user,
)
from mvgeos_gui.core.security import login_limiter
from mvgeos_gui.models.session import Session
from mvgeos_gui.models.user import User, UserRole

logger = logging.getLogger(__name__)

_SESSION_IDLE_TTL = 30 * 60
_SESSION_ABSOLUTE_TTL = 12 * 60 * 60


class AuthService:
    """Business logic for user accounts and session management."""

    def __init__(self) -> None:
        self._current_session: Session | None = None
        self._current_user: User | None = None

    def login(self, username: str, password: str) -> User | None:
        """Authenticate and return the user on success, None on failure."""
        if login_limiter.is_locked(username):
            logger.warning("Login attempt locked for username=%s", username)
            return None
        user = authenticate_user(username, password)
        if user is None:
            login_limiter.record_attempt(username)
            logger.info("Failed login for username=%s", username)
            return None
        self._current_user = user
        self._current_session = create_session(user.id)
        record_login(user.id)
        login_limiter.reset(username)
        logger.info("Successful login user=%s id=%s", user.username, user.id)
        return user

    def logout(self) -> None:
        if self._current_session:
            delete_session(self._current_session.token)
        self._current_session = None
        self._current_user = None
        logger.info("User logged out")

    def get_current_user(self) -> User | None:
        return self._current_user

    def get_current_session(self) -> Session | None:
        if self._current_session is None:
            return None
        refreshed = get_session(self._current_session.token)
        if refreshed is None:
            self._current_session = None
            self._current_user = None
            return None
        self._current_session = refreshed
        return refreshed

    def is_authenticated(self) -> bool:
        return self.get_current_session() is not None

    def require_admin(self) -> User | None:
        user = self._current_user
        if user and user.role == UserRole.ADMIN:
            return user
        return None

    def register(self, username: str, password: str) -> User:
        return create_user(username, password)

    def change_password(self, user_id: str, new_password: str) -> User | None:
        return update_user(user_id, password=new_password)

    def create_user_account(
        self,
        username: str,
        password: str,
        role: UserRole = UserRole.USER,
        must_change_password: bool = False,
    ) -> User:
        return create_user(username, password, role, must_change_password)

    def update_user_account(
        self,
        user_id: str,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
        must_change_password: bool | None = None,
    ) -> User | None:
        return update_user(
            user_id,
            role=role,
            is_active=is_active,
            must_change_password=must_change_password,
        )

    def delete_user_account(self, user_id: str) -> bool:
        if self._current_user and self._current_user.id == user_id:
            return False
        return delete_user(user_id)

    def list_all_users(self) -> list[User]:
        return list_users()
