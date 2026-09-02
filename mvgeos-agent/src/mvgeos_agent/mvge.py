from __future__ import annotations

import dataclasses
import inspect
import logging
import os
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any, cast

from dotenv import load_dotenv
from mvgeos_provider.base import Realm
from mvgeos_provider.registry import RealmRegistry
from mvgeos_provider.types import ChannelConfig, Model, RealmResponse
from mvgeos_runes.rune_runner import RuneRunner
from mvgeos_runes.types import (
    Diagnostic,
    RuneShortcut,
    SkillDiagnostic,
    SpellDefinition,
)
from mvgeos_tome.ledger import TomeLedger
from mvgeos_tome.types import TomeMetadata

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.compatibility import (
    SessionCompatibilityReport,
    validate_session_compatibility,
)
from mvgeos_agent.constants import (
    DEFAULT_AGENT_NAME,
    DEFAULT_TOME_DIR,
)
from mvgeos_agent.core_loop import StreamFn
from mvgeos_agent.environment import MvgeEnvironment
from mvgeos_agent.errors import MissingApiKeyError
from mvgeos_agent.event_bus import EventBus
from mvgeos_agent.function_spell import (
    SpellUnion,
    coerce_spell,
    discover_spells_from_dir,
)
from mvgeos_agent.harness import (
    DEFAULT_COMPACTION_SETTINGS,
    CompactionRunner,
    CompactionSettings,
    MvgeHarness,
)
from mvgeos_agent.mvge_loop import MvgeLoop
from mvgeos_agent.rune_lifecycle import RuneLifecycle
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


