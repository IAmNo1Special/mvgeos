"""Architecture guard: the provider layer must not depend on the agent layer.

mvgeos-provider sits below mvgeos-agent in the workspace dependency graph
(agent declares provider as a runtime dependency). Any import of
``mvgeos_agent`` from provider source recreates a circular dependency that
only resolves because the monorepo installs everything editable into one
environment.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PROVIDER_SRC = Path(__file__).resolve().parents[2] / "src" / "mvgeos_provider"


def _provider_sources() -> list[Path]:
    return sorted(_PROVIDER_SRC.rglob("*.py"))


def test_provider_never_imports_agent() -> None:
    """No provider module may import mvgeos_agent, even under TYPE_CHECKING."""
    offenders = [
        src
        for src in _provider_sources()
        if "mvgeos_agent" in src.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        "provider modules import the agent layer (circular dependency): "
        f"{[str(o.relative_to(_PROVIDER_SRC)) for o in offenders]}"
    )


def test_provider_package_importable_without_agent_side_effects() -> None:
    """Importing provider entry modules must not pull in mvgeos_agent.

    Runs in a subprocess because sys.modules is process-global; other tests
    in the same session may have imported the agent layer already.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "import mvgeos_provider.base\n"
                "import mvgeos_provider.model_registry\n"
                "import mvgeos_provider.openrouter\n"
                "import mvgeos_provider.registry\n"
                "import mvgeos_provider.retry\n"
                "import mvgeos_provider.sse\n"
                "import mvgeos_provider.types\n"
                "assert 'mvgeos_agent' not in sys.modules, "
                "'provider imports pulled in mvgeos_agent'\n"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"provider imports failed or pulled in agent: {result.stderr}"
    )
