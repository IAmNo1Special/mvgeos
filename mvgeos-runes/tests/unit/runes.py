import sys
import tempfile
import time
from pathlib import Path

import pytest
from mvgeos_core.spells import ExecutionMode

from mvgeos_runes.loader import (
    clear_skill_manifest_cache,
    discover_plugin_skill_paths,
    get_default_skill_paths,
    load_factory_from_manifest,
    load_manifests,
    load_runes_from_paths,
    load_skill_manifest,
    load_skill_manifests,
    load_skills_from_paths,
)
from mvgeos_runes.manifest import load_manifest
from mvgeos_runes.types import (
    DiagnosticKind,
    RuneManifest,
    RuneScope,
    SigilHook,
    SkillDiagnosticKind,
    SkillScope,
    SpellDefinition,
)


def test_load_manifest_valid() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test rune", "hooks": ["before_invocation"], '
            '"entry_point": "main.py"}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert manifest.name == "test_rune"
        assert manifest.version == "1.0.0"
        assert manifest.description == "Test rune"
        assert manifest.hooks == [SigilHook.BEFORE_INVOCATION]
        assert manifest.entry_point == "main.py"


def test_load_manifest_missing_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()

        manifest = load_manifest(rune_dir)

        assert manifest is None


def test_load_manifest_invalid_json() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_file.write_text("{invalid json}", encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is None


def test_load_manifest_missing_required_fields() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_file.write_text('{"version": "1.0.0"}', encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is None


def test_load_manifest_with_shortcuts_dict() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test", "hooks": [], '
            '"shortcuts": [{"key": "ctrl+k", "description": "Clear"}]}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert len(manifest.shortcuts) == 1
        assert manifest.shortcuts[0].key == "ctrl+k"
        assert manifest.shortcuts[0].description == "Clear"


def test_load_manifest_with_shortcuts_strings() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test", "hooks": [], '
            '"shortcuts": ["ctrl+k", "ctrl+r"]}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert len(manifest.shortcuts) == 2
        assert manifest.shortcuts[0].key == "ctrl+k"
        assert manifest.shortcuts[1].key == "ctrl+r"


def test_load_manifest_defaults() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test", "hooks": []}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert manifest.shortcuts == []
        assert manifest.system_deps == []
        assert manifest.python_deps == []
        assert manifest.enabled is True


def test_load_manifests_with_shortcuts() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ext_dir = Path(tmpdir)
        rune_dir = ext_dir / "rune_with_shortcuts"
        rune_dir.mkdir()
        manifest_data = (
            '{"name": "sc_rune", "version": "1.0.0", '
            '"description": "Rune with shortcuts", "hooks": [], '
            '"shortcuts": [{"key": "ctrl+s", "description": "Save"}]}'
        )
        (rune_dir / "manifest.json").write_text(manifest_data, encoding="utf-8")

        manifests = load_manifests(ext_dir)
        assert len(manifests) == 1
        assert len(manifests[0].shortcuts) == 1
        assert manifests[0].shortcuts[0].key == "ctrl+s"


def test_rune_loader_load_all() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        extensions_dir = Path(tmpdir)

        rune1_dir = extensions_dir / "rune1"
        rune1_dir.mkdir()
        rune1_data = (
            '{"name": "rune1", "version": "1.0.0", '
            '"description": "Rune 1", "hooks": [], "entry_point": "main.py"}'
        )
        (rune1_dir / "manifest.json").write_text(rune1_data, encoding="utf-8")

        rune2_dir = extensions_dir / "rune2"
        rune2_dir.mkdir()
        rune2_data = (
            '{"name": "rune2", "version": "2.0.0", '
            '"description": "Rune 2", "hooks": ["after_invocation"], '
            '"entry_point": "run.py"}'
        )
        (rune2_dir / "manifest.json").write_text(rune2_data, encoding="utf-8")

        manifests = load_manifests(extensions_dir)

        assert len(manifests) == 2
        names = {m.name for m in manifests}
        assert names == {"rune1", "rune2"}


def test_load_manifests_empty_dir() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        extensions_dir = Path(tmpdir)

        manifests = load_manifests(extensions_dir)

        assert manifests == []


def test_load_manifests_nonexistent_dir() -> None:
    manifests = load_manifests(Path("/nonexistent/path"))

    assert manifests == []


def test_load_manifests_skips_files() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ext_dir = Path(tmpdir)
        (ext_dir / "README.txt").write_text("hello", encoding="utf-8")
        assert load_manifests(ext_dir) == []


def test_discover_rune_site_packages_posix_structure(tmp_path: Path) -> None:
    from mvgeos_runes.loader import discover_rune_site_packages

    rune_dir = tmp_path / "my_rune"
    venv_dir = rune_dir / ".venv"
    lib_dir = venv_dir / "lib"
    posix_sp = lib_dir / "site-packages"
    posix_sp.mkdir(parents=True)
    python_sp = lib_dir / "python3.13" / "site-packages"
    python_sp.mkdir(parents=True)

    paths = discover_rune_site_packages(rune_dir)
    assert posix_sp in paths
    assert python_sp in paths


def test_load_factory_from_manifest_no_entry_point() -> None:
    manifest = RuneManifest(name="test", version="1.0", description="", entry_point="")
    factory = load_factory_from_manifest(manifest, Path("/tmp"))
    assert factory is None


def test_sigil_hook_enum_values() -> None:
    assert SigilHook.BEFORE_INVOCATION.value == "before_invocation"
    assert SigilHook.AFTER_INVOCATION.value == "after_invocation"
    assert SigilHook.BEFORE_SPELL_CAST.value == "before_spell_cast"
    assert SigilHook.AFTER_SPELL_RESULT.value == "after_spell_result"
    assert SigilHook.BEFORE_PROVIDER_REQUEST.value == "before_provider_request"
    assert SigilHook.AFTER_PROVIDER_RESPONSE.value == "after_provider_response"
    assert SigilHook.BEFORE_PROVIDER_HEADERS.value == "before_provider_headers"
    assert SigilHook.TURN_START.value == "turn_start"
    assert SigilHook.TURN_END.value == "turn_end"
    assert SigilHook.SESSION_START.value == "session_start"
    assert SigilHook.SESSION_SHUTDOWN.value == "session_shutdown"
    assert SigilHook.SESSION_BEFORE_SWITCH.value == "session_before_switch"
    assert SigilHook.SESSION_BEFORE_FORK.value == "session_before_fork"
    assert SigilHook.CONTEXT_TRANSFORM.value == "context_transform"


def test_load_manifest_with_system_deps() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test rune", "hooks": [], '
            '"system_deps": ["ripgrep", "git"]}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert manifest.system_deps == ["ripgrep", "git"]


def test_load_manifest_system_deps_non_list_defaults_to_empty() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test rune", "hooks": [], '
            '"system_deps": "not-a-list"}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert manifest.system_deps == []


def test_load_manifest_system_deps_filters_non_strings() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test rune", "hooks": [], '
            '"system_deps": ["ripgrep", 123, null, "git"]}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert manifest.system_deps == ["ripgrep", "git"]


def test_load_manifest_with_python_deps() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test rune", "hooks": [], '
            '"python_deps": ["heal_my_goap", "aiohttp"]}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert manifest.python_deps == ["heal_my_goap", "aiohttp"]


def test_load_manifest_enabled_false() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test rune", "hooks": [], "enabled": false}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert manifest.enabled is False


def test_load_manifest_enabled_non_bool_defaults_true() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test rune", "hooks": [], "enabled": "yes"}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)
        assert manifest is not None
        assert manifest.enabled is True


def test_load_manifests_skips_disabled_runes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        extensions_dir = Path(tmpdir)

        disabled_dir = extensions_dir / "disabled_rune"
        disabled_dir.mkdir()
        (disabled_dir / "manifest.json").write_text(
            '{"name": "disabled_rune", "version": "1.0.0", '
            '"hooks": [], "enabled": false}',
            encoding="utf-8",
        )

        manifests = load_manifests(extensions_dir)
        assert manifests == []


@pytest.mark.asyncio
async def test_spell_definition_execute_not_implemented() -> None:
    spell = SpellDefinition(
        name="test",
        description="test",
        parameters={},
        execution_mode=ExecutionMode.PARALLEL,
    )
    with pytest.raises(NotImplementedError):
        await spell.execute("cast-1", {})


@pytest.mark.asyncio
async def test_spell_definition_execute_with_handler() -> None:
    async def handler_with_id(spell_cast_id: str, params: dict, **kwargs) -> dict:
        return {"id": spell_cast_id, "params": params}

    spell1 = SpellDefinition(name="test1", description="test", handler=handler_with_id)
    result1 = await spell1.execute("cast-1", {"key": "val"})
    assert result1 == {"id": "cast-1", "params": {"key": "val"}}

    async def handler_params_only(params: dict, **kwargs) -> dict:
        return {"params": params}

    spell2 = SpellDefinition(
        name="test2", description="test", handler=handler_params_only
    )
    result2 = await spell2.execute("cast-2", {"num": 42})
    assert result2 == {"params": {"num": 42}}


class TestLoadRunesFromPaths:
    def test_dedup_by_name_first_wins(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir1,
            tempfile.TemporaryDirectory() as tmpdir2,
        ):
            rune1_dir = Path(tmpdir1) / "shared_name"
            rune1_dir.mkdir()
            (rune1_dir / "manifest.json").write_text(
                '{"name": "shared_name", "version": "1.0.0", '
                '"description": "First", "hooks": []}',
                encoding="utf-8",
            )

            rune2_dir = Path(tmpdir2) / "shared_name"
            rune2_dir.mkdir()
            (rune2_dir / "manifest.json").write_text(
                '{"name": "shared_name", "version": "2.0.0", '
                '"description": "Second", "hooks": []}',
                encoding="utf-8",
            )

            loads, diagnostics = load_runes_from_paths(
                [
                    (Path(tmpdir1), RuneScope.PROJECT),
                    (Path(tmpdir2), RuneScope.USER),
                ]
            )
            assert len(loads) == 1
            assert loads[0].manifest.version == "1.0.0"
            assert loads[0].manifest.scope == RuneScope.PROJECT

            shadowed = [
                d for d in diagnostics if d.kind == DiagnosticKind.SHADOWED_RUNE
            ]
            assert len(shadowed) == 1
            assert shadowed[0].rune_name == "shared_name"

    def test_winner_scope_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rune_dir = Path(tmpdir) / "my_rune"
            rune_dir.mkdir()
            (rune_dir / "manifest.json").write_text(
                '{"name": "my_rune", "version": "1.0.0", '
                '"description": "Test", "hooks": []}',
                encoding="utf-8",
            )

            loads, diagnostics = load_runes_from_paths(
                [(Path(tmpdir), RuneScope.AGENT)]
            )
            assert len(loads) == 1
            assert loads[0].manifest.scope == RuneScope.AGENT
            assert loads[0].manifest.path == str(rune_dir)

    def test_parse_warning_for_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rune_dir = Path(tmpdir) / "bad_rune"
            rune_dir.mkdir()
            (rune_dir / "manifest.json").write_text("{invalid json}", encoding="utf-8")

            loads, diagnostics = load_runes_from_paths([(Path(tmpdir), RuneScope.USER)])
            assert len(loads) == 0
            parse_warnings = [
                d for d in diagnostics if d.kind == DiagnosticKind.PARSE_WARNING
            ]
            assert len(parse_warnings) == 1
            assert parse_warnings[0].rune_name == "bad_rune"

    def test_load_failure_for_missing_entry_point(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rune_dir = Path(tmpdir) / "broken_rune"
            rune_dir.mkdir()
            (rune_dir / "manifest.json").write_text(
                '{"name": "broken_rune", "version": "1.0.0", '
                '"description": "Broken", "hooks": [], '
                '"entry_point": "nonexistent.py"}',
                encoding="utf-8",
            )

            loads, diagnostics = load_runes_from_paths([(Path(tmpdir), RuneScope.USER)])
            assert len(loads) == 1
            assert loads[0].factory is None
            load_failures = [
                d for d in diagnostics if d.kind == DiagnosticKind.LOAD_FAILURE
            ]
            assert len(load_failures) == 1
            assert load_failures[0].rune_name == "broken_rune"

    def test_multiple_scopes_no_duplicates(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir1,
            tempfile.TemporaryDirectory() as tmpdir2,
        ):
            rune1_dir = Path(tmpdir1) / "rune_a"
            rune1_dir.mkdir()
            (rune1_dir / "manifest.json").write_text(
                '{"name": "rune_a", "version": "1.0.0", '
                '"description": "A", "hooks": []}',
                encoding="utf-8",
            )

            rune2_dir = Path(tmpdir2) / "rune_b"
            rune2_dir.mkdir()
            (rune2_dir / "manifest.json").write_text(
                '{"name": "rune_b", "version": "1.0.0", '
                '"description": "B", "hooks": []}',
                encoding="utf-8",
            )

            loads, diagnostics = load_runes_from_paths(
                [
                    (Path(tmpdir1), RuneScope.PROJECT),
                    (Path(tmpdir2), RuneScope.USER),
                ]
            )
            assert len(loads) == 2
            names = {load.manifest.name for load in loads}
            assert names == {"rune_a", "rune_b"}


class TestLoadSkillManifest:
    def test_load_skill_manifest_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_data = """---
name: test-skill
description: Test skill for testing
version: "1.0.0"
license: MIT
compatibility: "Requires Python 3.10+"
metadata:
  author: test
---
# Test Skill

This is a test skill."""
            skill_md.write_text(skill_data, encoding="utf-8")

            manifest = load_skill_manifest(skill_dir)

            assert manifest is not None
            assert manifest.name == "test-skill"
            assert manifest.description == "Test skill for testing"
            assert manifest.version == "1.0.0"
            assert manifest.license == "MIT"
            assert manifest.compatibility == "Requires Python 3.10+"
            assert manifest.metadata == {"author": "test"}

    def test_load_skill_manifest_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test_skill"
            skill_dir.mkdir()

            manifest = load_skill_manifest(skill_dir)

            assert manifest is None

    def test_load_skill_manifest_missing_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_data = "# Test Skill\n\nNo frontmatter here."
            skill_md.write_text(skill_data, encoding="utf-8")

            manifest = load_skill_manifest(skill_dir)

            assert manifest is None

    def test_load_skill_manifest_invalid_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_data = """---
name: test-skill
description: Test
invalid yaml: [unclosed
---
Content"""
            skill_md.write_text(skill_data, encoding="utf-8")

            manifest = load_skill_manifest(skill_dir)

            assert manifest is None

    def test_load_skill_manifest_missing_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_data = """---
description: Test skill
---
Content"""
            skill_md.write_text(skill_data, encoding="utf-8")

            manifest = load_skill_manifest(skill_dir)

            assert manifest is None

    def test_load_skill_manifest_name_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "different-name"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_data = """---
name: test-skill
description: Test skill
---
Content"""
            skill_md.write_text(skill_data, encoding="utf-8")

            manifest = load_skill_manifest(skill_dir)

            assert manifest is None

    def test_load_skill_manifest_invalid_name_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_data = """---
name: Test_Skill
description: Test skill
---
Content"""
            skill_md.write_text(skill_data, encoding="utf-8")

            manifest = load_skill_manifest(skill_dir)

            assert manifest is None

    def test_load_skill_manifest_with_allowed_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_data = """---
name: test-skill
description: Test skill
allowed-tools: "read write edit"
---
Content"""
            skill_md.write_text(skill_data, encoding="utf-8")

            manifest = load_skill_manifest(skill_dir)

            assert manifest is not None
            assert manifest.allowed_tools == "read write edit"

    def test_load_skill_manifest_with_disable_model_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_data = """---
name: test-skill
description: Test skill
disable-model-invocation: true
---
Content"""
            skill_md.write_text(skill_data, encoding="utf-8")

            manifest = load_skill_manifest(skill_dir)

            assert manifest is not None
            assert manifest.disable_model_invocation is True

    def test_load_skill_manifest_bom_stripped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_data = (
                b"\xef\xbb\xbf---\nname: test-skill\ndescription: Test skill\n"
                b"---\nContent"
            )
            skill_md.write_bytes(skill_data)

            manifest = load_skill_manifest(skill_dir)

            assert manifest is not None
            assert manifest.name == "test-skill"
            assert manifest.description == "Test skill"

    def test_load_skill_manifest_invalid_structures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            # truncated frontmatter
            d1 = base / "trunc"
            d1.mkdir()
            (d1 / "SKILL.md").write_text("---incomplete", encoding="utf-8")
            assert load_skill_manifest(d1) is None

            # frontmatter not dict
            d2 = base / "notdict"
            d2.mkdir()
            (d2 / "SKILL.md").write_text("---\n- item1\n---\nbody", encoding="utf-8")
            assert load_skill_manifest(d2) is None

            # invalid description
            d3 = base / "baddesc"
            d3.mkdir()
            (d3 / "SKILL.md").write_text(
                "---\nname: baddesc\ndescription: 123\n---\nbody", encoding="utf-8"
            )
            assert load_skill_manifest(d3) is None

            # fallback metadata and disable_model_invocation
            d4 = base / "valid-extra"
            d4.mkdir()
            (d4 / "SKILL.md").write_text(
                "---\nname: valid-extra\ndescription: valid\nmetadata: non_dict\n"
                "disable-model-invocation: non_bool\n---\nbody",
                encoding="utf-8",
            )
            m = load_skill_manifest(d4)
            assert m is not None
            assert m.metadata == {}
            assert m.disable_model_invocation is False


class TestLoadSkillManifests:
    def test_load_skill_manifests_multiple(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)

            skill1_dir = skills_dir / "skill-one"
            skill1_dir.mkdir()
            (skill1_dir / "SKILL.md").write_text(
                """---
name: skill-one
description: First skill
---
Content""",
                encoding="utf-8",
            )

            skill2_dir = skills_dir / "skill-two"
            skill2_dir.mkdir()
            (skill2_dir / "SKILL.md").write_text(
                """---
name: skill-two
description: Second skill
---
Content""",
                encoding="utf-8",
            )

            manifests = load_skill_manifests(skills_dir)
            assert len(manifests) == 2
            names = {m.name for m in manifests}
            assert names == {"skill-one", "skill-two"}

    def test_load_skill_manifests_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)

            manifests = load_skill_manifests(skills_dir)
            assert manifests == []

    def test_load_skill_manifests_nonexistent_dir(self) -> None:
        manifests = load_skill_manifests(Path("/nonexistent/path"))
        assert manifests == []

    def test_load_skill_manifests_parse_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)

            bad_dir = skills_dir / "bad-skill"
            bad_dir.mkdir()
            (bad_dir / "SKILL.md").write_text("no frontmatter", encoding="utf-8")

            diagnostics: list = []
            manifests = load_skill_manifests(skills_dir, diagnostics=diagnostics)
            assert len(manifests) == 0
            assert len(diagnostics) == 1
            assert diagnostics[0].kind == SkillDiagnosticKind.PARSE_WARNING
            assert diagnostics[0].skill_name == "bad-skill"

    def test_load_skill_manifests_skips_dot_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)

            dot_dir = skills_dir / ".obsidian"
            dot_dir.mkdir()
            (dot_dir / "SKILL.md").write_text("no frontmatter", encoding="utf-8")

            good_dir = skills_dir / "real-skill"
            good_dir.mkdir()
            (good_dir / "SKILL.md").write_text(
                """---
name: real-skill
description: A real skill
---
Content""",
                encoding="utf-8",
            )

            diagnostics: list = []
            manifests = load_skill_manifests(skills_dir, diagnostics=diagnostics)
            assert len(manifests) == 1
            assert manifests[0].name == "real-skill"
            assert len(diagnostics) == 0

    def test_load_skill_manifests_skips_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)
            (skills_dir / "README.txt").write_text("info", encoding="utf-8")
            assert load_skill_manifests(skills_dir) == []


