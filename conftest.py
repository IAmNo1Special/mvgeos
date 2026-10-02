"""Session-wide hermeticity guards for the workspace test suite.

TESTING.md section 2 forbids real secrets and credential-bearing
environment variables in tests. Two mechanisms defeated that:

``Mvge.__init__`` calls ``load_dotenv()`` on the caller's ``.env``, and
``load_dotenv`` writes into the process-wide ``os.environ`` without ever
rolling back. The lookup is caller-frame relative, so a test cannot
reliably steer it away from the repository's own ``.env`` -- which holds
real credentials. Whichever test constructed an agent first therefore
handed the developer's API keys to every test that ran after it.

The guard below restores the credential variables after each test. It is
deliberately scoped to those variables rather than the whole environment:
the auto-loading behaviour is exercised on purpose by
``test_dot_env_auto_loading``, and a blanket rollback would also revert
unrelated writes that background watcher threads may still be reading.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

#: Every variable the engine reads as a credential, sourced from the
#: ``os.environ.get`` calls in ``mvgeos-*/src`` rather than guessed.
CREDENTIAL_ENV_VARS = (
    "OPENROUTER_API_KEY",
    "MVGEOS_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "STORAGE_SECRET",
)


@pytest.fixture(autouse=True)
def _isolate_credential_env() -> Iterator[None]:
    """Keep one test's loaded credentials out of the next test's environment.

    Requests come before a test's own ``monkeypatch`` so this fixture
    finalises last, which means it has the final word on the restored
    state rather than deferring to whatever ran before it.
    """
    snapshot = {name: os.environ.get(name) for name in CREDENTIAL_ENV_VARS}
    try:
        yield
    finally:
        for name, value in snapshot.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
