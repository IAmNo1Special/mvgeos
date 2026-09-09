from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mvgeos_agent.errors import AuthenticationError, RateLimitError
from mvgeos_agent.protocol import MvgeAgent
from rich.console import Console

_console = Console()


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


def format_cwd() -> str:
    """Return formatted current working directory relative to user home."""
    home = Path.home()
    try:
        rel = Path.cwd().relative_to(home)
    except ValueError:
        return str(Path.cwd())
    if str(rel) == ".":
        return "~"
    return f"~/{rel.as_posix()}"


def get_git_branch() -> str | None:
    """Return active git branch or None if not a repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def mana_context(agent: MvgeAgent) -> tuple[str, str]:
    """Return mana usage styling and text tuple."""
    used = getattr(agent, "mana_used", None)
    if used is None:
        state = getattr(agent, "_state", None)
        if state is not None:
            used = getattr(state, "mana_used", None)
    if used is None:
        return "", "mana ?"
    return "", f"mana {used}"


def fit_footer(items: list[tuple[str, str]], width: int) -> list[tuple[str, str]]:
    """Fit footer items to terminal width, truncating excess."""
    if width <= 0:
        return []
    items = list(items)
    while items:
        total = sum(len(text) for _, text in items)
        if total <= width:
            return items

        target_idx = -1
        if len(items) >= 2 and items[-1][1].lstrip().startswith("("):
            target_idx = -2

        n = len(items)
        norm_target = (target_idx + n) % n
        other_total = sum(
            len(text) for i, (_, text) in enumerate(items) if i != norm_target
        )
        room = width - other_total
        if room >= 1:
            style, text = items[norm_target]
            items[norm_target] = (style, text[: room - 1] + "…")
            return items
        items.pop(norm_target)

    return items


def format_tome_info(
    agent: MvgeAgent,
    branch: str | None = None,
    fit: bool = True,
    console_width: int | None = None,
) -> list[tuple[str, str]]:
    """Format footer status items for the active tome."""
    cwd = format_cwd()
    if branch:
        cwd = f"{cwd} ({branch})"
    items: list[tuple[str, str]] = [("bold", f" {cwd}")]
    tid = agent.tome_id
    if tid:
        items.append(("dim", f"  tome {tid[:8]}"))
    mana_style, mana_text = mana_context(agent)
    items.append((mana_style, f"  {mana_text}"))
    right = getattr(agent, "model_id", getattr(agent, "_model_id", ""))
    thinking = getattr(
        agent, "contemplation_level", getattr(agent, "_contemplation_level", None)
    )
    if thinking:
        right = f"{right} • {thinking}"
    items.append(("", f"  {right}"))
    if not fit:
        return items
    width = console_width if console_width is not None else _console.width
    return fit_footer(items, width)


async def render_live_rate_limit(
    exc: RateLimitError,
    out: Callable[[str], None] = _console.print,
    invalidate: Callable[[], None] | None = None,
    sleep_fn: Any = asyncio.sleep,
) -> None:
    """Render a live rate-limit countdown or static exhaustion message."""
    if exc.limit_source == "openrouter_free_tier_daily" or (
        exc.retry_after is None and exc.limit_source
    ):
        markup = format_error(exc)
        out(markup)
        if invalidate is not None:
            invalidate()
        return

    seconds = int(exc.retry_after or 60)
    for sec in range(seconds, 0, -1):
        msg = f"[yellow]Rate limited by the provider. Retry in {sec}s...[/yellow]"
        out(msg)
        if invalidate is not None:
            invalidate()
        await sleep_fn(1)


def _diag_kind(diag: Any) -> str:
    kind = getattr(diag, "kind", None)
    if kind is None:
        return ""
    return str(getattr(kind, "value", kind)).lower()


def check_and_warn_load_failures(
    diagnostics: list[Any],
    out: Callable[[str], None] = _console.print,
) -> None:
    """Scan diagnostics for load failures and print a prominent warning."""
    load_failures: list[Any] = []
    for diag in diagnostics:
        if _diag_kind(diag) == "load_failure":
            load_failures.append(diag)

    if not load_failures:
        return

    count = len(load_failures)
    out(f"[bold yellow]Warning: Failed to load {count} rune(s):[/bold yellow]")
    for diag in load_failures:
        name = (
            getattr(diag, "rune_name", None)
            or getattr(diag, "skill_name", None)
            or getattr(diag, "name", "unknown")
        )
        msg = getattr(diag, "message", str(diag))
        out(f"  [yellow]- {name}: {msg}[/yellow]")
    out("[dim]Run 'mvgeos info' for detailed diagnostic information.[/dim]\n")


def check_and_warn_missing_deps(
    diagnostics: list[Any],
    out: Callable[[str], None] = _console.print,
    prompt: Callable[[str], str] | None = None,
    install: Callable[[], Any] | None = None,
) -> bool:
    """Scan diagnostics for MISSING_DEP and print a recovery alert."""
    missing: list[Any] = []
    for diag in diagnostics:
        if _diag_kind(diag) == "missing_dep":
            missing.append(diag)

    if not missing:
        return False

    out("[bold yellow]Missing rune dependencies detected:[/bold yellow]")
    for diag in missing:
        name = getattr(diag, "rune_name", None) or getattr(diag, "name", "unknown")
        msg = getattr(diag, "message", str(diag))
        out(f"  [yellow]- {name}: {msg}[/yellow]")
    out("[dim]Run 'mvgeos setup install' to install the missing dependencies.[/dim]")

    if install is not None and prompt is not None:
        response = (
            prompt("Auto-install missing dependencies now? [y/N]: ").strip().lower()
        )
        if response == "y":
            install()
    out("")
    return True
