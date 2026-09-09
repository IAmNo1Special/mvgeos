from unittest.mock import AsyncMock, MagicMock

import pytest
from mvgeos_tome.ledger import TomeLedger

from mvgeos_agent.commands import SLASH_COMMANDS, CommandAction, CommandDispatcher
from mvgeos_agent.protocol import MvgeAgent


def test_slash_commands_catalog() -> None:
    assert "/fork" in SLASH_COMMANDS
    assert "/leaves" in SLASH_COMMANDS
    assert "/checkout" in SLASH_COMMANDS
    assert "/undo" in SLASH_COMMANDS
    assert "/compact" in SLASH_COMMANDS
    assert "/skills" in SLASH_COMMANDS


def test_tome_ledger_list_leaves_and_parent_summoner(tmp_path) -> None:
    ledger = TomeLedger(tmp_path)
    meta = ledger.create_tome(str(tmp_path))
    tome_id = meta.id

    # Initially no content entries
    assert ledger.list_leaves(tome_id) == []

    # Summoner turn 1
    m1 = ledger.append_message(tome_id, "user", "Hello", parent_id=None)
    ledger.append_leaf(tome_id, m1.id)
    r1 = ledger.append_message(tome_id, "assistant", "Hi there", parent_id=m1.id)
    ledger.append_leaf(tome_id, r1.id)

    # Leaves should be [r1.id] (m1 is parent of r1)
    leaves = ledger.list_leaves(tome_id)
    assert leaves == [r1.id]

    # Parent of summoner message in turn 1 is None (it was root)
    assert ledger.get_parent_summoner_entry(tome_id, r1.id) is None

    # Summoner turn 2
    m2 = ledger.append_message(tome_id, "user", "How are you?", parent_id=r1.id)
    ledger.append_leaf(tome_id, m2.id)
    r2 = ledger.append_message(tome_id, "assistant", "I am well", parent_id=m2.id)
    ledger.append_leaf(tome_id, r2.id)

    # Leaves should be [r2.id]
    assert ledger.list_leaves(tome_id) == [r2.id]

    # Parent of summoner message in turn 2 should be r1
    parent_entry = ledger.get_parent_summoner_entry(tome_id, r2.id)
    assert parent_entry is not None
    assert parent_entry.id == r1.id


@pytest.mark.asyncio
async def test_command_dispatcher_tree_commands() -> None:
    agent = MagicMock(spec=MvgeAgent)
    agent.tome_id = "tome-xyz"
    agent.fork_tome = AsyncMock(return_value="tome-forked")
    agent.list_leaves = AsyncMock(return_value=["leaf-1", "leaf-2"])
    agent.checkout_leaf = AsyncMock()
    agent.undo = AsyncMock(return_value="leaf-1")
    agent.compact = AsyncMock(return_value="Compaction completed")
    agent.get_skills_catalog = MagicMock(
        return_value=[
            {
                "name": "test_skill",
                "description": "A skill",
                "scope": "project",
                "path": "/p",
            }
        ]
    )

    dispatcher = CommandDispatcher(agent)

    # /leaves
    outcome = await dispatcher.dispatch("/leaves")
    assert outcome.action == CommandAction.LEAVES_LISTED
    assert outcome.data["leaves"] == ["leaf-1", "leaf-2"]

    # /checkout
    outcome = await dispatcher.dispatch("/checkout leaf-1")
    assert outcome.action == CommandAction.LEAF_CHECKED_OUT
    assert outcome.data["leaf_id"] == "leaf-1"
    agent.checkout_leaf.assert_awaited_once_with("leaf-1")

    # /undo
    outcome = await dispatcher.dispatch("/undo")
    assert outcome.action == CommandAction.INVOCATION_UNDONE
    assert outcome.data["target_id"] == "leaf-1"
    agent.undo.assert_awaited_once()

    # /fork
    outcome = await dispatcher.dispatch("/fork entry-1")
    assert outcome.action == CommandAction.FORK_CREATED
    assert outcome.data["tome_id"] == "tome-forked"
    agent.fork_tome.assert_awaited_once_with("entry-1")

    # /compact
    outcome = await dispatcher.dispatch("/compact")
    assert outcome.action == CommandAction.MANA_COMPACTED
    assert outcome.data["result"] == "Compaction completed"

    # /skills
    outcome = await dispatcher.dispatch("/skills")
    assert outcome.action == CommandAction.SKILLS_LISTED
    assert len(outcome.data["skills"]) == 1
