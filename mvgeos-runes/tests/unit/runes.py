import tempfile
from pathlib import Path

from mvgeos_runes.loader import (
    RuneLoader,
    load_factories,
    load_factory_from_manifest,
    load_manifests,
)
from mvgeos_runes.manifest import load_manifest
from mvgeos_runes.types import (
    RuneManifest,
    SigilHook,
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


def test_load_manifest_without_shortcuts() -> None:
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

        loader = RuneLoader(extensions_dir)
        manifests = loader.load_all()

        assert len(manifests) == 2
        names = {m.name for m in manifests}
        assert names == {"rune1", "rune2"}


def test_rune_loader_load_all_empty_dir() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        extensions_dir = Path(tmpdir)

        loader = RuneLoader(extensions_dir)
        manifests = loader.load_all()

        assert manifests == []


def test_rune_loader_load_all_nonexistent_dir() -> None:
    loader = RuneLoader(Path("/nonexistent/path"))
    manifests = loader.load_all()

    assert manifests == []


def test_load_factories_empty_dir() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        factories = load_factories(Path(tmpdir))
        assert factories == []


def test_load_factories_nonexistent_dir() -> None:
    factories = load_factories(Path("/nonexistent/path"))
    assert factories == []


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


def test_load_manifest_without_system_deps() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test rune", "hooks": []}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert manifest.system_deps == []


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


def test_load_manifest_without_python_deps() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test rune", "hooks": []}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert manifest.python_deps == []


def test_load_manifest_enabled_defaults_true() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        rune_dir = Path(tmpdir) / "test_rune"
        rune_dir.mkdir()
        manifest_file = rune_dir / "manifest.json"
        manifest_data = (
            '{"name": "test_rune", "version": "1.0.0", '
            '"description": "Test rune", "hooks": []}'
        )
        manifest_file.write_text(manifest_data, encoding="utf-8")

        manifest = load_manifest(rune_dir)

        assert manifest is not None
        assert manifest.enabled is True


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


def test_load_all_skips_disabled_runes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        extensions_dir = Path(tmpdir)

        enabled_dir = extensions_dir / "enabled_rune"
        enabled_dir.mkdir()
        (enabled_dir / "manifest.json").write_text(
            '{"name": "enabled_rune", "version": "1.0.0", "hooks": []}',
            encoding="utf-8",
        )

        disabled_dir = extensions_dir / "disabled_rune"
        disabled_dir.mkdir()
        (disabled_dir / "manifest.json").write_text(
            '{"name": "disabled_rune", "version": "1.0.0", '
            '"hooks": [], "enabled": false}',
            encoding="utf-8",
        )

        loader = RuneLoader(extensions_dir)
        manifests = loader.load_all()

        assert len(manifests) == 1
        assert manifests[0].name == "enabled_rune"


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


def test_load_factories_skips_disabled_runes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        extensions_dir = Path(tmpdir)

        disabled_dir = extensions_dir / "disabled_rune"
        disabled_dir.mkdir()
        (disabled_dir / "manifest.json").write_text(
            '{"name": "disabled_rune", "version": "1.0.0", "hooks": [], '
            '"entry_point": "rune.py", "enabled": false}',
            encoding="utf-8",
        )
        (disabled_dir / "rune.py").write_text(
            "def rune_factory(api): pass", encoding="utf-8"
        )

        factories = load_factories(extensions_dir)
        assert factories == []


def test_spell_definition_execute_not_implemented() -> None:
    from mvgeos_runes.types import ExecutionMode, SpellDefinition

    spell = SpellDefinition(
        name="test",
        description="test",
        parameters={},
        execution_mode=ExecutionMode.PARALLEL,
    )

    import asyncio

    import pytest

    with pytest.raises(NotImplementedError):
        asyncio.run(spell.execute("cast-1", {}))
