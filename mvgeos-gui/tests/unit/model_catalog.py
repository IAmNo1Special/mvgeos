"""Unit tests for mvgeos_gui.model_catalog."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mvgeos_gui.model_catalog import (
    _provider_label,
    get_flat_model_ids,
    get_model_options,
)


def _mock_registry(models: list[MagicMock]) -> MagicMock:
    """Create a mock registry that returns the given models."""
    mock_registry = MagicMock()
    mock_registry.list_all.return_value = models
    return mock_registry


class TestProviderLabel:
    def test_known_providers(self) -> None:
        assert _provider_label("nvidia") == "NVIDIA"
        assert _provider_label("google") == "Google"
        assert _provider_label("anthropic") == "Anthropic"
        assert _provider_label("openai") == "OpenAI"

    def test_unknown_provider_title_cased(self) -> None:
        assert _provider_label("someprovider") == "Someprovider"


class TestGetModelOptions:
    def test_returns_dict_mapping_ids_to_names(self) -> None:
        mock_model = MagicMock()
        mock_model.id = "nvidia/nemotron-3-ultra-550b-a55b:free"
        mock_model.name = "NVIDIA: Nemotron 3 Ultra (free)"
        mock_model.free = True
        mock_model.provider = "nvidia"

        with patch("mvgeos_gui.model_catalog._get_registry") as mock_get_registry:
            mock_get_registry.return_value = _mock_registry([mock_model])
            options = get_model_options()

        assert options == {
            "nvidia/nemotron-3-ultra-550b-a55b:free": "NVIDIA: Nemotron 3 Ultra (free)"
        }

    def test_free_models_come_before_paid(self) -> None:
        mock_free = MagicMock()
        mock_free.id = "nvidia/nemotron-3-ultra-550b-a55b:free"
        mock_free.name = "NVIDIA: Nemotron 3 Ultra (free)"
        mock_free.free = True
        mock_free.provider = "nvidia"

        mock_paid = MagicMock()
        mock_paid.id = "nvidia/nemotron-3-ultra-550b-a55b"
        mock_paid.name = "NVIDIA: Nemotron 3 Ultra"
        mock_paid.free = False
        mock_paid.provider = "nvidia"

        with patch("mvgeos_gui.model_catalog._get_registry") as mock_get_registry:
            mock_get_registry.return_value = _mock_registry([mock_paid, mock_free])
            options = get_model_options()

        keys = list(options.keys())
        assert keys[0] == "nvidia/nemotron-3-ultra-550b-a55b:free"
        assert keys[1] == "nvidia/nemotron-3-ultra-550b-a55b"

    def test_tilde_models_excluded(self) -> None:
        mock_normal = MagicMock()
        mock_normal.id = "nvidia/nemotron-3-ultra-550b-a55b"
        mock_normal.name = "NVIDIA: Nemotron 3 Ultra"
        mock_normal.free = False
        mock_normal.provider = "nvidia"

        mock_alias = MagicMock()
        mock_alias.id = "~deepseek/deepseek-v4-flash-latest"
        mock_alias.name = "DeepSeek V4 Flash Latest"
        mock_alias.free = False
        mock_alias.provider = "deepseek"

        with patch("mvgeos_gui.model_catalog._get_registry") as mock_get_registry:
            mock_get_registry.return_value = _mock_registry([mock_normal, mock_alias])
            options = get_model_options()

        assert "~deepseek/deepseek-v4-flash-latest" not in options
        assert "nvidia/nemotron-3-ultra-550b-a55b" in options

    def test_empty_registry_returns_empty_dict(self) -> None:
        with patch("mvgeos_gui.model_catalog._get_registry") as mock_get_registry:
            mock_get_registry.return_value = _mock_registry([])
            options = get_model_options()

        assert options == {}


class TestGetFlatModelIds:
    def test_returns_list_of_ids(self) -> None:
        mock_model = MagicMock()
        mock_model.id = "nvidia/nemotron-3-ultra-550b-a55b:free"

        with patch("mvgeos_gui.model_catalog._get_registry") as mock_get_registry:
            mock_get_registry.return_value = _mock_registry([mock_model])
            ids = get_flat_model_ids()

        assert ids == ["nvidia/nemotron-3-ultra-550b-a55b:free"]

    def test_excludes_tilde_models(self) -> None:
        mock_normal = MagicMock()
        mock_normal.id = "nvidia/nemotron-3-ultra-550b-a55b"
        mock_alias = MagicMock()
        mock_alias.id = "~deepseek/deepseek-v4-flash-latest"

        with patch("mvgeos_gui.model_catalog._get_registry") as mock_get_registry:
            mock_get_registry.return_value = _mock_registry([mock_normal, mock_alias])
            ids = get_flat_model_ids()

        assert "~deepseek/deepseek-v4-flash-latest" not in ids
        assert "nvidia/nemotron-3-ultra-550b-a55b" in ids
