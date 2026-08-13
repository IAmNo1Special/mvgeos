from __future__ import annotations

from mvgeos_agent.errors import AuthenticationError, RateLimitError

from mvgeos_cli.formatting import format_error


def test_format_error_rate_limit_without_retry() -> None:
    exc = RateLimitError("Rate limit exceeded")
    markup = format_error(exc)
    assert markup == "[yellow]Rate limited by the provider.[/yellow]"


def test_format_error_rate_limit_with_retry() -> None:
    exc = RateLimitError("Rate limit exceeded", retry_after=5.0)
    markup = format_error(exc)
    assert markup == "[yellow]Rate limited by the provider. Try again in 5s.[/yellow]"


def test_format_error_authentication_error() -> None:
    exc = AuthenticationError("Invalid API key")
    markup = format_error(exc)
    assert markup == (
        "[red]Authentication failed (401). "
        "Check your OPENROUTER_API_KEY or --api-key.[/red]"
    )


def test_format_error_generic_exception() -> None:
    exc = RuntimeError("Unexpected connection error")
    markup = format_error(exc)
    assert markup == "[red]Error: Unexpected connection error[/red]"


def test_format_error_string_with_error_prefix() -> None:
    markup = format_error("Error: Something went wrong")
    assert markup == "[red]Error: Something went wrong[/red]"


def test_format_error_plain_string() -> None:
    markup = format_error("Tome not found: 1234")
    assert markup == "[red]Error: Tome not found: 1234[/red]"


def test_format_error_already_marked_up() -> None:
    msg = "[red]API key required.[/red]"
    markup = format_error(msg)
    assert markup == msg
