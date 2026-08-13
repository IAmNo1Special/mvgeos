from __future__ import annotations

from mvgeos_agent.errors import AuthenticationError, RateLimitError


def format_error(exc: Exception | str) -> str:
    """Format an exception or error string into consistent Rich markup."""
    if isinstance(exc, RateLimitError):
        hint = ""
        if exc.retry_after is not None:
            hint = f" Try again in {exc.retry_after:.0f}s."
        return f"[yellow]Rate limited by the provider.{hint}[/yellow]"
    if isinstance(exc, AuthenticationError):
        return (
            "[red]Authentication failed (401). "
            "Check your OPENROUTER_API_KEY or --api-key.[/red]"
        )
    msg = str(exc)
    if msg.startswith("[red]") or msg.startswith("[yellow]"):
        return msg
    if msg.startswith("Error: "):
        return f"[red]{msg}[/red]"
    return f"[red]Error: {msg}[/red]"
