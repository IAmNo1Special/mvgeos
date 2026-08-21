from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mvgeos_provider.types import Model
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import SigilHook
from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeMetadata

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.base_mvge import BaseMvge
from mvgeos_agent.tome_lifecycle import TomeLifecycle


@pytest.fixture
def tome_ledger() -> TomeLedger:
    with tempfile.TemporaryDirectory() as tmp:
        yield TomeLedger(Path(tmp))


@pytest.fixture
def tome_metadata(tome_ledger: TomeLedger) -> TomeMetadata:
    return tome_ledger.create_tome("/test")


@pytest.fixture
def rune_runner() -> RuneRunner:
    return RuneRunner()


@pytest.fixture
def started_source(
    tome_ledger: TomeLedger,
    tome_metadata: TomeMetadata,
    rune_runner: RuneRunner,
) -> MvgeTome:
    return MvgeTome(tome_ledger, tome_metadata, rune_runner)


@pytest.mark.asyncio
async def test_switch_to_cancelled(
    rune_runner: RuneRunner, started_source: MvgeTome
) -> None:
    def canceller(data: dict) -> dict:
        return {"cancel": True}

    rune_runner.register_handler(SigilHook.SESSION_BEFORE_SWITCH, canceller)
    await started_source.start(reason="startup")

    lifecycle = TomeLifecycle(started_source.ledger, rune_runner)
    result = await lifecycle.switch_to(started_source, Path("/path/to/target.jsonl"))
    assert result is None


@pytest.mark.asyncio
async def test_switch_to_invalid_tome_id(
    rune_runner: RuneRunner, started_source: MvgeTome
) -> None:
    await started_source.start(reason="startup")

    # Invalid format - no 32-char hex
    lifecycle = TomeLifecycle(started_source.ledger, rune_runner)
    result = await lifecycle.switch_to(started_source, Path("/path/to/invalid.jsonl"))
    assert result is None


@pytest.mark.asyncio
async def test_switch_to_tome_not_found(
    rune_runner: RuneRunner, started_source: MvgeTome
) -> None:
    await started_source.start(reason="startup")

    # Valid format but tome doesn't exist
    lifecycle = TomeLifecycle(started_source.ledger, rune_runner)
    target_file = Path("/path/to") / f"{'a' * 32}.jsonl"
    result = await lifecycle.switch_to(started_source, target_file)
    assert result is None


@pytest.mark.asyncio
async def test_switch_to_success(
    tome_ledger: TomeLedger, rune_runner: RuneRunner, started_source: MvgeTome
) -> None:
    await started_source.start(reason="startup")

    # Create a second tome to switch to
    meta2 = tome_ledger.create_tome("/test2")
    target_file = tome_ledger.tome_file(meta2.id)

    lifecycle = TomeLifecycle(tome_ledger, rune_runner)
    result = await lifecycle.switch_to(started_source, target_file)
    assert result is not None
    assert result.tome_id == meta2.id


@pytest.mark.asyncio
async def test_fork_at_cancelled(
    tome_ledger: TomeLedger, rune_runner: RuneRunner, started_source: MvgeTome
) -> None:
    def canceller(data: dict) -> dict:
        return {"cancel": True}

    rune_runner.register_handler(SigilHook.SESSION_BEFORE_FORK, canceller)
    await started_source.start(reason="startup")

    entry = tome_ledger.append_message(
        tome_id=started_source.tome_id, role="user", content="test"
    )

    lifecycle = TomeLifecycle(tome_ledger, rune_runner)
    result = await lifecycle.fork_at(started_source, entry.id)
    assert result is None


@pytest.mark.asyncio
async def test_fork_at_success(
    tome_ledger: TomeLedger, rune_runner: RuneRunner, started_source: MvgeTome
) -> None:
    await started_source.start(reason="startup")

    entry = tome_ledger.append_message(
        tome_id=started_source.tome_id, role="user", content="test"
    )

    lifecycle = TomeLifecycle(tome_ledger, rune_runner)
    result = await lifecycle.fork_at(started_source, entry.id)
    assert result is not None
    assert result.tome_id != started_source.tome_id

    # The branch copies the ancestor chain up to the fork entry
    branched_entries = tome_ledger.get_entries(result.tome_id)
    assert any(e.id == entry.id for e in branched_entries)


@pytest.mark.asyncio
async def test_fork_at_invalid_entry_creates_branched(
    tome_ledger: TomeLedger, rune_runner: RuneRunner, started_source: MvgeTome
) -> None:
    await started_source.start(reason="startup")

    # Invalid entry ID - ledger doesn't validate, creates branched tome anyway
    lifecycle = TomeLifecycle(tome_ledger, rune_runner)
    result = await lifecycle.fork_at(started_source, "nonexistent-entry")
    assert result is not None
    assert result.tome_id != started_source.tome_id


def _mock_model() -> Model:
    return Model(
        id="test-model",
        name="test-model",
        realm="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
        context_window=4096,
        max_tokens=1024,
    )


@pytest.mark.asyncio
async def test_open_or_create_matches_base_mvge_inline_semantics() -> None:
    """Issue #91: BaseMvge's inline tome logic and TomeLifecycle must produce
    identical session state for a fresh session."""
    with (
        tempfile.TemporaryDirectory() as agent_dir,
        tempfile.TemporaryDirectory() as lifecycle_dir,
    ):
        agent = BaseMvge(api_key="test-key", tome_dir=Path(agent_dir))
        agent._compose_model = MagicMock(return_value=_mock_model())  # type: ignore[method-assign]
        agent._provider_registry.create_realm = MagicMock()  # type: ignore[method-assign]
        with patch.object(
            agent,
            "_build_system_prompt_async",
            new_callable=AsyncMock,
            return_value="sys",
        ):
            await agent.initialize()
        assert agent._agent_tome is not None

        lifecycle = TomeLifecycle(TomeLedger(Path(lifecycle_dir)), None)
        tome = await lifecycle.open_or_create(None)

        assert tome.metadata.cwd == str(Path.cwd())
        assert tome.metadata.cwd == agent._agent_tome.metadata.cwd
        assert tome.metadata.parent_tome_id is None
        assert tome.record_custom("probe", {}) is not None
