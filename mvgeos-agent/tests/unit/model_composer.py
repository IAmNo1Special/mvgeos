from __future__ import annotations

from pathlib import Path

import pytest
from mvgeos_provider.composer import ModelComposer
from mvgeos_provider.openrouter import OpenRouterRealm
from mvgeos_provider.registry import RealmRegistry

from mvgeos_agent.base_mvge import BaseMvge

CATALOG_MODEL_ID = "openai/gpt-oss-20b:free"


def _make_agent(tmp_path: Path) -> BaseMvge:
    return BaseMvge(api_key="test-key", tome_dir=tmp_path)


class TestModelComposerEquivalence:
    def test_base_mvge_compose_matches_model_composer(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path)
        expected_model, realm = ModelComposer(RealmRegistry()).compose(
            CATALOG_MODEL_ID, api_key="test-key"
        )
        actual_model = agent._compose_model(CATALOG_MODEL_ID)
        assert actual_model == expected_model
        assert isinstance(realm, OpenRouterRealm)

    def test_base_mvge_unknown_raises_like_model_composer(self, tmp_path: Path) -> None:
        agent = _make_agent(tmp_path)
        with pytest.raises(ValueError, match="Unknown model: unknown/model"):
            agent._compose_model("unknown/model")
        with pytest.raises(ValueError, match="Unknown model: unknown/model"):
            ModelComposer(RealmRegistry()).compose("unknown/model", api_key="test-key")
