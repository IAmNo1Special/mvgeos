"""Pytest configuration and fixtures for mvgeos-gui tests."""

import os
import shutil as _shutil
import warnings
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from nicegui.storage import Storage as _Storage
from nicegui.testing import User
from nicegui.testing.user_simulation import user_simulation

import mvgeos_gui.services.config_service as _config_svc
import mvgeos_gui.services.tome_service as _tome_svc

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

# On Windows, NTFS delayed file-handle release can cause self.path.rmdir()
# in Storage.clear() to raise OSError WinError 145 (directory not empty).
# Gracefully fall back to shutil.rmtree with error suppression.
_orig_storage_clear = _Storage.clear


def _safe_storage_clear(self: _Storage) -> None:
    try:
        _orig_storage_clear(self)
    except OSError:
        if self.path.exists():
            _shutil.rmtree(self.path, ignore_errors=True)


_Storage.clear = _safe_storage_clear


@pytest.fixture(autouse=True)
def isolate_tome_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tome storage directory to ensure hermetic test execution."""
    tome_dir = tmp_path / "tomes"
    tome_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_tome_svc, "DEFAULT_TOME_DIR", tome_dir)


@pytest.fixture(autouse=True)
def isolate_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the OS keyring to ensure hermetic test execution.

    Saving settings otherwise reaches the real OS keyring; on headless
    macOS CI that blocks forever inside SecItemAdd with no way to answer
    the authorization prompt.
    """
    store: dict[str, str] = {}

    def _fake_save(api_key: str) -> bool:
        if api_key:
            store["api_key"] = api_key
        return True

    def _fake_load() -> str | None:
        return store.get("api_key")

    def _fake_delete() -> None:
        store.pop("api_key", None)

    monkeypatch.setattr(_config_svc, "_save_api_key_to_keyring", _fake_save)
    monkeypatch.setattr(_config_svc, "_load_api_key_from_keyring", _fake_load)
    monkeypatch.setattr(_config_svc, "_delete_api_key_from_keyring", _fake_delete)


@pytest_asyncio.fixture(loop_scope="function")
async def user() -> AsyncGenerator[User]:
    """Create a new nicegui User test simulation client."""
    async with user_simulation() as simulated_user:
        yield simulated_user
