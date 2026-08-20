"""Pytest configuration and fixtures for mvgeos-gui tests."""

import os
import warnings
from collections.abc import AsyncGenerator

import pytest_asyncio
from nicegui.testing import User
from nicegui.testing.user_simulation import user_simulation

# Suppress RuntimeWarning from unawaited mock coroutines created by
# asyncio.create_task in sync methods under test. This is a test-only
# artifact: the event loop is not running, so mock coroutines never
# execute, but the code under test still wraps them in a Task.
warnings.filterwarnings(
    "ignore",
    message="coroutine '.*' was never awaited",
    category=RuntimeWarning,
)

# In environments without /dev/shm (e.g. certain containers), NiceGUI's
# process-pool setup fails because multiprocessing semaphores require
# /dev/shm on Linux. Since tests run in-process and never use cpu_bound
# offloading, we gracefully skip the pool setup.
if not os.path.exists("/dev/shm"):
    from nicegui import run as _run

    _orig_setup = _run.setup

    def _safe_setup() -> None:
        try:
            _orig_setup()
        except FileNotFoundError:
            _run.process_pool = None
            _run._pool_context = None

    _run.setup = _safe_setup


@pytest_asyncio.fixture(loop_scope="function")
async def user() -> AsyncGenerator[User]:
    """Create a new nicegui User test simulation client."""
    async with user_simulation() as simulated_user:
        yield simulated_user
