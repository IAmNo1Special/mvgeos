from __future__ import annotations


class MvgeError(Exception):
    def __init__(self, code: str, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.code = code
        if cause is not None:
            self.__cause__ = cause


def to_error(err: Exception | str | None) -> MvgeError:
    if isinstance(err, MvgeError):
        return err
    if isinstance(err, Exception):
        return MvgeError("unknown", str(err), err)
    if isinstance(err, str):
        return MvgeError("unknown", err)
    return MvgeError("unknown", "Unknown error")


class SpellNotFoundError(MvgeError):
    def __init__(self, spell_name: str) -> None:
        super().__init__("spell_not_found", f"Spell not found: {spell_name}")


class RateLimitError(MvgeError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__("rate_limited", message)
        self.retry_after = retry_after


class AuthenticationError(MvgeError):
    def __init__(self, message: str) -> None:
        super().__init__("auth_failed", message)


class SpellTimeoutError(MvgeError):
    def __init__(self, spell_name: str, timeout_ms: int) -> None:
        super().__init__(
            "spell_timeout",
            f"Spell '{spell_name}' timed out after {timeout_ms}ms",
        )
        self.timeout_ms = timeout_ms


class ManaExhaustedError(MvgeError):
    def __init__(self, used: int, budget: int) -> None:
        super().__init__(
            "mana_exhausted",
            f"Mana budget exhausted: {used}/{budget}",
        )
        self.used = used
        self.budget = budget


class MaxTurnsExceededError(MvgeError):
    def __init__(self, max_turns: int) -> None:
        super().__init__("max_turns_exceeded", f"Max turns exceeded: {max_turns}")
        self.max_turns = max_turns


class TomeResumeError(MvgeError):
    def __init__(self, path: str, cause: Exception | None = None) -> None:
        super().__init__(
            "tome_resume_failed",
            f"Failed to resume tome: {path}",
            cause,
        )


class SpellExecutionError(MvgeError):
    def __init__(self, spell_name: str, cause: Exception) -> None:
        super().__init__(
            "spell_execution_failed",
            f"Spell '{spell_name}' execution failed: {cause}",
            cause,
        )
