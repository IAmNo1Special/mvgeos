from pathlib import Path

import pytest

from mvgeos_agent.config_manager import is_known_agent, validate_agent_name


def test_is_known_agent_with_project_dir(tmp_path: Path) -> None:
    agent_dir = tmp_path / ".agents" / ".mvgeos" / "my-agent"
    agent_dir.mkdir(parents=True)
    assert is_known_agent("my-agent", project_dir=tmp_path) is True
    assert is_known_agent("unknown", project_dir=tmp_path) is False


def test_is_known_agent_invalid_pattern() -> None:
    assert is_known_agent("bad name!") is False
    assert is_known_agent("") is False


def test_validate_agent_name_valid() -> None:
    # should not raise with allow_create
    validate_agent_name("valid_agent-123", allow_create=True)
    # known agent
    validate_agent_name("default-mvge")


def test_validate_agent_name_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid agent name"):
        validate_agent_name("bad name!")