class TestLoadSkillsFromPaths:
    def test_load_skills_from_paths_skips_nonexistent(self) -> None:
        loads, diags = load_skills_from_paths(
            [("/nonexistent/skills/path", SkillScope.PROJECT)]
        )
        assert loads == []
        assert diags == []

    def test_dedup_by_name_first_wins(self) -> None:

        with (
            tempfile.TemporaryDirectory() as tmpdir1,
            tempfile.TemporaryDirectory() as tmpdir2,
        ):
            skill1_dir = Path(tmpdir1) / "shared-name"
            skill1_dir.mkdir()
            (skill1_dir / "SKILL.md").write_text(
                """---
name: shared-name
description: First skill
---
Content""",
                encoding="utf-8",
            )

            skill2_dir = Path(tmpdir2) / "shared-name"
            skill2_dir.mkdir()
            (skill2_dir / "SKILL.md").write_text(
                """---
name: shared-name
description: Second skill
---
Content""",
                encoding="utf-8",
            )

            loads, diagnostics = load_skills_from_paths(
                [
                    (Path(tmpdir1), SkillScope.PROJECT),
                    (Path(tmpdir2), SkillScope.USER),
                ]
            )
            assert len(loads) == 1
            assert loads[0].manifest.description == "First skill"
            assert loads[0].manifest.scope == SkillScope.PROJECT

            shadowed = [
                d for d in diagnostics if d.kind == SkillDiagnosticKind.SHADOWED_SKILL
            ]
            assert len(shadowed) == 1
            assert shadowed[0].skill_name == "shared-name"

    def test_winner_scope_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: my-skill
