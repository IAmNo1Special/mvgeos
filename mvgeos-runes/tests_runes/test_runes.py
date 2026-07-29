import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from mvgeos_runes.loader import RuneLoader
from mvgeos_runes.manifest import load_manifest
from mvgeos_runes.sigils import SigilRegistry
from mvgeos_runes.types import SigilHook


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


def test_sigil_registry_register_and_emit() -> None:
    registry = SigilRegistry()
    handler = MagicMock()

    registry.register(SigilHook.BEFORE_INVOCATION, handler)
    registry.emit(SigilHook.BEFORE_INVOCATION, {"test": "data"})

    handler.before_invocation.assert_called_once_with({"test": "data"})


def test_sigil_registry_multiple_handlers() -> None:
    registry = SigilRegistry()
    handler1 = MagicMock()
    handler2 = MagicMock()

    registry.register(SigilHook.BEFORE_INVOCATION, handler1)
    registry.register(SigilHook.BEFORE_INVOCATION, handler2)
    registry.emit(SigilHook.BEFORE_INVOCATION, {"key": "value"})

    handler1.before_invocation.assert_called_once_with({"key": "value"})
    handler2.before_invocation.assert_called_once_with({"key": "value"})


def test_sigil_registry_emit_no_handlers() -> None:
    registry = SigilRegistry()
    # Should not raise
    registry.emit(SigilHook.BEFORE_INVOCATION, {"test": "data"})


def test_sigil_registry_emit_async_handler() -> None:

    registry = SigilRegistry()

    async def async_handler(data):
        pass

    registry.register(SigilHook.BEFORE_INVOCATION, async_handler)
    # Should not raise
    registry.emit(SigilHook.BEFORE_INVOCATION, {"test": "data"})


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
