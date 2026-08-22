from __future__ import annotations

import logging
import re
from pathlib import Path

from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeMetadata

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.types import TomeResumeError

logger = logging.getLogger(__name__)

_TOME_FILE_PATTERN = re.compile(r"([a-f0-9]{32})\.jsonl$")


class TomeLifecycle:
    """Creates/opens tomes and starts MvgeTome sessions.

    Single owner of every path that brings a running session into existence:
    fresh start, resume, fork, and switch. BaseMvge and callers hand this
    module a ledger (and optionally the rune runner plus working directory);
    they get back a started MvgeTome or None when a sigil cancelled the
    transition.
    """

    def __init__(
        self,
        ledger: TomeLedger,
        rune_runner: RuneRunner | None = None,
        cwd: str | None = None,
    ) -> None:
        self._ledger = ledger
        self._rune_runner = rune_runner
        self._cwd = cwd if cwd is not None else str(Path.cwd())

    @property
    def ledger(self) -> TomeLedger:
        return self._ledger

    async def open_or_create(self, tome_resume: str | None = None) -> MvgeTome:
        """Resume the given tome, or create a fresh one when no target given.

        Raises TomeResumeError when a resume target is given but cannot be
        opened; mirrors the inline logic previously found in BaseMvge.
        """
        if tome_resume:
            metadata = self._ledger.open_tome(tome_resume)
            if metadata is None:
                raise TomeResumeError(tome_resume)
            return await self.start_from_metadata(metadata, reason="resume")

        metadata = self._ledger.create_tome(self._cwd)
        return await self.start_from_metadata(metadata, reason="startup")

    async def start_from_metadata(
        self, metadata: TomeMetadata, *, reason: str
    ) -> MvgeTome:
        """Wrap ledger metadata into a MvgeTome and emit its session start."""
        tome = MvgeTome(self._ledger, metadata, self._rune_runner)
        await tome.start(reason=reason)
        return tome

    async def fork_at(self, source: MvgeTome, entry_id: str) -> MvgeTome | None:
        """Fork the source session at an entry and start the branched tome.

        Returns None when a SESSION_BEFORE_FORK sigil cancels the fork or the
        ledger rejects the branch; failures leave the source session running.
        """
        fork_result = await source.before_fork(entry_id)
        if fork_result and fork_result.get("cancelled"):
            return None

        try:
            new_metadata = self._ledger.create_branched_tome(
                parent_tome_id=source.metadata.id,
                cwd=source.metadata.cwd,
                fork_from_leaf_id=entry_id,
            )
        except (KeyError, ValueError) as e:
            logger.exception("Failed to fork tome: %s", e)
            return None

        await source.shutdown(reason="fork", target_session_file=source.tome_file)
        return await self.start_from_metadata(new_metadata, reason="fork")

    async def switch_to(self, source: MvgeTome, target_file: Path) -> MvgeTome | None:
        """Shut the source session down and resume the tome behind a file.

        Returns None when a SESSION_BEFORE_SWITCH sigil cancels the switch,
        the file name carries no tome id, or the target tome cannot be opened;
        failures leave the source session running.
        """
        switch_result = await source.before_switch(str(target_file))
        if switch_result and switch_result.get("cancelled"):
            return None

        match = _TOME_FILE_PATTERN.search(str(target_file))
        if not match:
            logger.error("Could not parse tome_id from target_file: %s", target_file)
            return None
        target_tome_id = match.group(1)

        try:
            metadata = self._ledger.open_tome(target_tome_id)
            if metadata is None:
                logger.error("Failed to open target tome: %s", target_tome_id)
                return None
        except (ValueError, FileNotFoundError) as e:
            logger.exception("Failed to open target tome: %s", e)
            return None

        await source.shutdown(reason="resume", target_session_file=str(target_file))
        return await self.start_from_metadata(metadata, reason="resume")
