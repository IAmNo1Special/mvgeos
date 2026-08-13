"""Pytest configuration and fixtures for mvgeos-gui tests."""

from collections.abc import AsyncGenerator

import pytest_asyncio
from nicegui.testing import User
from nicegui.testing.user_simulation import user_simulation


@pytest_asyncio.fixture(loop_scope="function")
async def user() -> AsyncGenerator[User]:
    """Create a new nicegui User test simulation client."""
    async with user_simulation() as simulated_user:
        yield simulated_user
