"""Unit tests for core security primitives."""

from __future__ import annotations

import time

from mvgeos_gui.core.security import (
    RateLimiter,
    generate_session_token,
    hash_password,
    verify_password,
)


def test_hash_password_format_and_verification() -> None:
    hashed = hash_password("secret-password")
    assert hashed.startswith("pbkdf2_sha256$260000$")
    assert verify_password("secret-password", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_verify_password_malformed_hashes() -> None:
    assert verify_password("pass", "invalid_hash") is False
    assert verify_password("pass", "other_algo$1000$abcd$1234") is False
    assert verify_password("pass", "pbkdf2_sha256$not_int$abcd$1234") is False
    assert verify_password("pass", "pbkdf2_sha256$1000$not_hex$1234") is False


def test_generate_session_token() -> None:
    t1 = generate_session_token()
    t2 = generate_session_token()
    assert len(t1) > 20
    assert t1 != t2


def test_rate_limiter_lockout_and_reset() -> None:
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)
    key = "user-123"

    assert limiter.is_locked(key) is False
    assert limiter.record_attempt(key) is False
    assert limiter.record_attempt(key) is False
    assert limiter.record_attempt(key) is True
    assert limiter.is_locked(key) is True

    limiter.reset(key)
    assert limiter.is_locked(key) is False


def test_rate_limiter_prune_expired() -> None:
    limiter = RateLimiter(max_attempts=3, window_seconds=1, lockout_seconds=1)
    key = "user-abc"

    limiter.record_attempt(key)
    # Simulate time passing
    limiter._attempts[key] = [time.time() - 10]
    limiter._last_prune = time.time() - 100

    assert limiter.is_locked(key) is False
    assert len(limiter._attempts.get(key, [])) == 0
