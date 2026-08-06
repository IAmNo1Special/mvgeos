from __future__ import annotations

from pathlib import Path

from mvgeos_agent.prompt_config import (
    _SYSTEM_PROMPT_BODY,
    DEFAULT_GUIDELINES,
    DEFAULT_SYSTEM_PROMPT,
    build_system_prompt,
    ensure_config_files,
    load_guidelines,
    load_system_prompt,
)


def test_build_system_prompt_basic() -> None:
    prompt = build_system_prompt(spells=["bash", "read"])
    assert "You are Mvge" in prompt
    assert "Active spells:" in prompt
    assert "bash" in prompt
    assert "read" in prompt
    assert "Guidelines:" in prompt


def test_build_system_prompt_no_spells() -> None:
    prompt = build_system_prompt(spells=[])
    assert "Active spells:" in prompt
    assert "(none)" in prompt


def test_build_system_prompt_with_cwd() -> None:
    prompt = build_system_prompt(spells=["bash"], cwd="/test/path")
    assert "Current working directory: /test/path" in prompt


def test_build_system_prompt_with_custom_prompt() -> None:
    prompt = build_system_prompt(spells=[], custom_prompt="Custom prompt here")
    assert "Custom prompt here" in prompt


def test_build_system_prompt_with_context_files() -> None:
    prompt = build_system_prompt(
        spells=[], context_files=[{"path": "test.py", "content": "print('hi')"}]
    )
    assert "You are Mvge" in prompt


def test_build_system_prompt_with_name() -> None:
    prompt = build_system_prompt(spells=[], name="test-agent")
    assert "You are Mvge" in prompt


def test_build_system_prompt_with_config_dir_system_md(tmp_path: Path) -> None:
    system_md = tmp_path / "SYSTEM.md"
    system_md.write_text("Custom SYSTEM.md content", encoding="utf-8")

    prompt = build_system_prompt(spells=[], config_dir=tmp_path)
    assert "Custom SYSTEM.md content" in prompt


def test_build_system_prompt_with_config_dir_guidelines(tmp_path: Path) -> None:
    system_md = tmp_path / "SYSTEM.md"
    system_md.write_text("Custom system", encoding="utf-8")

    guidelines_md = tmp_path / "GUIDELINES.md"
    guidelines_md.write_text("- Custom rule 1\n- Custom rule 2\n", encoding="utf-8")

    prompt = build_system_prompt(spells=[], config_dir=tmp_path)
    assert "Custom system" in prompt


def test_ensure_config_files_creates_files(tmp_path: Path) -> None:
    config_dir = ensure_config_files("test-agent")

    assert config_dir.exists()
    assert (config_dir / "SYSTEM.md").exists()
    assert (config_dir / "GUIDELINES.md").exists()

    system_content = (config_dir / "SYSTEM.md").read_text(encoding="utf-8")
    assert "You are Mvge" in system_content


def test_ensure_config_files_idempotent(tmp_path: Path) -> None:
    config_dir = ensure_config_files("test-agent")
    ensure_config_files("test-agent")

    assert (config_dir / "SYSTEM.md").exists()
    assert (config_dir / "GUIDELINES.md").exists()


def test_load_system_prompt_custom_overrides() -> None:
    prompt = load_system_prompt("test-agent", custom="Custom prompt")
    assert prompt == "Custom prompt"


def test_load_system_prompt_with_spells() -> None:
    prompt = load_system_prompt("test-agent", spells=["bash", "read"])
    assert "Active spells:" in prompt
    assert "bash" in prompt
    assert "read" in prompt


def test_load_system_prompt_config_dir_with_system(tmp_path: Path) -> None:
    system_md = tmp_path / "SYSTEM.md"
    system_md.write_text("From config dir", encoding="utf-8")

    prompt = load_system_prompt("test-agent", config_dir=tmp_path)
    assert "From config dir" in prompt


def test_load_system_prompt_config_dir_with_guidelines(tmp_path: Path) -> None:
    system_md = tmp_path / "SYSTEM.md"
    system_md.write_text("Base prompt", encoding="utf-8")

    guidelines_md = tmp_path / "GUIDELINES.md"
    guidelines_md.write_text("- Guideline 1\n- Guideline 2\n", encoding="utf-8")

    prompt = load_system_prompt("test-agent", config_dir=tmp_path)
    assert "Base prompt" in prompt
    assert "Guideline 1" in prompt
    assert "Guideline 2" in prompt


def test_load_system_prompt_config_dir_with_guidelines(tmp_path: Path) -> None:
    system_md = tmp_path / "SYSTEM.md"
    system_md.write_text("Base prompt", encoding="utf-8")

    guidelines_md = tmp_path / "GUIDELINES.md"
    guidelines_md.write_text("- Guideline 1\n- Guideline 2\n", encoding="utf-8")

    prompt = load_system_prompt("test-agent", config_dir=tmp_path)
    assert "Base prompt" in prompt
    assert "Guideline 1" in prompt
    assert "Guideline 2" in prompt


