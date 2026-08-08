from __future__ import annotations

import tempfile
from pathlib import Path

from mvgeos_agent.prompt_config import DEFAULT_GUIDELINES, build_system_prompt


class TestGuidelinesFromConfigDir:
    def test_custom_guidelines_replace_the_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            (config / "GUIDELINES.md").write_text(
                "- Always cite file paths\n- Never guess an API\n",
                encoding="utf-8",
            )

            prompt = build_system_prompt(spells=[], config_dir=config)

            assert "Always cite file paths" in prompt
            assert "Never guess an API" in prompt

    def test_defaults_used_when_no_guidelines_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prompt = build_system_prompt(spells=[], config_dir=Path(tmp))

            assert DEFAULT_GUIDELINES[0] in prompt

    def test_guidelines_are_not_read_from_cwd(
        self, tmp_path: Path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        # A GUIDELINES.md in the working directory must be ignored: only the
        # config dir is authoritative.
        cwd_dir = tmp_path / "work"
        config_dir = tmp_path / "config"
        cwd_dir.mkdir()
        config_dir.mkdir()
        (cwd_dir / "GUIDELINES.md").write_text(
            "- Stray guideline from cwd\n", encoding="utf-8"
        )
        monkeypatch.chdir(cwd_dir)

        prompt = build_system_prompt(spells=[], config_dir=config_dir)

        assert "Stray guideline from cwd" not in prompt
        assert DEFAULT_GUIDELINES[0] in prompt

    def test_bullet_prefixes_are_normalised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            (config / "GUIDELINES.md").write_text(
                "- Keep answers short\nNo bullet here\n", encoding="utf-8"
            )

            prompt = build_system_prompt(spells=[], config_dir=config)

            assert "- Keep answers short" in prompt
            assert "- No bullet here" in prompt

    def test_blank_lines_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            (config / "GUIDELINES.md").write_text(
                "- One\n\n\n- Two\n", encoding="utf-8"
            )

            prompt = build_system_prompt(spells=[], config_dir=config)

            # "Guidelines:" also appears in the default prompt body, so take
            # the trailing section that the builder appends last.
            guidelines_block = prompt.rsplit("Guidelines:", 1)[1]
            assert guidelines_block.strip().splitlines() == ["- One", "- Two"]

    def test_empty_guidelines_file_falls_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            (config / "GUIDELINES.md").write_text("   \n", encoding="utf-8")

            prompt = build_system_prompt(spells=[], config_dir=config)

            assert DEFAULT_GUIDELINES[0] in prompt