class Mvge:
    """Core concrete agent implementation in MvgeOS.

    Configured with tools (spells), prompt, model, environment, and persistence.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        name: str = DEFAULT_AGENT_NAME,
        spells: Sequence[SpellUnion] | None = None,
        custom_system_prompt: str = "",
        extension_dir: str | None = None,
        tome_dir: Path | None = None,
        tome_resume: str | None = None,
        provider_name: str | None = None,
        runes_paths: Sequence[str] | None = None,
        compaction: CompactionSettings = DEFAULT_COMPACTION_SETTINGS,
        environment: MvgeEnvironment | None = None,
        strict_resume: bool = False,
        force_fork_resume: bool = False,
    ) -> None:
        caller_dir: Path | None = None
        try:
            caller_frame = inspect.stack()[1]
            caller_file = caller_frame.filename
            if caller_file:
                caller_dir = Path(caller_file).resolve().parent
                env_path = caller_dir / ".env"
                if env_path.is_file():
                    load_dotenv(env_path)
        except Exception:
            pass

        self._api_key = (
            api_key
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("MVGEOS_API_KEY")
            or ""
        )
        self._name = name
        self._caller_dir = caller_dir

        if spells is not None:
            self._spells: list[SpellUnion] = list(spells)
        elif caller_dir is not None and (caller_dir / "spells").is_dir():
            self._spells = list(discover_spells_from_dir(caller_dir / "spells"))
        else:
            self._spells = []

        resolved_runes_paths = list(runes_paths) if runes_paths is not None else []
        if caller_dir is not None and (caller_dir / "runes").is_dir():
            colocated_runes = str(caller_dir / "runes")
            if colocated_runes not in resolved_runes_paths:
                resolved_runes_paths.append(colocated_runes)

        self._custom_system_prompt = custom_system_prompt
        self._extension_dir = extension_dir
        self._tome_dir = tome_dir or DEFAULT_TOME_DIR
        self._tome_resume = tome_resume
        self._provider_name = provider_name
        self._compaction_settings = compaction
        self._strict_resume = strict_resume
        self._force_fork_resume = force_fork_resume
        self._resume_diagnostics: list[Diagnostic | SkillDiagnostic] = []

        if environment is None:
            environment = MvgeEnvironment.resolve(
                name,
                config_dir=Path(f"~/.agents/.mvgeos/{name}").expanduser(),
                caller_dir=caller_dir,
                extension_dir=extension_dir,
                runes_paths=resolved_runes_paths if resolved_runes_paths else None,
            )

        self._environment = environment
        self._config_manager = environment.config_manager

        self._model_id = environment.model_id
        self._temperature = environment.temperature
        self._max_tokens = environment.max_tokens
        self._contemplation_level = environment.contemplation_level
        self._contemplation_budget = environment.contemplation_budget
        self._exclude_contemplation = environment.exclude_contemplation
        self._queue_mode: QueueMode = environment.queue_mode
        self._spell_names = environment.spell_names
        self._runes_paths = (
            list(resolved_runes_paths)
            if resolved_runes_paths
            else list(environment.runes_paths)
        )

        self._provider_registry = RealmRegistry()
        self._runner: RuneRunner | None = None
        self._rune_lifecycle: RuneLifecycle | None = None
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
    def session_id(self) -> str | None:
        """Alias for tome_id adhering to standard agent protocol vocabulary."""
        return self.tome_id

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def contemplation_level(self) -> ContemplationLevel | str:
        return self._contemplation_level

    @property
    def mana_used(self) -> int | None:
        if self._state is not None:
            return getattr(self._state, "mana_used", None)
        return None

    @property
    def enabled_spells(self) -> list[str]:
        return [s.name for s in self._build_spells()]

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
    def name(self) -> str:
        return self._name

    @property
    def config_dir(self) -> Path:
        if self._config_manager is not None and getattr(
            self._config_manager, "agent_config_path", None
        ):
            return self._config_manager.agent_config_path.parent
        return Path(f"~/.agents/.mvgeos/{self._name}").expanduser()

    @property
    def environment(self) -> MvgeEnvironment:
        return self._environment

    @property
    def diagnostics(self) -> list[Diagnostic | SkillDiagnostic]:
        diags: list[Diagnostic | SkillDiagnostic] = list(self._resume_diagnostics)
        if self._environment is not None and self._environment.diagnostics:
            for d in self._environment.diagnostics:
                if d not in diags:
                    diags.append(d)
        return diags

    def set_environment(self, environment: MvgeEnvironment) -> None:
        """Replace the environment and update config_manager reference."""
        self._environment = environment
        self._config_manager = environment.config_manager

    def set_config_manager(self, config_manager: Any) -> None:
        """Replace the config manager on both agent and environment."""
        self._config_manager = config_manager
        if self._environment is not None:
            self._environment = dataclasses.replace(
                self._environment, config_manager=config_manager
            )

    def set_runner(self, runner: RuneRunner | None) -> None:
        """Inject an explicit RuneRunner."""
        self._runner = runner
        if self._rune_lifecycle is not None:
            self._rune_lifecycle._runner = runner

    async def load_runes(self) -> None:
        """Explicitly initialize runes and skills."""
        await self._load_runes()

    async def _load_runes(self) -> None:
        """Initialize the RuneLifecycle collaborator."""
        if self._rune_lifecycle is None:
            self._rune_lifecycle = RuneLifecycle(
                agent_name=self._name,
                api_key=self._api_key,
                runes_paths=self._runes_paths,
                environment=self._environment,
                provider_registry=self._provider_registry,
                runner=self._runner,
            )
        await self._rune_lifecycle.load()
        await self._rune_lifecycle.start()
        self._runner = self._rune_lifecycle.runner
        if self._rune_lifecycle.environment is not None:
            self._environment = self._rune_lifecycle.environment
        if self._environment.diagnostics:
            self._resume_diagnostics = list(self._environment.diagnostics)

    def validate_tome_compatibility(
        self,
        tome_id_or_meta: str | TomeMetadata,
    ) -> SessionCompatibilityReport:
        """Inspect compatibility of a target tome against active configuration."""
        if self._tome_ledger is None:
            self._tome_ledger = TomeLedger(self._tome_dir)

        if isinstance(tome_id_or_meta, TomeMetadata):
            meta = tome_id_or_meta
        else:
            loaded_meta = self._tome_ledger.open_tome(tome_id_or_meta)
            if loaded_meta is None:
                raise TomeResumeError(tome_id_or_meta)
            meta = loaded_meta

        active_spells = [s.name for s in self._build_spells()]
        if self._runner is not None:
            active_spells.extend(
                [s.name for s in self._runner.get_all_registered_spells()]
            )
        active_spells = list(dict.fromkeys(active_spells))

        if self._model is not None:
            model_id = self._model.id
        elif self._model_id:
            try:
                resolved_model, _ = self._provider_registry.resolve(
                    self._model_id, self._api_key, self._provider_name
                )
                model_id = resolved_model.id
            except Exception:
                model_id = self._model_id
        else:
            model_id = None

        entries = self._tome_ledger.get_entries(meta.id)
        return validate_session_compatibility(
            meta,
            expected_model=model_id,
            expected_contemplation=str(self._contemplation_level),
            expected_spells=active_spells,
            entries=entries,
        )

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
        return self._queue_mode

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

    def abort(self) -> None:
        if self._abort_controller is not None:
            self._abort_controller.abort()

    def _compose_model(self, model_id: str) -> Model:
        model, _ = self._provider_registry.resolve(
            model_id, self._api_key, self._provider_name
        )
        return model

    def _build_spells(self) -> list[MvgeSpell]:
        """Convert injected callables and rune spells to executable MvgeSpells."""
        spells: list[MvgeSpell] = [coerce_spell(s) for s in self._spells]
        if self._runner is not None:
            active = set(self._runner.get_active_spells())
            for rs in self._runner.get_all_registered_spells():
                if rs.name in active:
                    spells.append(cast(MvgeSpell, rs))
        return spells

    def _build_system_prompt(self) -> str:
        """Build the agent system prompt string."""
        return self._environment.resolved_prompt.text

    def _render_prompt(
        self, body: str, spell_names: list[str], guidelines: list[str]
    ) -> str:
        """Render a prompt with body, spells, guidelines, and environment."""
        cwd = str(getattr(self._config_manager, "_project_dir", "") or Path.cwd())
        active_names = (
            spell_names if spell_names else [s.name for s in self._build_spells()]
        )
        spells_dir = (
            (self._caller_dir / "spells")
            if self._caller_dir and (self._caller_dir / "spells").is_dir()
            else None
        )
        skills_paths: list[Path] = []
        if self._caller_dir and (self._caller_dir / "skills").is_dir():
            skills_paths.append(self._caller_dir / "skills")
        return self._environment.render_prompt(
            body,
            active_names,
            guidelines,
            cwd=cwd,
            spells_dir=spells_dir,
            skills_paths=skills_paths,
            runes_paths=self._environment.runes_paths,
            system_path=self._environment.resolved_prompt.path,
            guidelines_path=self._environment.resolved_guidelines.path,
        )

    async def _build_system_prompt_async(self) -> str:
        """Async version that supports rune prompt injection via sigil hooks."""
        active_names = [s.name for s in self._build_spells()]
        return await self._environment.assemble_system_prompt(
            runner=self._runner,
            base_prompt=self._build_system_prompt(),
            custom_prompt=getattr(self, "_custom_system_prompt", ""),
            cwd=Path.cwd(),
            spell_names=active_names,
            config_dir=self.config_dir,
        )

    async def _run_impl(self) -> MvgeInvocation:
        """Turn-processing logic using the harness."""
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
        """Wire lifecycle modules into a running agent."""
        if self._initialized:
            return

        if not self._api_key:
            self._api_key = (
                os.environ.get("OPENROUTER_API_KEY")
                or os.environ.get("MVGEOS_API_KEY")
                or ""
            )
        if not self._api_key:
            raise MissingApiKeyError

        await self._load_runes()

        self._tome_ledger = TomeLedger(self._tome_dir)
        final_prompt = await self._build_system_prompt_async()
        self._model, self._realm = self._provider_registry.resolve(
            self._model_id, self._api_key, self._provider_name
        )
        active_spells = [s.name for s in self._build_spells()]
        if self._runner is not None:
            active_spells.extend(
                [s.name for s in self._runner.get_all_registered_spells()]
            )
        active_spells = list(dict.fromkeys(active_spells))

        model_id = self._model.id if self._model is not None else self._model_id
        self._agent_tome = await MvgeTome.open_or_create(
            self._tome_ledger,
            self._tome_resume,
            runner=self._runner,
            model=model_id,
            contemplation_level=str(self._contemplation_level),
            spells=active_spells,
            strict=self._strict_resume,
            force_fork=self._force_fork_resume,
        )

        if (
            self._agent_tome is not None
            and self._agent_tome.compatibility_report is not None
        ):
            self._resume_diagnostics = list(
                self._agent_tome.compatibility_report.diagnostics
            )

        self._wire_runtime(final_prompt)
        self._initialized = True

    def _wire_runtime(self, final_prompt: str) -> None:
        """Construct MvgeState and MvgeHarness from the wired collaborators."""
        assert self._model is not None
        assert self._realm is not None
        assert self._agent_tome is not None

        initial_invocations: list[MvgeInvocation] = []
        if self._tome_resume:
            initial_invocations = self._agent_tome.reconstruct_invocations()

        self._state = MvgeState(
            system_prompt=final_prompt,
            prompt_source=self._prompt_source,
            model=dataclasses.asdict(self._model),
            contemplation_level=ContemplationLevel(self._contemplation_level),
            spells=self._build_spells(),
            invocations=initial_invocations,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            contemplation_budget=self._contemplation_budget,
            exclude_contemplation=self._exclude_contemplation,
            queue_mode=self._queue_mode,
            rune_runner=self._runner,
            agent_tome=self._agent_tome,
            event_bus=self._event_bus,
        )

        self._harness = MvgeHarness(
            state=self._state,
            tome=self._agent_tome,
            realm=self._realm,
            model=self._model,
            compaction=self._compaction,
        )
        self._loop = self._harness.loop

    async def run(self, prompt: str) -> MvgeInvocation:
        """Template method for processing a turn."""
        await self.initialize()
        assert self._state is not None

        user_msg = SummonerRequest(role="user", content=prompt)
        self._state.invocations.append(user_msg)

        final_prompt = await self._build_system_prompt_async()
        self._state.system_prompt = final_prompt

        return await self._run_impl()

    async def switch_model(self, model_id: str) -> None:
        """Switch the model in-flight."""
        if self._model is not None and self._model.id == model_id:
            return

        self._model_id = model_id
        if self._initialized:
            new_model = self._compose_model(model_id)
            self._model = new_model
            if self._state is not None:
                self._state.model = dataclasses.asdict(new_model)
            if self._agent_tome is not None:
                await self._agent_tome.record_custom_async(
                    "model_switch", {"model": new_model.id}
                )

    async def set_contemplation_level(self, level: ContemplationLevel | str) -> None:
        """Switch the contemplation level in-flight."""
        if isinstance(level, str):
            level = ContemplationLevel(level)
        if self._contemplation_level == level:
            return

        self._contemplation_level = level
        if self._state is not None:
            self._state.contemplation_level = level
        if self._agent_tome is not None:
            await self._agent_tome.record_custom_async(
                "contemplation_switch", {"level": level.value}
            )

    async def close(self) -> None:
        """Teardown the agent session and release resources."""
        if self._abort_controller is not None:
            self._abort_controller.abort()

        if self._rune_lifecycle is not None:
            await self._rune_lifecycle.shutdown()
            self._rune_lifecycle = None
            self._runner = None

        if self._realm is not None:
            await self._realm.close()
            self._realm = None

        if self._agent_tome is not None:
            await self._agent_tome.shutdown()

        self._initialized = False

    async def __aenter__(self) -> Mvge:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()
