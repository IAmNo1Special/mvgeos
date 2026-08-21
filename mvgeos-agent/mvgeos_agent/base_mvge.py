from __future__ import annotations

import dataclasses
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any, cast

from mvgeos_provider.base import Realm
from mvgeos_provider.composer import ModelComposer
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse
from mvgeos_runes.loader import (
    get_default_skill_paths,
    load_runes_from_paths,
    load_skills_from_paths,
)
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    Diagnostic,
    RuneContext,
    RuneScope,
    RuneShortcut,
    SigilHook,
    SkillDiagnostic,
    SpellDefinition,
)
from mvgeos_runes.watcher import RuneWatcher
from mvgeos_tome.ledger import TomeLedger

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.config_parsing import ConfigParsing
from mvgeos_agent.constants import (
    DEFAULT_AGENT_NAME,
    DEFAULT_TOME_DIR,
)
from mvgeos_agent.core_loop import StreamFn
from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.event_bus import EventBus
from mvgeos_agent.harness import (
    DEFAULT_COMPACTION_SETTINGS,
    CompactionRunner,
    CompactionSettings,
    MvgeHarness,
)
from mvgeos_agent.mvge_loop import MvgeLoop
from mvgeos_agent.snapshot import RuntimeSnapshot
from mvgeos_agent.types import (
    AbortController,
    AbortSignal,
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    MvgeInvocation,
    MvgeSpell,
    MvgeState,
    QueueMode,
    SummonerRequest,
    TomeResumeError,
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
        extension_dir: str | None = None,
        tome_dir: Path | None = None,
        tome_resume: str | None = None,
        provider_name: str | None = None,
        runes_paths: Sequence[str] | None = None,
        compaction: CompactionSettings = DEFAULT_COMPACTION_SETTINGS,
        environment: MvgeEnvironment | None = None,
    ) -> None:
        self._api_key = api_key
        self._name = name
        self._extension_dir = extension_dir
        self._tome_dir = tome_dir or DEFAULT_TOME_DIR
        self._tome_resume = tome_resume
        self._provider_name = provider_name
        self._compaction_settings = compaction

        if environment is None:
            environment = MvgeEnvironment.resolve(
                name,
                config_dir=Path(f"~/.agents/.mvgeos/{name}").expanduser(),
                allow_unknown_agent=True,
            )

        self._environment = environment
        self._config_manager = environment.config_manager

        parsed = ConfigParsing.resolve(
            environment.config,
            agent_name=name,
            extension_dir=extension_dir,
            runes_paths=runes_paths,
        )
        self._model_id = parsed.model_id
        self._temperature = parsed.temperature
        self._max_tokens = parsed.max_tokens
        self._contemplation_level = parsed.contemplation_level
        self._contemplation_budget = parsed.contemplation_budget
        self._exclude_contemplation = parsed.exclude_contemplation
        self._queue_mode: QueueMode = parsed.queue_mode
        self._spell_names = parsed.spell_names
        self._runes_paths = parsed.runes_paths

        self._provider_registry = RealmRegistry()
        self._model_composer = ModelComposer(self._provider_registry)
        self._runner: RuneRunner | None = None
        self._watchers: list[RuneWatcher] = []
        self._prompt_source = environment.resolved_prompt.source
        self._model: Model | None = None
        self._realm: Realm | None = None
        self._agent_tome: MvgeTome | None = None
        self._tome_ledger: TomeLedger | None = None
        self._loop: MvgeLoop | None = None
        self._harness: MvgeHarness | None = None
        self._compaction: CompactionRunner | None = None
        self._state: MvgeState | None = None
        self._event_bus = EventBus()
        self._abort_controller: AbortController | None = None
        self._initialized = False

    @property
    def tome_id(self) -> str | None:
        if self._tome_ledger is not None:
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

    @property
    def environment(self) -> MvgeEnvironment:
        return self._environment

    @property
    def runner(self) -> RuneRunner | None:
        """Expose the active RuneRunner for runtime introspection (GUI)."""
        return self._runner

    @property
    def diagnostics(self) -> list[Diagnostic | SkillDiagnostic]:
        if self._runner is not None:
            return list(self._runner.diagnostics) + list(self._runner.skill_diagnostics)
        return list(self._environment.diagnostics)

    def build_snapshot(self) -> RuntimeSnapshot:
        """Assemble a resolved runtime snapshot of the agent's surface."""
        spells: list[MvgeSpell | SpellDefinition] = cast(
            list[MvgeSpell | SpellDefinition], self._build_spells()
        )
        env = MvgeEnvironment.resolve(
            self._name,
            config_dir=self.config_dir,
            project_dir=getattr(self._config_manager, "_project_dir", None),
            custom_prompt=getattr(self, "_custom_system_prompt", ""),
            spells=spells,
            runner=self._runner,
            config_manager=self._config_manager,
            has_config_manager=(self._config_manager is not None),
        )
        return env.build_snapshot()

    def on(
        self,
        event_type: MvgeEventType | str,
        callback: Callable[[MvgeEvent], None],
    ) -> Callable[[], None]:
        if isinstance(event_type, str):
            event_type = MvgeEventType(event_type)
        return self._event_bus.on(event_type, callback)

    @property
    def queue_mode(self) -> QueueMode:
        return getattr(self, "_queue_mode", QueueMode.ONE_AT_A_TIME)

    @queue_mode.setter
    def queue_mode(self, mode: QueueMode | str) -> None:
        if isinstance(mode, str):
            mode = QueueMode(mode)
        self._queue_mode = mode

    def steer(self, text: str) -> None:
        if self._state is not None:
            self._state.steer_queue.append(SummonerRequest(role="user", content=text))

    def follow_up(self, text: str) -> None:
        if self._state is not None:
            self._state.followup_queue.append(
                SummonerRequest(role="user", content=text)
            )

    def queue(self, text: str) -> None:
        self.steer(text)

    def _compose_model(self, model_id: str) -> Model:
        model, _ = self._model_composer.compose(
            model_id, self._api_key, self._provider_name
        )
        return model

    def _build_spells(self) -> list[MvgeSpell]:
        """Override in subclass to provide agent-specific spells."""
        return []

    def _build_system_prompt(self) -> str:
        """Override in subclass to provide agent-specific system prompt."""
        return "You are a helpful AI agent."

    def _render_prompt(
        self, body: str, spell_names: list[str], guidelines: list[str]
    ) -> str:
        """Render a prompt with body, spells, guidelines, and environment."""
        from mvgeos_agent.prompt_config import _render_prompt as render_p

        cwd = str(getattr(self._config_manager, "_project_dir", "") or Path.cwd())
        return render_p(body=body, spells=spell_names, guidelines=guidelines, cwd=cwd)

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
            base_prompt = str(
                prompt_data.get("base_prompt", self._build_system_prompt())
            )

            # Inject skill catalog if not suppressed
            if not self._runner.is_skill_catalog_suppressed():
                skill_catalog = self._runner.get_skill_catalog()
                if skill_catalog:
                    base_prompt = f"{base_prompt}\n\n{skill_catalog}"

            return base_prompt
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

        if self._abort_controller is not None:
            self._abort_controller.abort()
        self._abort_controller = AbortController()
        signal = self._abort_controller.signal

        return await self._harness.run(
            stream_fn,
            model=dataclasses.asdict(self._model),
            contemplation_level=self._contemplation_level,
            signal=signal,
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
            signal: AbortSignal | None = None,
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
                signal=signal,
            )

        return stream_fn

    async def initialize(self) -> None:
        if self._initialized:
            return

        await self._load_runes()

        # Initialize tome ledger (needed for both new and resumed sessions)
        self._tome_ledger = TomeLedger(self._tome_dir)

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

        self._model, self._realm = self._model_composer.compose(
            self._model_id, self._api_key, self._provider_name
        )

        if self._tome_resume:
            meta = self._tome_ledger.open_tome(self._tome_resume)
            if meta is None:
                raise TomeResumeError(self._tome_resume)
            self._agent_tome = MvgeTome(self._tome_ledger, meta, self._runner)
            await self._agent_tome.start(reason="resume")

        if self._agent_tome is None:
            meta = self._tome_ledger.create_tome(str(Path.cwd()))
            self._agent_tome = MvgeTome(self._tome_ledger, meta, self._runner)
            await self._agent_tome.start(reason="startup")

        self._state = MvgeState(
            system_prompt=final_prompt,
            prompt_source=self._prompt_source,
            model=dataclasses.asdict(self._model),
            contemplation_level=ContemplationLevel(self._contemplation_level),
            spells=self._build_spells(),
            invocations=[],
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            contemplation_budget=self._contemplation_budget,
            exclude_contemplation=self._exclude_contemplation,
            queue_mode=self._queue_mode,
            rune_runner=self._runner,
            agent_tome=self._agent_tome,
            event_bus=self._event_bus,
        )

        assert self._agent_tome is not None
        self._harness = MvgeHarness(
            state=self._state,
            tome=self._agent_tome,
            realm=self._realm,
            model=self._model,
            compaction_settings=self._compaction_settings,
        )
        self._loop = self._harness.loop
        self._compaction = self._harness.compaction

        self._initialized = True

    async def _load_runes(self) -> None:
        """Load runes from all three levels (global, agent, project)."""
        paths_with_scope = self._build_rune_paths_with_scope()
        loads, diagnostics = load_runes_from_paths(paths_with_scope, self._name)

        if self._runner is None:
            self._runner = RuneRunner()
            self._runner.bind_context(
                RuneContext(
                    cwd=str(Path.cwd()),
                    mode="cli",
                    agent_name=self._name,
                    api_key=self._api_key,
                )
            )

        if loads:
            await self._runner.load_rune_loads(loads, diagnostics)
            for pname, pconfig in self._runner.get_registered_providers().items():
                if isinstance(pconfig, dict):
                    self._provider_registry.register_provider(pname, pconfig)
        elif diagnostics:
            self._runner._diagnostics.extend(diagnostics)

        # Load skills from standard scopes
        skill_paths = get_default_skill_paths(self._name)
        skill_loads, skill_diagnostics = load_skills_from_paths(skill_paths, self._name)
        if skill_loads:
            self._runner.load_skills(skill_loads, diagnostics=skill_diagnostics)
        elif skill_diagnostics:
            self._runner._skill_diagnostics.extend(skill_diagnostics)

        if skill_diagnostics:
            for diag in skill_diagnostics:
                logger.warning(
                    "Skill diagnostic: %s (skill=%s, scope=%s, path=%s)",
                    diag.message,
                    diag.skill_name,
                    diag.scope.value if diag.scope else "unknown",
                    diag.path,
                )

        self._environment = dataclasses.replace(
            self._environment,
            diagnostics=list(self._runner.diagnostics)
            + list(self._runner.skill_diagnostics),
            runner=self._runner,
        )

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
        new_model, new_realm = self._model_composer.compose(
            model_id, self._api_key, self._provider_name
        )
        if new_model.provider != self._model.provider:
            if self._realm is not None:
                await self._realm.close()
            self._realm = new_realm
        self._model = new_model
        assert self._state is not None
        self._state.model = dataclasses.asdict(new_model)
        if self._harness is not None and self._realm is not None:
            self._harness.set_model_and_realm(new_model, self._realm)
            self._compaction = self._harness.compaction

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
        self._state.prompt_source = self._prompt_source

        return await self._run_impl()

    def abort(self) -> None:
        """Abort the currently running invocation.

        Triggers the active AbortController (if any), which signals the loop
        to interrupt in-flight channeling and spell execution. Mirrors Pi's
        ``agent.abort()`` pattern.
        """
        if self._abort_controller is not None:
            self._abort_controller.abort()

    async def close(self) -> None:
        if self._agent_tome is not None:
            await self._agent_tome.shutdown(reason="quit")
        for watcher in self._watchers:
            await watcher.stop()
        self._watchers.clear()
        if self._realm is not None:
            await self._realm.close()
            self._realm = None
        if self._provider_registry is not None:
            await self._provider_registry.close()
        self._initialized = False
        self._runner = None
        self._agent_tome = None
        self._loop = None
        self._harness = None
        self._state = None
        self._abort_controller = None

    async def __aenter__(self) -> BaseMvge:
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
