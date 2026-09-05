from __future__ import annotations

from datetime import UTC, datetime

from mvgeos_agent.errors import AuthenticationError, RateLimitError


def format_error(exc: Exception | str) -> str:
    """Format an exception or error string into consistent Rich markup."""
    if isinstance(exc, RateLimitError):
        if exc.limit_source == "openrouter_free_tier_daily":
            limit_str = (
                f" ({exc.quota_limit}/{exc.quota_limit} requests)"
                if exc.quota_limit
                else ""
            )
            reset_str = ""
            if exc.reset_at:
                dt = datetime.fromtimestamp(exc.reset_at, UTC)
                reset_str = f" Resets at {dt.strftime('%H:%M UTC')}."
            hint = f"\n[dim]Hint: {exc.remedy_hint}[/dim]" if exc.remedy_hint else ""
            return (
                f"[yellow]Daily free-model quota exhausted{limit_str}."
                f"{reset_str}[/yellow]{hint}"
            )
        if (
            exc.limit_source == "upstream_rate_limit"
            or "provider returned error" in str(exc).lower()
        ):
            return f"[yellow]Upstream provider overloaded: {exc}[/yellow]"

        hint = ""
        if exc.retry_after is not None:
            hint = f" Try again in {exc.retry_after:.0f}s."
        remedy = f"\n[dim]Hint: {exc.remedy_hint}[/dim]" if exc.remedy_hint else ""
        if str(exc) and str(exc).lower() not in (
            "rate limited",
            "rate limit exceeded",
            "you are being rate limited",
        ):
            return (
                f"[yellow]Rate limited by the provider: {exc}.{hint}[/yellow]{remedy}"
            )
        return f"[yellow]Rate limited by the provider.{hint}[/yellow]{remedy}"
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
