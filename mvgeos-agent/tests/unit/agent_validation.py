from __future__ import annotations

from pathlib import Path

import pytest

from mvgeos_agent.config_manager import is_known_agent, validate_agent_name
from mvgeos_agent.constants import DEFAULT_AGENT_NAME


def test_default_agent_is_known() -> None:
    assert is_known_agent(DEFAULT_AGENT_NAME) is True


def test_validate_default_agent_succeeds() -> None:
    validate_agent_name(DEFAULT_AGENT_NAME)


def test_invalid_agent_name_syntax_raises() -> None:
    with pytest.raises(ValueError, match="Invalid agent name"):
        validate_agent_name("")

    with pytest.raises(ValueError, match="Invalid agent name"):
        validate_agent_name("   ")

    with pytest.raises(ValueError, match="Invalid agent name"):
        validate_agent_name("../invalid")

    with pytest.raises(ValueError, match="Invalid agent name"):
        validate_agent_name("invalid/path")

    with pytest.raises(ValueError, match="Invalid agent name"):
        validate_agent_name("agent name with spaces")


def test_nonexistent_agent_raises_value_error(tmp_path: Path) -> None:
    fake_base = tmp_path / "agents"
    fake_base.mkdir()

    assert is_known_agent("nonexistent", agent_config_base=fake_base) is False

    with pytest.raises(ValueError, match="Unknown agent 'nonexistent'"):
        validate_agent_name("nonexistent", agent_config_base=fake_base)


def test_existing_agent_directory_is_known(tmp_path: Path) -> None:
    fake_base = tmp_path / "agents"
    fake_base.mkdir()
    custom_agent_dir = fake_base / "custom-agent"
    custom_agent_dir.mkdir()

    assert is_known_agent("custom-agent", agent_config_base=fake_base) is True
    validate_agent_name("custom-agent", agent_config_base=fake_base)


def test_existing_agent_config_file_is_known(tmp_path: Path) -> None:
    fake_base = tmp_path / "agents"
    custom_agent_dir = fake_base / "custom-agent-2"
    custom_agent_dir.mkdir(parents=True)
    (custom_agent_dir / "config.json").write_text("{}", encoding="utf-8")

    assert is_known_agent("custom-agent-2", agent_config_base=fake_base) is True
    validate_agent_name("custom-agent-2", agent_config_base=fake_base)


def test_allow_create_skips_existence_check(tmp_path: Path) -> None:
    fake_base = tmp_path / "agents"
    fake_base.mkdir()

    validate_agent_name("new-agent", agent_config_base=fake_base, allow_create=True)
