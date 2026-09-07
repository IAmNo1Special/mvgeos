"""SQLite persistence for users and sessions."""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mvgeos_gui.core.security import (
    generate_session_token,
    hash_password,
    verify_password,
)
from mvgeos_gui.models.session import Session
from mvgeos_gui.models.user import User, UserRole

_DB_FILENAME = "mvgeos.db"
_DEFAULT_SESSION_TTL = 12 * 60 * 60


def _db_path() -> Path:
    env_path = os.environ.get("MVGEOS_DB_PATH")
    if env_path:
        p = Path(env_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    base = Path(__file__).resolve().parent.parent.parent
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _DB_FILENAME


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they do not exist and seed the default admin."""
    with _get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_activity_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user
                ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires
                ON sessions(expires_at);
        """)
        _seed_admin(conn)


def _seed_admin(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if row:
        return
    import secrets

    user = User(
        id=secrets.token_hex(8),
        username="admin",
        password_hash=hash_password("admin"),
        role=UserRole.ADMIN,
    )
    conn.execute(
        "INSERT INTO users (id, username, password_hash, role, is_active, "
        "must_change_password, created_at, last_login_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user.id,
            user.username,
            user.password_hash,
            user.role.value,
            1 if user.is_active else 0,
            1 if user.must_change_password else 0,
            user.created_at,
            user.last_login_at,
        ),
    )


def get_user_by_username(username: str) -> User | None:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            return None
        return _row_to_user(row)


def get_user_by_id(user_id: str) -> User | None:
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return _row_to_user(row)


def list_users() -> list[User]:
    with _get_connection() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
        return [_row_to_user(r) for r in rows]


def create_user(
    username: str,
    password: str,
    role: UserRole = UserRole.USER,
    must_change_password: bool = False,
) -> User:
    import secrets

    user = User(
        id=secrets.token_hex(8),
        username=username,
        password_hash=hash_password(password),
        role=role,
        must_change_password=must_change_password,
    )
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role, is_active, "
            "must_change_password, created_at, last_login_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user.id,
                user.username,
                user.password_hash,
                user.role.value,
                1 if user.is_active else 0,
                1 if user.must_change_password else 0,
                user.created_at,
                user.last_login_at,
            ),
        )
    return user


def update_user(
    user_id: str,
    *,
    password: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    must_change_password: bool | None = None,
) -> User | None:
    user = get_user_by_id(user_id)
    if not user:
        return None
    if password is not None:
        user.password_hash = hash_password(password)
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    if must_change_password is not None:
        user.must_change_password = must_change_password
    with _get_connection() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, role = ?, is_active = ?, "
            "must_change_password = ? WHERE id = ?",
            (
                user.password_hash,
                user.role.value,
                1 if user.is_active else 0,
                1 if user.must_change_password else 0,
                user.id,
            ),
        )
    return user


def delete_user(user_id: str) -> bool:
    with _get_connection() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return cur.rowcount > 0


def record_login(user_id: str) -> None:
    with _get_connection() as conn:
        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), user_id),
        )


def authenticate_user(username: str, password: str) -> User | None:
    user = get_user_by_username(username)
    if user and user.is_active and verify_password(password, user.password_hash):
        return user
    return None


def create_session(user_id: str, ttl: int = _DEFAULT_SESSION_TTL) -> Session:
    token = generate_session_token()
    now = time.time()
    session = Session(
        token=token,
        user_id=user_id,
        created_at=datetime.fromtimestamp(now, UTC).isoformat(),
        last_activity_at=datetime.fromtimestamp(now, UTC).isoformat(),
        expires_at=datetime.fromtimestamp(now + ttl, UTC).isoformat(),
    )
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, "
            "last_activity_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (
                session.token,
                session.user_id,
                session.created_at,
                session.last_activity_at,
                session.expires_at,
            ),
        )
    return session


def get_session(token: str) -> Session | None:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if not row:
            return None
        return _row_to_session(row)


def refresh_session(token: str, ttl: int = _DEFAULT_SESSION_TTL) -> Session | None:
    session = get_session(token)
    if session is None:
        return None
    now = time.time()
    session.last_activity_at = datetime.fromtimestamp(now, UTC).isoformat()
    session.expires_at = datetime.fromtimestamp(now + ttl, UTC).isoformat()
    with _get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET last_activity_at = ?, expires_at = ? WHERE token = ?",
            (session.last_activity_at, session.expires_at, token),
        )
    return session


def delete_session(token: str) -> bool:
    with _get_connection() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        return cur.rowcount > 0


def cleanup_expired_sessions() -> int:
    now = datetime.now(UTC).isoformat()
    with _get_connection() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        return cur.rowcount


def _row_to_user(row: Any) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        role=UserRole(row["role"]),
        is_active=bool(row["is_active"]),
        must_change_password=bool(row["must_change_password"]),
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )


def _row_to_session(row: Any) -> Session:
    return Session(
        token=row["token"],
        user_id=row["user_id"],
        created_at=row["created_at"],
        last_activity_at=row["last_activity_at"],
        expires_at=row["expires_at"],
    )
