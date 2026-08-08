from __future__ import annotations

from pathlib import Path

import pytest

from mvgeos_agent.prompt_config import (
    DEFAULT_GUIDELINES,
    DEFAULT_GUIDELINES_MD,
    DEFAULT_SYSTEM_MD,
    build_system_prompt,
    ensure_config_files,
    load_guidelines,
    load_system_prompt,
    resolve_config_dir,
)


class TestSeededConfigFiles:
    def test_creates_both_files(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        config_dir = ensure_config_files("test-mvge")

        assert (config_dir / "SYSTEM.md").exists()
        assert (config_dir / "GUIDELINES.md").exists()

    def test_guidelines_seeded_with_real_content(
        self, tmp_path: Path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        config_dir = ensure_config_files("test-mvge")
        text = (config_dir / "GUIDELINES.md").read_text(encoding="utf-8")

        assert text.strip()
        assert "Be concise" in text
        for guideline in DEFAULT_GUIDELINES:
            assert guideline in text

    def test_system_seeded_with_real_content(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        config_dir = ensure_config_files("test-mvge")
        text = (config_dir / "SYSTEM.md").read_text(encoding="utf-8")

        assert text.strip()
        assert "Mvge" in text

    def test_existing_files_are_never_overwritten(
        self, tmp_path: Path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        config_dir = ensure_config_files("test-mvge")
        (config_dir / "GUIDELINES.md").write_text("- Mine\n", encoding="utf-8")
        (config_dir / "SYSTEM.md").write_text("Mine too", encoding="utf-8")

        ensure_config_files("test-mvge")

        assert (config_dir / "GUIDELINES.md").read_text(encoding="utf-8") == "- Mine\n"
        assert (config_dir / "SYSTEM.md").read_text(encoding="utf-8") == "Mine too"

    def test_empty_file_from_older_versions_is_seeded(
        self, tmp_path: Path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        """Earlier versions created GUIDELINES.md with touch(), leaving it empty."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        config_dir = ensure_config_files("test-mvge")
        (config_dir / "GUIDELINES.md").write_text("", encoding="utf-8")

        ensure_config_files("test-mvge")

        assert (config_dir / "GUIDELINES.md").read_text(encoding="utf-8").strip()

    def test_seeded_guidelines_round_trip(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """What ensure_config_files writes must parse back to the defaults."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        config_dir = ensure_config_files("test-mvge")

        assert load_guidelines("test-mvge", config_dir) == DEFAULT_GUIDELINES


class TestResolveConfigDir:
    def test_defaults_to_dotagents_path(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        resolved = resolve_config_dir("my-mvge")

        assert resolved == tmp_path / ".agents" / ".mvgeos" / "my-mvge"

    def test_explicit_dir_wins(self, tmp_path: Path) -> None:
        assert resolve_config_dir("my-mvge", tmp_path) == tmp_path


class TestSingleRendering:
    def test_load_and_build_agree_on_guidelines(self, tmp_path: Path) -> None:
        """Both entry points must render the same file the same way."""
        (tmp_path / "GUIDELINES.md").write_text(
            "- Alpha rule\n- Beta rule\n", encoding="utf-8"
        )

        built = build_system_prompt(spells=[], config_dir=tmp_path)
        loaded = load_system_prompt("test-mvge", config_dir=tmp_path)

        for text in (built, loaded):
            assert "- Alpha rule" in text
            assert "- Beta rule" in text

    def test_both_fall_back_to_defaults(self, tmp_path: Path) -> None:
        built = build_system_prompt(spells=[], config_dir=tmp_path)
        loaded = load_system_prompt("test-mvge", config_dir=tmp_path)

        for text in (built, loaded):
            assert DEFAULT_GUIDELINES[0] in text

    def test_both_honour_custom_system_md(self, tmp_path: Path) -> None:
        (tmp_path / "SYSTEM.md").write_text("You are a haiku bot.", encoding="utf-8")

        built = build_system_prompt(spells=[], config_dir=tmp_path)
        loaded = load_system_prompt("test-mvge", config_dir=tmp_path)

        for text in (built, loaded):
            assert "You are a haiku bot." in text


class TestLoadGuidelines:
    def test_reads_from_config_dir(self, tmp_path: Path) -> None:
        (tmp_path / "GUIDELINES.md").write_text("- Only rule\n", encoding="utf-8")

        assert load_guidelines("test-mvge", tmp_path) == ["Only rule"]

    def test_defaults_when_missing(self, tmp_path: Path) -> None:
        assert load_guidelines("test-mvge", tmp_path) == DEFAULT_GUIDELINES

    def test_defaults_when_blank(self, tmp_path: Path) -> None:
        (tmp_path / "GUIDELINES.md").write_text("  \n\n", encoding="utf-8")

        assert load_guidelines("test-mvge", tmp_path) == DEFAULT_GUIDELINES

    def test_strips_bullet_markers(self, tmp_path: Path) -> None:
        (tmp_path / "GUIDELINES.md").write_text(
            "- Dash\n* Star\nBare\n", encoding="utf-8"
        )

        assert load_guidelines("test-mvge", tmp_path) == ["Dash", "Star", "Bare"]


class TestSeedConstants:
    def test_guidelines_md_is_markdown_bullets(self) -> None:
        assert DEFAULT_GUIDELINES_MD.strip().startswith("- ")

    def test_system_md_is_not_empty(self) -> None:
        assert DEFAULT_SYSTEM_MD.strip()

    @pytest.mark.parametrize("guideline", DEFAULT_GUIDELINES)
    def test_every_default_appears_in_the_seed(self, guideline: str) -> None:
        assert guideline in DEFAULT_GUIDELINES_MD
