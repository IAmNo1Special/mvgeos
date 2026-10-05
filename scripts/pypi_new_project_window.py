"""Say when PyPI's new-project cap frees a slot, from the index itself.

A `429 Too many new projects created` refusal is not a broken distribution. It
is a full account quota, and the only useful thing to tell the person holding
the release is when to come back.

PyPI enforces the quota as a trailing window, not a daily reset. The policy it
advertises is::

    Ratelimit-Policy: "project.create.user";q=4;w=86400;pk=:user:

Four creations counted in the trailing 24 hours. A creation leaves the window
when it turns 24 hours old, so the quota next has room at the upload time of
the *oldest* project in the window, plus 24 hours. This script reads those
upload times from the JSON API and prints that instant.

That distinction is the whole point. A batch of four created seconds apart
ages out seconds apart, so the full quota returns at once. Reading it as
"one slot per day" turns one day into four and sends someone chasing a limit
request that was never needed.

Usage:
    python scripts/pypi_new_project_window.py
    python scripts/pypi_new_project_window.py --json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.error
import urllib.request
from typing import TypedDict

from check_publish import publish_order, workspace_packages

# "w=86400" in the policy PyPI advertises: the quota counts the trailing 24
# hours, so a creation is back in the clear exactly 24 hours after it landed.
WINDOW = dt.timedelta(seconds=86400)

# "q=4" in the same policy: four new projects per account per window.
QUOTA = 4

JSON_URL = "https://pypi.org/pypi/{name}/json"


def published_at(name: str, timeout: float = 30.0) -> dt.datetime | None:
    """Return the earliest upload time for a name, or None if it is not on PyPI.

    The earliest time is the one that matters: it is the creation that leaves
    the window first and so frees the first slot.
    """
    try:
        with urllib.request.urlopen(
            JSON_URL.format(name=name), timeout=timeout
        ) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    times = [
        dt.datetime.fromisoformat(upload["upload_time_iso_8601"].replace("Z", "+00:00"))
        for upload in payload.get("urls", [])
    ]
    # A project with no files of the current version still occupies a slot.
    release = payload.get("releases", {}).get(payload["info"]["version"], [])
    times.extend(
        dt.datetime.fromisoformat(upload["upload_time_iso_8601"].replace("Z", "+00:00"))
        for upload in release
    )
    return min(times) if times else None


class Report(TypedDict):
    """The state of the quota, as read from the index."""

    window_seconds: int
    quota: int
    checked_at: str
    published: dict[str, str]
    missing: list[str]
    next_slot_at: str
    seconds_until_next_slot: int
    slots_in_next_window: int
    windows_needed: int


def describe(names: list[str], now: dt.datetime | None = None) -> Report:
    """Read the index and report the state of the quota."""
    now = now or dt.datetime.now(dt.UTC)
    published: dict[str, dt.datetime] = {}
    missing: list[str] = []
    for name in names:
        landed = published_at(name)
        if landed is None:
            missing.append(name)
        else:
            published[name] = landed

    oldest = min(published.values()) if published else None
    next_slot = oldest + WINDOW if oldest else now
    # Names that still need a slot, and how many of them the first free window
    # cannot hold.
    windows_needed = -(-len(missing) // QUOTA) if missing else 0
    return {
        "window_seconds": int(WINDOW.total_seconds()),
        "quota": QUOTA,
        "checked_at": now.isoformat(),
        "published": {
            name: when.isoformat() for name, when in sorted(published.items())
        },
        "missing": missing,
        "next_slot_at": next_slot.isoformat(),
        "seconds_until_next_slot": max(0, int((next_slot - now).total_seconds())),
        "slots_in_next_window": min(QUOTA, len(missing)),
        "windows_needed": windows_needed,
    }


def _format_stamp(iso: str) -> str:
    stamp = dt.datetime.fromisoformat(iso).astimezone(dt.UTC)
    return stamp.strftime("%Y-%m-%d %H:%M:%S UTC")


def render(report: Report) -> str:
    lines = [
        "### PyPI new-project quota",
        "",
        f"- Policy: {report['quota']} new projects per account per trailing "
        f"{report['window_seconds'] // 3600} hours.",
        f"- On the index: {len(report['published'])} of "
        f"{len(report['published']) + len(report['missing'])}.",
    ]
    if report["published"]:
        oldest = min(report["published"].values())
        lines.append(f"- Oldest creation in the window: {_format_stamp(oldest)}.")
    lines.append(f"- A slot next frees: **{_format_stamp(report['next_slot_at'])}**.")
    if report["missing"]:
        lines.append(
            f"- Still to create ({len(report['missing'])}): "
            + ", ".join(f"`{name}`" for name in report["missing"])
        )
        if report["windows_needed"] > 1:
            lines.append(
                f"- That is more names than one window holds, so it takes "
                f"{report['windows_needed']} windows. Re-run once a slot frees."
            )
    else:
        lines.append(
            "- Every distribution is on the index. Nothing is waiting on a slot."
        )
    lines += [
        "",
        "A refusal is a full quota, not a bad distribution. Re-dispatch the "
        "publish workflow after the time above; it skips what already landed.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the report as JSON instead of Markdown",
    )
    args = parser.parse_args()

    report = describe(publish_order(workspace_packages()))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    # This reports; it never blocks. A caller decides what the numbers mean.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