description: Test skill
---
Content""",
                encoding="utf-8",
            )

            loads, diagnostics = load_skills_from_paths(
                [(Path(tmpdir), SkillScope.AGENT)]
            )
            assert len(loads) == 1
            assert loads[0].manifest.scope == SkillScope.AGENT
            assert loads[0].manifest.path == str(skill_dir)

    def test_parse_warning_for_invalid_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "bad-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("no frontmatter", encoding="utf-8")

            loads, diagnostics = load_skills_from_paths(
                [(Path(tmpdir), SkillScope.USER)]
            )
            assert len(loads) == 0
            parse_warnings = [
                d for d in diagnostics if d.kind == SkillDiagnosticKind.PARSE_WARNING
            ]
            assert len(parse_warnings) == 1
            assert parse_warnings[0].skill_name == "bad-skill"

    def test_multiple_scopes_no_duplicates(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir1,
            tempfile.TemporaryDirectory() as tmpdir2,
        ):
            skill1_dir = Path(tmpdir1) / "skill-a"
            skill1_dir.mkdir()
            (skill1_dir / "SKILL.md").write_text(
                """---
name: skill-a
description: Skill A
---
Content""",
                encoding="utf-8",
            )

            skill2_dir = Path(tmpdir2) / "skill-b"
            skill2_dir.mkdir()
            (skill2_dir / "SKILL.md").write_text(
                """---
