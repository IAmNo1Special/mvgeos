from __future__ import annotations

import dataclasses
import logging
from collections.abc import AsyncGenerator, Callable, Sequence
from pathlib import Path
from typing import Any

from mvgeos_provider.base import Realm
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse
from mvgeos_runes.loader import load_runes_from_paths
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import RuneContext, RuneShortcut
from mvgeos_runes.watcher import RuneWatcher
from mvgeos_tome.ledger import TomeLedger

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.event_bus import EventBus
from mvgeos_agent.loop import MvgeLoop
from mvgeos_agent.types import (
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    MvgeSpell,
    MvgeState,
    SessionResumeError,
    SpellResultMessage,
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
        name: str = "base-mvge",
        model: str = "openrouter/free",
        extension_dir: str | None = None,
        session_dir: Path | None = None,
        session_resume: str | None = None,
        provider_name: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        mana_budget: int | None = None,
        contemplation_level: str = "medium",
        contemplation_budget: int | None = None,
        exclude_contemplation: bool = False,
        runes_paths: Sequence[str] | None = None,
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
        self._mana_budget = mana_budget
        self._contemplation_level = contemplation_level
        self._contemplation_budget = contemplation_budget
        self._exclude_contemplation = exclude_contemplation
        self._runes_paths: Sequence[str] = runes_paths or [
            "~/.agents/.mvgeos/runes",
            f"~/.agents/.mvgeos/{name}/runes",
            ".agents/.mvgeos/runes",
        ]

        self._provider_registry = RealmRegistry()
        self._runner: RuneRunner | None = None
        self._watchers: list[RuneWatcher] = []
        self._model: Model | None = None
        self._realm: Realm | None = None
        self._agent_session: MvgeTome | None = None
        self._tome_ledger: TomeLedger | None = None
        self._loop: MvgeLoop | None = None
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

    async def _run_impl(self) -> MvgeInvocation:
        """Override in subclass to implement turn-processing logic."""
        raise NotImplementedError

    def _make_stream(
        self,
        model: Model,
        realm: Realm,
        state: MvgeState,
        temperature: float,
        max_tokens: int,
        mana_budget: int | None,
    ) -> Callable[[], AsyncGenerator[RealmResponse]]:
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

        async def stream_fn() -> AsyncGenerator[RealmResponse]:
            turns = 0
            while True:
                if turns >= state.max_turns:
                    raise RuntimeError("Max turns exceeded")
                turns += 1
                results_before = sum(
                    1
                    for inv in state.invocations
                    if isinstance(inv, SpellResultMessage)
                )
                async for response in realm.stream(
                    model=model,
                    invocations=state.invocations,
                    config=ChannelConfig(
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        contemplation_level=state.contemplation_level.value,
                        contemplation_budget=state.contemplation_budget,
                        exclude_contemplation=state.exclude_contemplation,
                        tools=tools,
                    ),
                ):
                    yield response
                results_after = sum(
                    1
                    for inv in state.invocations
                    if isinstance(inv, SpellResultMessage)
                )
                if results_after == results_before:
                    break

        return stream_fn

    async def initialize(self) -> None:
        if self._initialized:
            return

        await self._load_runes()

        self._model = self._compose_model(self._model_id)

        self._realm = self._provider_registry.create_realm(
            self._model, self._api_key, self._provider_name
        )

        # Only load seeker spells (meta-tools) - no preloaded builtin spells
        # All capabilities discovered on demand via tool_search, skill_search, mcp_search
        seeker_spells = []
        if self._runner is not None:
            for rs in self._runner.get_all_registered_spells():
                if rs.name in ("tool_search", "skill_search", "skill_execute", "mcp_search"):
                    # Use the actual SpellDefinition from rune (preserves execute)
                    seeker_spells.append(rs)

        self._tome_ledger = TomeLedger(self._session_dir)

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
            system_prompt=self._build_system_prompt(),
            model=dataclasses.asdict(self._model),
            contemplation_level=ContemplationLevel(self._contemplation_level),
            spells=self._build_spells(),
            invocations=[],
            mana_budget=self._mana_budget,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            contemplation_budget=self._contemplation_budget,
            exclude_contemplation=self._exclude_contemplation,
            rune_runner=self._runner,
            agent_session=self._agent_session,
            event_bus=self._event_bus,
        )

        self._loop = MvgeLoop(self._state)
        self._initialized = True

    async def _load_runes(self) -> None:
        """Load runes from all three levels (global, agent, project)."""
        factories, manifests = load_runes_from_paths(self._runes_paths, self._name)
        if not factories and not manifests:
            return

        self._runner = RuneRunner()
        self._runner.bind_context(RuneContext(cwd=str(Path.cwd()), mode="cli", agent_name=self._name, api_key=self._api_key))
        await self._runner.load_runes(factories, manifests)
        for pname, pconfig in self._runner.get_registered_providers().items():
            if isinstance(pconfig, dict):
                self._provider_registry.register_provider(pname, pconfig)

        # Start a watcher for each path that exists
        for path_str in self._runes_paths:
            expanded = str(path_str).replace("{agent_name}", self._name)
            path = Path(expanded).expanduser()
            if path.exists():
                watcher = RuneWatcher(path, self._runner)
                await watcher.start()
                self._watchers.append(watcher)

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
        self._state.system_prompt = self._build_system_prompt()

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
        self._state = None

    async def __aenter__(self) -> BaseMvge:
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