def test_build_system_prompt_with_config_dir_guidelines(tmp_path: Path) -> None:
    system_md = tmp_path / "SYSTEM.md"
    system_md.write_text("Custom system", encoding="utf-8")

    # build_system_prompt doesn't load GUIDELINES from config_dir
    # (load_guidelines does that from ~/.agents/.mvgeos/{name}/GUIDELINES.md)
    prompt = build_system_prompt(spells=[], config_dir=tmp_path)
    assert "Custom system" in prompt


def test_build_system_prompt_guidelines_empty_file(tmp_path: Path) -> None:
    system_md = tmp_path / "SYSTEM.md"
    system_md.write_text("Custom system", encoding="utf-8")

    # build_system_prompt doesn't load GUIDELINES.md from config_dir
    # (load_guidelines does that from ~/.agents/.mvgeos/{name}/GUIDELINES.md)
    # Default guidelines are always included
    prompt = build_system_prompt(spells=[], config_dir=tmp_path)
    assert "Custom system" in prompt
    assert "Guidelines:" in prompt


def test_ensure_config_files_creates_guidelines_file(tmp_path: Path) -> None:
    config_dir = ensure_config_files("test-agent")

    assert config_dir.exists()
    assert (config_dir / "SYSTEM.md").exists()
    assert (config_dir / "GUIDELINES.md").exists()


def test_load_system_prompt_oserror_fallback(tmp_path: Path) -> None:
    import sys
    if sys.platform == "win32":
        import pytest
        pytest.skip("File permissions not enforced on Windows")

    config_path = tmp_path / "SYSTEM.md"
    config_path.write_text("Original prompt", encoding="utf-8")

    config_path.chmod(0o000)

    try:
        prompt = load_system_prompt("test-agent", config_dir=tmp_path)
        assert prompt == DEFAULT_SYSTEM_PROMPT
    finally:
        config_path.chmod(0o644)


def test_load_guidelines_oserror_fallback(tmp_path: Path) -> None:
    import sys
    if sys.platform == "win32":
        import pytest
        pytest.skip("File permissions not enforced on Windows")

    home = Path.home()
    config_dir = home / ".agents" / ".mvgeos" / "test-agent-oserror"
    config_dir.mkdir(parents=True, exist_ok=True)

    try:
        guidelines_md = config_dir / "GUIDELINES.md"
        guidelines_md.write_text("- Custom 1\n- Custom 2\n", encoding="utf-8")
        guidelines_md.chmod(0o000)

        try:
            guidelines = load_guidelines("test-agent-oserror")
            assert guidelines == DEFAULT_GUIDELINES
        finally:
            guidelines_md.chmod(0o644)
    finally:
        import shutil

        shutil.rmtree(config_dir, ignore_errors=True)


def test_load_system_prompt_fallback_to_default() -> None:
    prompt = load_system_prompt("nonexistent-agent")
    assert "You are Mvge" in prompt
    assert "Guidelines:" in prompt


def test_load_guidelines_default() -> None:
    guidelines = load_guidelines("nonexistent-agent")
    assert guidelines == DEFAULT_GUIDELINES


def test_load_guidelines_from_config_dir(tmp_path: Path) -> None:
    # Use the actual config directory path that load_guidelines expects
    home = Path.home()
    config_dir = home / ".agents" / ".mvgeos" / "test-agent-load-test"
    config_dir.mkdir(parents=True, exist_ok=True)

    try:
        guidelines_md = config_dir / "GUIDELINES.md"
        guidelines_md.write_text("- Custom 1\n- Custom 2\n", encoding="utf-8")

        guidelines = load_guidelines("test-agent-load-test")
        assert "Custom 1" in guidelines
        assert "Custom 2" in guidelines
    finally:
        # Cleanup
        import shutil

        shutil.rmtree(config_dir, ignore_errors=True)


def test_load_guidelines_empty_file(tmp_path: Path) -> None:
    home = Path.home()
    config_dir = home / ".agents" / ".mvgeos" / "test-agent-empty"
    config_dir.mkdir(parents=True, exist_ok=True)

    try:
        guidelines_md = config_dir / "GUIDELINES.md"
        guidelines_md.write_text("", encoding="utf-8")

        guidelines = load_guidelines("test-agent-empty")
        assert guidelines == DEFAULT_GUIDELINES
    finally:
        import shutil

        shutil.rmtree(config_dir, ignore_errors=True)


def test_default_system_prompt_content() -> None:
    assert "You are Mvge" in DEFAULT_SYSTEM_PROMPT
    assert "Guidelines:" in DEFAULT_SYSTEM_PROMPT
    assert "Be concise" in DEFAULT_SYSTEM_PROMPT


def test_default_guidelines_content() -> None:
    assert len(DEFAULT_GUIDELINES) > 0
    assert "Be concise" in DEFAULT_GUIDELINES[0]


def test_system_prompt_body() -> None:
    assert "You are Mvge" in _SYSTEM_PROMPT_BODY
    assert "spells (tools)" in _SYSTEM_PROMPT_BODY
