from __future__ import annotations

import asyncio

from coding_mvge.spells.types import SpellResult, SpellStatus


async def cast_bash(command: str, timeout_ms: int = 30000) -> SpellResult:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_ms / 1000
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return SpellResult(
                spell_name="bash",
                status=SpellStatus.PARTIAL,
                content=stdout.decode("utf-8", errors="replace"),
                error_message=f"Command timed out after {timeout_ms}ms",
            )

        if proc.returncode != 0:
            return SpellResult(
                spell_name="bash",
                status=SpellStatus.ERROR,
                content=stdout.decode("utf-8", errors="replace"),
                error_message=stderr.decode("utf-8", errors="replace").strip(),
            )

        return SpellResult(
            spell_name="bash",
            status=SpellStatus.SUCCESS,
            content=stdout.decode("utf-8", errors="replace"),
        )
    except Exception as exc:
        return SpellResult(
            spell_name="bash",
            status=SpellStatus.ERROR,
            content="",
            error_message=str(exc),
        )