name: skill-b
description: Skill B
---
Content""",
                encoding="utf-8",
            )

            loads, diagnostics = load_skills_from_paths(
                [
                    (Path(tmpdir1), SkillScope.PROJECT),
                    (Path(tmpdir2), SkillScope.USER),
                ]
            )
            assert len(loads) == 2
            names = {load.manifest.name for load in loads}
            assert names == {"skill-a", "skill-b"}


class TestGetDefaultSkillPaths:
    def test_get_default_skill_paths_order(self) -> None:
        paths = get_default_skill_paths("test_agent")

        assert len(paths) == 3
        # Order: project, user, agent
        assert paths[0][1] == SkillScope.PROJECT
        assert paths[1][1] == SkillScope.USER
        assert paths[2][1] == SkillScope.AGENT
        # Agent path should have agent name substituted
        agent_path = paths[2][0]
        assert "test_agent" in str(agent_path)

    def test_discover_plugin_skill_paths(self, tmp_path: Path) -> None:
        plugins_root = tmp_path / ".agents" / "plugins"
        plugins_root.mkdir(parents=True)
        # Create non-directory file
        (plugins_root / "README.md").write_text("Plugins info", encoding="utf-8")
        # Create hidden directory
        (plugins_root / ".cache").mkdir()
        # Create plugin directory without skills/
        (plugins_root / "empty-plugin").mkdir()

        plugin_dir = plugins_root / "my-plugin"
        plugin_skills = plugin_dir / "skills" / "my-skill"
        plugin_skills.mkdir(parents=True)
        (plugin_skills / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test skill\n---\nBody",
            encoding="utf-8",
        )

        discovered = discover_plugin_skill_paths(cwd=tmp_path)
        assert len(discovered) == 1
        path, scope = discovered[0]
        assert path == plugin_dir / "skills"
        assert scope == SkillScope.PROJECT

        loads, diags = load_skills_from_paths(discovered)
        assert len(loads) == 1
        assert loads[0].manifest.name == "my-skill"


def test_load_factory_from_manifest_with_local_import() -> None:
    orig_sys_path = list(sys.path)
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            rune_dir = Path(tmpdir) / "imported_rune"
            rune_dir.mkdir()
            (rune_dir / "manifest.json").write_text(
                '{"name": "imported_rune", "version": "1.0.0", '
                '"description": "Test", "entry_point": "main.py"}',
                encoding="utf-8",
            )
            (rune_dir / "helper_mod.py").write_text(
                "HELPER_VALUE = 123\n", encoding="utf-8"
            )
            (rune_dir / "main.py").write_text(
                "import helper_mod\n\ndef rune_factory(api):\n    pass\n",
                encoding="utf-8",
            )

            manifest = load_manifest(rune_dir)
            assert manifest is not None
            factory = load_factory_from_manifest(manifest, rune_dir)
            assert factory is not None
            assert str(rune_dir.resolve()) in sys.path
    finally:
        sys.path.clear()
        sys.path.extend(orig_sys_path)


def test_load_factory_from_manifest_nested_entrypoint_with_imports() -> None:
    orig_sys_path = list(sys.path)
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            rune_dir = Path(tmpdir) / "nested_rune"
            rune_dir.mkdir()
            src_dir = rune_dir / "src"
            src_dir.mkdir()

            (rune_dir / "manifest.json").write_text(
                '{"name": "nested_rune", "version": "1.0.0", '
                '"description": "Test", "entry_point": "src/main.py"}',
                encoding="utf-8",
            )
            (rune_dir / "root_helper.py").write_text(
                "ROOT_VAL = 'root'\n", encoding="utf-8"
            )
            (src_dir / "nested_helper.py").write_text(
                "NESTED_VAL = 'nested'\n", encoding="utf-8"
            )
            (src_dir / "main.py").write_text(
                "import root_helper\n"
                "import nested_helper\n\n"
                "def rune_factory(api):\n"
                "    pass\n",
                encoding="utf-8",
            )

            manifest = load_manifest(rune_dir)
            assert manifest is not None
            factory = load_factory_from_manifest(manifest, rune_dir)
            assert factory is not None
            assert str(src_dir.resolve()) in sys.path
            assert str(rune_dir.resolve()) in sys.path
    finally:
        sys.path.clear()
        sys.path.extend(orig_sys_path)


def test_load_skill_manifest_caching() -> None:
    clear_skill_manifest_cache()
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "test-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\nname: test-skill\ndescription: A test skill.\n---\nBody",
            encoding="utf-8",
        )

        # First load - cache miss
        manifest1 = load_skill_manifest(skill_dir)
        assert manifest1 is not None
        assert manifest1.name == "test-skill"

        # Second load - cache hit, returns independent copy
        manifest2 = load_skill_manifest(skill_dir)
        assert manifest2 is not None
        assert manifest2.name == "test-skill"
        assert manifest1 is not manifest2

        # Mutate manifest2, manifest1 remains unaffected
        manifest2.scope = SkillScope.USER
        assert manifest1.scope == SkillScope.PROJECT

        # Update file content and mtime
        time.sleep(0.01)
        skill_file.write_text(
            "---\nname: test-skill\ndescription: Updated description.\n---\nBody",
            encoding="utf-8",
        )
        manifest3 = load_skill_manifest(skill_dir)
        assert manifest3 is not None
        assert manifest3.description == "Updated description."

        # Clear cache test
        clear_skill_manifest_cache()
        manifest4 = load_skill_manifest(skill_dir)
        assert manifest4 is not None
        assert manifest4.description == "Updated description."
