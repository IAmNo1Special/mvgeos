import asyncio

from mvgeos_spells.casting import cast_bash


def test_cast_bash_echo_returns_content() -> None:
    result = asyncio.run(cast_bash("echo hello world"))
    assert result.status.value == "success"
    assert "hello world" in result.content
