from __future__ import annotations

import dataclasses
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any

from mvgeos_harness import MvgeHarness
from mvgeos_provider.base import Realm
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse
from mvgeos_runes.loader import load_runes_from_paths
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import RuneContext, RuneScope, RuneShortcut, SigilHook
from mvgeos_runes.watcher import RuneWatcher
from mvgeos_tome.ledger import TomeLedger

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.compaction import DEFAULT_COMPACTION_SETTINGS, CompactionSettings
from mvgeos_agent.compaction_runner import CompactionRunner
from mvgeos_agent.constants import (
    DEFAULT_AGENT_NAME,
    DEFAULT_MODEL,
    resolve_rune_paths,
)
from mvgeos_agent.event_bus import EventBus
from mvgeos_agent.loop import MvgeLoop, StreamFn
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    MvgeSpell,
    MvgeState,
    SessionResumeError,
    SummonerRequest,
)

logger = logging.getLogger(__name__)


class BaseMvge:
    """Abstract agent skeleton (Template Method pattern).

    Subclasses override:
      _build_spells()        -> list of MvgeSpell instances
      _build_system_prompt() -> system prompt string
      _run_impl()            -> turn-processing logic

    The public run() method is the sealed template that calls initialize(),
    appends the prompt, rebuilds the system prompt, and delegates to _run_impl().
    """

    def __init__(
        self,
        api_key: str,
        *,
        name: str = DEFAULT_AGENT_NAME,
        model: str = DEFAULT_MODEL,
        extension_dir: str | None = None,
        session_dir: Path | None = None,
        session_resume: str | None = None,
        provider_name: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        contemplation_level: str = "medium",
        contemplation_budget: int | None = None,
        exclude_contemplation: bool = False,
        runes_paths: Sequence[str] | None = None,
        compaction: CompactionSettings = DEFAULT_COMPACTION_SETTINGS,
    ) -> None:
        self._api_key = api_key
        self._name = name
        self._model_id = model
        self._extension_dir = extension_dir
        self._session_dir = session_dir or Path("~/.agents/.mvgeos/tomes").expanduser()
        self._session_resume = session_resume
        self._provider_name = provider_name
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._contemplation_level = contemplation_level
        self._contemplation_budget = contemplation_budget
        self._exclude_contemplation = exclude_contemplation
        self._compaction_settings = compaction
        if runes_paths is not None:
            self._runes_paths: list[Path] = [
                Path(str(p)).expanduser() for p in runes_paths
            ]
        else:
            self._runes_paths = resolve_rune_paths(name)

        self._provider_registry = RealmRegistry()
        self._runner: RuneRunner | None = None
        self._watchers: list[RuneWatcher] = []
        self._model: Model | None = None
        self._realm: Realm | None = None
        self._agent_session: MvgeTome | None = None
        self._tome_ledger: TomeLedger | None = None
        self._loop: MvgeLoop | None = None
        self._compaction: CompactionRunner | None = None
        self._state: MvgeState | None = None
        self._event_bus = EventBus()
        self._initialized = False

    @property
    def session_id(self) -> str | None:
        if self._tome_ledger is not None:
            # Get the first tome's ID
            tomes = self._tome_ledger.list_tomes()
            if tomes:
                return tomes[0].id
        return None

    @property
    def registered_commands(self) -> list[str]:
        if self._runner is None:
            return []
        return [c.name for c in self._runner.get_commands()]

    @property
    def registered_shortcuts(self) -> list[RuneShortcut]:
        if self._runner is None:
            return []
        return self._runner.get_shortcuts()

    @property
    def registered_providers(self) -> list[str]:
        return self._provider_registry.get_registered_providers()

    @property
    def config_dir(self) -> Path:
        return Path(f"~/.agents/.mvgeos/{self._name}").expanduser()

    def on(
        self,
        event_type: MvgeEventType | str,
        callback: Callable[[MvgeEvent], None],
    ) -> Callable[[], None]:
        if isinstance(event_type, str):
            event_type = MvgeEventType(event_type)
        return self._event_bus.on(event_type, callback)

    def steer(self, text: str) -> None:
        if self._state is not None:
            self._state.steer_queue.append(SummonerRequest(role="user", content=text))

    def follow_up(self, text: str) -> None:
        if self._state is not None:
            self._state.followup_queue.append(
                SummonerRequest(role="user", content=text)
            )

    def _compose_model(self, model_id: str) -> Model:
        model = self._provider_registry.compose_model(
            model_id, self._api_key, self._provider_name
        )
        if model is not None:
            return model
        from mvgeos_provider.models import get_model

        model_info = get_model(model_id)
        if model_info is None:
            raise ValueError(f"Unknown model: {model_id}")
        return Model(
            id=model_info.id,
            name=model_info.name,
            realm=model_info.realm,
            base_url=model_info.base_url,
            api_key=self._api_key,
            max_completion_mana=model_info.max_completion_mana,
            context_window=model_info.context_window,
            max_tokens=model_info.max_tokens,
            headers=dict(model_info.headers or {}),
            supported_parameters=list(model_info.supported_parameters),
        )

    def _build_spells(self) -> list[MvgeSpell]:
        """Override in subclass to provide agent-specific spells."""
        return []

    def _build_system_prompt(self) -> str:
        """Override in subclass to provide agent-specific system prompt."""
        return "You are a helpful AI agent."

    async def _build_system_prompt_async(self) -> str:
        """Async version that supports rune prompt injection via sigil hooks.
        Override in subclass for async prompt building with rune injection.
        Default delegates to sync version for backward compatibility.
        """
        if self._runner is not None:
            prompt_data: dict[str, Any] = {
                "base_prompt": self._build_system_prompt(),
                "spell_names": [],
                "config_dir": str(self.config_dir) if self.config_dir else "",
                "custom_prompt": getattr(self, "_custom_system_prompt", ""),
                "agent_name": self._name,
                "cwd": str(Path.cwd()),
            }
            prompt_data = await self._runner.emit_chain(
                SigilHook.BEFORE_MVGE_START, prompt_data
            )
            return str(prompt_data.get("base_prompt", self._build_system_prompt()))
        return self._build_system_prompt()

    async def _run_impl(self) -> MvgeInvocation:
        """Default implementation using the harness."""
        assert self._model is not None
        assert self._realm is not None
        assert self._state is not None
        assert self._loop is not None
        assert self._harness is not None

        stream_fn = self._make_stream_fn(
            self._model,
            self._realm,
            self._state,
            self._temperature,
            self._max_tokens,
        )

        return await self._harness.run(
            stream_fn,
            model=dataclasses.asdict(self._model),
            contemplation_level=self._contemplation_level,
        )

    def _make_stream_fn(
        self,
        model: Model,
        realm: Realm,
        state: MvgeState,
        temperature: float,
        max_tokens: int,
    ) -> StreamFn:
        """Build the per-turn channel the loop calls to reach the Realm.

        The loop owns the turn cycle, so this only channels one request. It is
        handed the transcript for that turn rather than reading agent state.
        """
        tools = [
            {
                "type": "function",
                "function": {
                    "name": spell.name,
                    "description": spell.description,
                    "parameters": spell.parameters,
                },
            }
            for spell in state.spells
            if spell.parameters
        ]

        def stream_fn(
            invocations: list[MvgeInvocation],
        ) -> AsyncIterator[RealmResponse]:
            return realm.stream(
                model=model,
                invocations=invocations,
                config=ChannelConfig(
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    contemplation_level=state.contemplation_level.value,
                    contemplation_budget=state.contemplation_budget,
                    exclude_contemplation=state.exclude_contemplation,
                    tools=tools,
                ),
            )

        return stream_fn

    async def initialize(self) -> None:
        if self._initialized:
            return

        await self._load_runes()

        self._model = self._compose_model(self._model_id)

        self._realm = self._provider_registry.create_realm(
            self._model, self._api_key, self._provider_name
        )

        # Initialize tome ledger (needed for both new and resumed sessions)
        self._tome_ledger = TomeLedger(self._session_dir)

        # Emit BEFORE_MVGE_START to allow runes to inject prompt additions
        base_prompt = await self._build_system_prompt_async()
        prompt_data: dict[str, Any] = {
            "base_prompt": base_prompt,
            "spell_names": [],
            "config_dir": str(self.config_dir) if self.config_dir else "",
            "custom_prompt": getattr(self, "_custom_system_prompt", ""),
            "agent_name": self._name,
            "cwd": str(Path.cwd()),
        }
        if self._runner is not None:
            prompt_data = await self._runner.emit_chain(
                SigilHook.BEFORE_MVGE_START, prompt_data
            )

        # Build final system prompt from prompt_data (may have been modified by runes)
        final_prompt = str(prompt_data.get("base_prompt", base_prompt))

        self._model = self._compose_model(self._model_id)

        self._realm = self._provider_registry.create_realm(
            self._model, self._api_key, self._provider_name
        )

        if self._session_resume:
            resume_path = Path(self._session_resume)
            if not resume_path.exists():
                raise FileNotFoundError(
                    f"Session file not found: {self._session_resume}"
                )
            tome_id = resume_path.stem
            meta = self._tome_ledger.open_tome(tome_id)
            if meta is None:
                raise SessionResumeError(
                    f"Failed to resume session {self._session_resume}: tome not found"
                )
            self._agent_session = MvgeTome(self._tome_ledger, meta, self._runner)
            await self._agent_session.start(reason="resume")

        if self._agent_session is None:
            meta = self._tome_ledger.create_tome(str(Path.cwd()))
            self._agent_session = MvgeTome(self._tome_ledger, meta, self._runner)
            await self._agent_session.start(reason="startup")

        self._state = MvgeState(
            system_prompt=final_prompt,
            model=dataclasses.asdict(self._model),
            contemplation_level=ContemplationLevel(self._contemplation_level),
            spells=self._build_spells(),
            invocations=[],
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            contemplation_budget=self._contemplation_budget,
            exclude_contemplation=self._exclude_contemplation,
            rune_runner=self._runner,
            agent_session=self._agent_session,
            event_bus=self._event_bus,
        )

        self._loop = MvgeLoop(self._state)
        self._harness: MvgeHarness | None = None

        if self._realm is not None and self._model is not None:
            self._compaction = CompactionRunner(
                realm=self._realm,
                model=self._model,
                emit=self._loop.emit,
                settings=self._compaction_settings,
                tome=self._agent_session,
            )
            # Build callbacks from the loop (includes rune sigil handlers)
            callbacks = self._loop._build_callbacks()
            # Add compaction callback to the callbacks
            original_after_invocation = callbacks.after_invocation

            async def after_invocation_with_compaction(
                invocations: list[MvgeInvocation],
            ) -> list[MvgeInvocation] | None:
                # Run compaction first
                if self._compaction is not None:
                    replacement = await self._compaction.maybe_compact(
                        list(invocations)
                    )
                    if replacement is not None:
                        invocations = list(replacement)
                # Then run original after_invocation for Rune-specific mutations
                if original_after_invocation is not None:
                    replacement = await original_after_invocation(list(invocations))
                    if replacement is not None:
                        invocations = list(replacement)
                return invocations

            callbacks.after_invocation = after_invocation_with_compaction
            # Create harness that wraps the loop and owns compaction/lifecycle
            self._harness = MvgeHarness(self._loop, self._compaction, callbacks)

        self._initialized = True

    async def _load_runes(self) -> None:
        """Load runes from all three levels (global, agent, project)."""
        paths_with_scope = self._build_rune_paths_with_scope()
        loads, diagnostics = load_runes_from_paths(paths_with_scope, self._name)
        if not loads:
            return

        self._runner = RuneRunner()
        self._runner.bind_context(
            RuneContext(
                cwd=str(Path.cwd()),
                mode="cli",
                agent_name=self._name,
                api_key=self._api_key,
            )
        )
        await self._runner.load_rune_loads(loads, diagnostics)
        for pname, pconfig in self._runner.get_registered_providers().items():
            if isinstance(pconfig, dict):
                self._provider_registry.register_provider(pname, pconfig)

        for path, _ in paths_with_scope:
            if path.exists():
                watcher = RuneWatcher(path, self._runner)
                await watcher.start()
                self._watchers.append(watcher)

    def _build_rune_paths_with_scope(self) -> list[tuple[Path, RuneScope]]:
        result: list[tuple[Path, RuneScope]] = []
        for path in self._runes_paths:
            resolved = Path(str(path).replace("{agent_name}", self._name)).expanduser()
            if ".mvgeos/runes" in str(path) and "{agent_name}" not in str(path):
                scope = RuneScope.USER
            elif "{agent_name}" in str(path):
                scope = RuneScope.AGENT
            else:
                scope = RuneScope.PROJECT
            result.append((resolved, scope))
        return result

    async def switch_model(self, model_id: str) -> None:
        """Switch the active model, preserving the current session context."""
        if model_id == self._model_id:
            return
        self._model_id = model_id
        if not self._initialized:
            return

        assert self._model is not None
        new_model = self._compose_model(model_id)
        if new_model.provider != self._model.provider:
            if self._realm is not None:
                await self._realm.close()
            self._realm = self._provider_registry.create_realm(
                new_model, self._api_key, self._provider_name
            )
        self._model = new_model
        assert self._state is not None
        self._state.model = dataclasses.asdict(new_model)

    async def run(self, prompt: str) -> MvgeInvocation:
        """Template method. Sealed entry point for all agents."""
        if not self._initialized:
            await self.initialize()

        assert self._model is not None
        assert self._realm is not None
        assert self._state is not None
        assert self._loop is not None

        self._state.invocations.append(SummonerRequest(role="user", content=prompt))
        self._state.system_prompt = await self._build_system_prompt_async()

        return await self._run_impl()

    async def close(self) -> None:
        if self._agent_session is not None:
            await self._agent_session.shutdown(reason="quit")
        for watcher in self._watchers:
            await watcher.stop()
        self._watchers.clear()
        if self._realm is not None:
            await self._realm.close()
            self._realm = None
        self._initialized = False
        self._runner = None
        self._agent_session = None
        self._session_manager = None
        self._loop = None
        self._harness = None
        self._state = None

    async def __aenter__(self) -> BaseMvge:
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
