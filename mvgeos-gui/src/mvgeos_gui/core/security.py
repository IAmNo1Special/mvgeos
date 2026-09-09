"""Security primitives: password hashing, session tokens, rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field

_PBKDF2_ITERATIONS = 260_000
_SALT_SIZE = 16
_TOKEN_SIZE = 32
_RATE_LIMIT_WINDOW = 15 * 60
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_LOCKOUT = 30 * 60


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256.

    Returns a string of the form ``pbkdf2_sha256$iterations$salt$hash``.
    """
    salt = os.urandom(_SALT_SIZE)
    p_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${p_hash.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a plaintext password against a stored hash.

    Uses ``hmac.compare_digest`` for constant-time comparison.
    """
    try:
        algo, iterations_str, salt_hex, hash_hex = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False

    p_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(p_hash, expected)


def generate_session_token() -> str:
    """Return a cryptographically secure session token."""
    return secrets.token_urlsafe(_TOKEN_SIZE)


@dataclass
class RateLimiter:
    """In-memory sliding-window rate limiter.

    Tracks attempts per key over a fixed window; after ``max_attempts`` the
    key is locked out for ``lockout_seconds``.  Stale entries are pruned
    periodically to bound memory use.
    """

    max_attempts: int = _RATE_LIMIT_MAX
    window_seconds: int = _RATE_LIMIT_WINDOW
    lockout_seconds: int = _RATE_LIMIT_LOCKOUT
    _attempts: dict[str, list[float]] = field(default_factory=dict, repr=False)
    _locked_until: dict[str, float] = field(default_factory=dict, repr=False)
    _last_prune: float = field(default_factory=time.time, repr=False)

    def _prune(self) -> None:
        now = time.time()
        if now - self._last_prune < 60:
            return
        self._last_prune = now
        cutoff = now - self.window_seconds
        self._attempts = {
            k: [t for t in v if t > cutoff]
            for k, v in self._attempts.items()
            if v and max(v) > cutoff
        }
        self._locked_until = {k: t for k, t in self._locked_until.items() if t > now}

    def is_locked(self, key: str) -> bool:
        self._prune()
        return time.time() < self._locked_until.get(key, 0.0)

    def record_attempt(self, key: str) -> bool:
        """Record a failed attempt.

        Returns True if the key is now locked out.
        """
        self._prune()
        now = time.time()
        cutoff = now - self.window_seconds
        self._attempts[key] = [t for t in self._attempts.get(key, []) if t > cutoff]
        self._attempts[key].append(now)
        if len(self._attempts[key]) >= self.max_attempts:
            self._locked_until[key] = now + self.lockout_seconds
            return True
        return False

    def reset(self, key: str) -> None:
        self._attempts.pop(key, None)
        self._locked_until.pop(key, None)


login_limiter: RateLimiter = RateLimiter()
