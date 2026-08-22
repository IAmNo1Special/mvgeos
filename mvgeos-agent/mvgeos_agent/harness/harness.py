from __future__ import annotations

from typing import Any

from mvgeos_provider.base import Realm
from mvgeos_provider.types import Model

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.core_loop import LoopCallbacks, StreamFn
from mvgeos_agent.harness.compaction.compaction import (
    DEFAULT_COMPACTION_SETTINGS,
    CompactionSettings,
)
from mvgeos_agent.harness.compaction.compaction_runner import CompactionRunner
from mvgeos_agent.mvge_loop import MvgeLoop
from mvgeos_agent.types import AbortSignal, MvgeInvocation, MvgeState, SummonerRequest


class MvgeHarness:
    """Wraps MvgeLoop and owns session lifecycle and compaction.

    Matches Pi's AgentHarness architecture.

    Encapsulates:
    - MvgeTome session lifecycle (startup, shutdown, record_message, record_compaction)
    - MvgeLoop turn execution and event routing
    - CompactionRunner execution during after_invocation callbacks
    """

    def __init__(
        self,
        loop: MvgeLoop | None = None,
        compaction: CompactionRunner | None = None,
        callbacks: LoopCallbacks | None = None,
        *,
        state: MvgeState | None = None,
        tome: MvgeTome | None = None,
        realm: Realm | None = None,
        model: Model | None = None,
        compaction_settings: CompactionSettings = DEFAULT_COMPACTION_SETTINGS,
    ) -> None:
        if loop is not None:
            self._loop = loop
            self._state = state or loop.state
        elif state is not None:
            self._state = state
            self._loop = MvgeLoop(state)
        else:
            raise ValueError("MvgeHarness requires either 'loop' or 'state'")

        self._tome: MvgeTome | None = tome or getattr(self._state, "agent_tome", None)
        self._realm = realm
        self._model = model
        self._compaction_settings = compaction_settings
        self._callbacks = callbacks

        self._compaction: CompactionRunner | None
        if compaction is not None:
            self._compaction = compaction
        elif self._realm is not None and self._model is not None:
            self._compaction = CompactionRunner(
                realm=self._realm,
                model=self._model,
                emit=self._loop.emit,
                settings=self._compaction_settings,
                tome=self._tome,
            )
        else:
            self._compaction = None

    @property
    def loop(self) -> MvgeLoop:
        return self._loop

    @property
    def state(self) -> MvgeState:
        return self._state

    @property
    def tome(self) -> MvgeTome | None:
        return self._tome

    @property
    def compaction(self) -> CompactionRunner | None:
        return self._compaction

    def switch_tome(self, tome: MvgeTome) -> None:
        """Switch active Tome session reference and update CompactionRunner."""
        self._tome = tome
        self._state.agent_tome = tome
        if self._compaction is not None:
            self._compaction._tome = tome

    def set_model_and_realm(self, model: Model, realm: Realm) -> None:
        """Update model and realm references on harness and compaction runner."""
        self._model = model
        self._realm = realm
        comp: CompactionRunner | None = self._compaction
        if comp is None:
            self._compaction = CompactionRunner(
                realm=self._realm,
                model=self._model,
                emit=self._loop.emit,
                settings=self._compaction_settings,
                tome=self._tome,
            )
        else:
            comp._model = model
            comp._realm = realm

    async def run(
        self,
        stream_fn: StreamFn,
        model: dict[str, Any],
        contemplation_level: str = "medium",
        signal: AbortSignal | None = None,
        prompt: str | None = None,
    ) -> MvgeInvocation:
        """Run the harness by driving turn processing via MvgeLoop.run()."""
        if prompt is not None:
            self._state.invocations.append(SummonerRequest(role="user", content=prompt))

        # Build effective callbacks and set after_invocation on the loop
        effective_callbacks = self._callbacks or self._loop._build_callbacks()
        original_after_invocation = effective_callbacks.after_invocation

        async def after_invocation_with_compaction(
            invocations: list[MvgeInvocation],
        ) -> list[MvgeInvocation] | None:
            if self._compaction is not None:
                replacement = await self._compaction.maybe_compact(
                    list(invocations), signal
                )
                if replacement is not None:
                    invocations = list(replacement)
                    self._state.invocations = list(replacement)
            if original_after_invocation is not None:
                replacement = await original_after_invocation(list(invocations))
                if replacement is not None:
                    invocations = list(replacement)
                    self._state.invocations = list(replacement)
            return invocations

        self._loop.set_after_invocation(after_invocation_with_compaction)

        return await self._loop.run(
            stream_fn=stream_fn,
            model=model,
            contemplation_level=contemplation_level,
            signal=signal,
        )


__all__ = ["MvgeHarness"]
