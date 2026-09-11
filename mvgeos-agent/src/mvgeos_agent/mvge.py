from __future__ import annotations

import copy
import dataclasses
import importlib.util
import inspect
import logging
import os
import re
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any, cast

from dotenv import load_dotenv
from mvgeos_core.abort import (
    AbortController,
    AbortSignal,
)
from mvgeos_core.channel import (
    ChannelConfig,
    Model,
    RealmResponse,
)
from mvgeos_core.constants import (
    DEFAULT_AGENT_NAME,
    DEFAULT_TOME_DIR,
)
from mvgeos_core.errors import MissingApiKeyError, TomeResumeError
from mvgeos_core.event_bus import EventBus
from mvgeos_core.events import (
    ContemplationLevel,
    MvgeEvent,
    MvgeEventType,
    QueueMode,
)
from mvgeos_core.invocations import (
    MvgeInvocation,
    SummonerRequest,
)
from mvgeos_core.loop import StreamFn
from mvgeos_core.spells import MvgeSpell
from mvgeos_provider.base import Realm
from mvgeos_provider.model_registry import ModelRegistry
from mvgeos_provider.registry import RealmRegistry
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
from mvgeos_agent.environment import MvgeEnvironment, resolve_config_dir
from mvgeos_agent.function_spell import (
    RuneSpellWrapper,
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
from mvgeos_agent.rune_lifecycle import RuneLifecycle
from mvgeos_agent.snapshot import RuntimeSnapshot
from mvgeos_agent.types import MvgeState

logger = logging.getLogger(__name__)

SPELL_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")


def _resolve_api_key(explicit_key: str | None = None) -> str:
    return (
        explicit_key
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("MVGEOS_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    )


def _validate_spell_name(name: Any) -> bool:
    """Validate spell name conforms to provider identifier standards."""
    return isinstance(name, str) and bool(SPELL_NAME_REGEX.match(name))


def _validate_spell_parameters(parameters: Any) -> bool:
    """Validate that parameters conform to a JSON Schema object dictionary."""
    if not isinstance(parameters, dict):
        return False
    if not parameters:
        return True

    schema_type = parameters.get("type")
    if schema_type is not None and schema_type != "object":
        return False

    properties = parameters.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            return False
        for prop_name, prop_def in properties.items():
            if not isinstance(prop_name, str) or not isinstance(prop_def, dict):
                return False

    required = parameters.get("required")
    if required is not None:
        if not isinstance(required, (list, tuple, set)):
            return False
        if not all(isinstance(r, str) for r in required):
            return False

    return True


def _validate_spell_signature(spell: Any) -> bool:
    """Validate that spell.execute matches the MvgeSpell execution contract."""
    execute_fn = getattr(spell, "execute", None)
    if not callable(execute_fn):
        return False
    try:
        sig = inspect.signature(execute_fn)
    except (ValueError, TypeError):
        return False

    try:
        sig.bind("dummy_id", {}, signal=None, on_update=None)
        return True
    except TypeError:
        try:
            sig.bind("dummy_id", {}, signal=None)
            return True
        except TypeError:
            return False


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
        caller_dir: Path | None = None,
    ) -> None:
        resolved_caller_dir: Path | None = (
            caller_dir.resolve() if caller_dir is not None else None
        )
        if resolved_caller_dir is None:
            try:
                caller_frame = inspect.stack()[1]
                caller_file = caller_frame.filename
                if caller_file:
                    resolved_caller_dir = Path(caller_file).resolve().parent
            except Exception:
                pass
        if resolved_caller_dir is not None:
            env_path = resolved_caller_dir / ".env"
            if env_path.is_file():
                load_dotenv(env_path)
        caller_dir = resolved_caller_dir

        self._api_key = _resolve_api_key(api_key)
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
        # Discover built-in runes for named agent package
        # (e.g., coding_mvge -> coding_mvge/runes)
        # Ensures GUI/CLI `Mvge(name="coding_mvge")` from any caller_dir still finds
        # `coding-mvge/src/coding_mvge/runes/skill_evolution` (evolution layer)
        # Handles hyphen/underscore mismatch: agent "coding-mvge" vs "coding_mvge"
        if name and name != DEFAULT_AGENT_NAME:
            for try_name in (name, name.replace("-", "_"), name.replace("_", "-")):
                try:
                    spec = importlib.util.find_spec(try_name)
                    if spec is None:
                        continue
                    pkg_path = None
                    if spec.origin and spec.origin not in (None, "namespace"):
                        pkg_path = Path(spec.origin).parent
                    elif spec.submodule_search_locations:
                        for loc in spec.submodule_search_locations:
                            pkg_path = Path(loc)
                            break
                    if pkg_path is not None:
                        candidate = pkg_path / "runes"
                        if candidate.is_dir():
                            cand_str = str(candidate)
                            if cand_str not in resolved_runes_paths:
                                resolved_runes_paths.append(cand_str)
                            break
                except Exception:
                    continue

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
                config_dir=resolve_config_dir(name),
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
        self._harness: MvgeHarness | None = None
        self._compaction: CompactionRunner | None = None
        self._state: MvgeState | None = None
        self._event_bus = EventBus()
        self._abort_controller: AbortController | None = None
        self._enabled_spells_filter: set[str] | None = None
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
    def tome_dir(self) -> Path:
        return self._tome_dir

    @property
    def session_dir(self) -> Path:
        """Alias for tome_dir adhering to .agents protocol boundary."""
        return self._tome_dir

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
        spells = self._build_spells()
        if spells:
            return [s.name for s in spells]
        if self._enabled_spells_filter is not None:
            return list(self._spell_names or self._enabled_spells_filter)
        return []

    @property
    def available_spells(self) -> list[str]:
        """List of all available spell names (builtin + rune-registered)."""
        names: list[str] = [coerce_spell(s).name for s in self._spells]
        if self._runner is not None:
            names.extend([s.name for s in self._runner.get_all_registered_spells()])
        return list(dict.fromkeys(names))

    def set_enabled_spells(self, spell_names: Sequence[str]) -> None:
        """Filter which spells are enabled for execution."""
        self._enabled_spells_filter = set(spell_names)
        self._spell_names = list(spell_names)
        if self._state is not None:
            self._state.spells = self._build_spells()

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
    def model_registry(self) -> ModelRegistry:
        """Active model registry bound to the agent's realm registry."""
        return self._provider_registry.model_registry

    @property
    def name(self) -> str:
        return self._name

    @property
    def config_dir(self) -> Path:
        if self._config_manager is not None and getattr(
            self._config_manager, "agent_config_path", None
        ):
            return self._config_manager.agent_config_path.parent
        return resolve_config_dir(self._name)

    @property
    def environment(self) -> MvgeEnvironment:
        return self._environment

    @property
    def spells(self) -> list[SpellUnion]:
        return list(self._spells)

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

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
        if runner is not None:
            runner.on_event(
                "mvge_event", lambda ev: self._event_bus.emit(ev.type, ev.data)
            )
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
        if self._runner is not None:
            self._runner.on_event(
                "mvge_event", lambda ev: self._event_bus.emit(ev.type, ev.data)
            )
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

    def abort(self) -> None:
        if self._abort_controller is not None:
            self._abort_controller.abort()

    def _build_spells(self) -> list[MvgeSpell]:
        """Convert injected callables and rune spells to executable MvgeSpells."""
        spells: list[MvgeSpell] = []
        for s in self._spells:
            spell = coerce_spell(s)
            if not _validate_spell_name(spell.name):
                logger.warning(
                    "Spell '%s' has an invalid name (must match ^[a-zA-Z0-9_-]+$) "
                    "and will be skipped.",
                    spell.name,
                )
                continue
            spells.append(spell)

        seen_names: set[str] = {s.name for s in spells}

        if self._runner is not None:
            active = set(self._runner.get_active_spells())
            for rs in self._runner.get_all_registered_spells():
                if rs.name not in active:
                    continue

                if not _validate_spell_name(rs.name):
                    logger.warning(
                        "Rune spell '%s' has an invalid name "
                        "(must match ^[a-zA-Z0-9_-]+$) and will be skipped.",
                        rs.name,
                    )
                    continue

                if not _validate_spell_parameters(getattr(rs, "parameters", None)):
                    logger.warning(
                        "Rune spell '%s' has an invalid parameter schema "
                        "and will be skipped.",
                        rs.name,
                    )
                    continue

                if not _validate_spell_signature(rs):
                    logger.warning(
                        "Rune spell '%s' execution signature does not conform "
                        "to the execution contract and will be skipped.",
                        rs.name,
                    )
                    continue

                spell_to_add: MvgeSpell = RuneSpellWrapper(rs)
                spell_name = rs.name
                if spell_name in seen_names:
                    source_rune = getattr(rs, "source_rune", None) or "rune"
                    prefixed_name = f"{source_rune}_{spell_name}"
                    logger.warning(
                        "Rune spell '%s' collides with existing spell; "
                        "renaming to '%s'.",
                        spell_name,
                        prefixed_name,
                    )
                    if not _validate_spell_name(prefixed_name):
                        logger.warning(
                            "Prefixed rune spell '%s' has an invalid name "
                            "and will be skipped.",
                            prefixed_name,
                        )
                        continue
                    if prefixed_name in seen_names:
                        logger.warning(
                            "Prefixed rune spell '%s' still collides with an "
                            "existing spell and will be skipped.",
                            prefixed_name,
                        )
                        continue
                    spell_to_add = copy.copy(spell_to_add)
                    spell_to_add.name = prefixed_name
                    spell_name = prefixed_name

                seen_names.add(spell_name)
                spells.append(spell_to_add)

        if self._enabled_spells_filter is not None:
            spells = [s for s in spells if s.name in self._enabled_spells_filter]

        return spells

    def _build_system_prompt(self) -> str:
        """Build the agent system prompt string."""
        return self._environment.resolved_prompt.text

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
        spells = [
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
                    spells=spells,
                    system_prompt=state.system_prompt,
                ),
                signal=signal,
            )

        return stream_fn

    async def initialize(self) -> None:
        """Wire lifecycle modules into a running agent."""
        if self._initialized:
            return

        if not self._api_key:
            self._api_key = _resolve_api_key()
        is_ollama = bool(
            (self._model_id and self._model_id.startswith("ollama"))
            or self._provider_name == "ollama"
        )
        if not self._api_key and not is_ollama:
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

        self._rebind_runner_context()

        if (
            self._agent_tome is not None
            and self._agent_tome.compatibility_report is not None
        ):
            self._resume_diagnostics = list(
                self._agent_tome.compatibility_report.diagnostics
            )

        self._wire_runtime(final_prompt)
        self._initialized = True

    def _rebind_runner_context(self) -> None:
        """Synchronize active session/tome context into the bound RuneRunner."""
        if self._runner is not None and self._agent_tome is not None:
            new_ctx = dataclasses.replace(
                self._runner.context,
                session_id=self._agent_tome.tome_id,
                tome_dir=str(self._tome_dir),
                model_id=self._model_id,
            )
            self._runner.bind_context(new_ctx)

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
            compaction_settings=self._compaction_settings,
        )
        self._compaction = self._harness.compaction

    async def run(self, prompt: str) -> MvgeInvocation:
        """Template method for processing a turn."""
        await self.initialize()
        assert self._state is not None

        user_msg = SummonerRequest(role="user", content=prompt)
        self._state.invocations.append(user_msg)

        if not self._state.system_prompt:
            final_prompt = await self._build_system_prompt_async()
            self._state.system_prompt = final_prompt

        return await self._run_impl()

    async def switch_model(self, model_id: str) -> None:
        """Switch the model in-flight."""
        if self._model is not None and self._model.id == model_id:
            return

        self._model_id = model_id
        if self._initialized:
            new_model, new_realm = self._provider_registry.resolve(
                model_id, self._api_key, self._provider_name
            )
            self._model = new_model
            self._realm = new_realm
            if self._state is not None:
                self._state.model = dataclasses.asdict(new_model)
            if self._harness is not None:
                self._harness.set_model_and_realm(new_model, new_realm)
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

    async def reset_session(self, *, resume_tome_id: str | None = None) -> None:
        """Reset or resume session lifecycle."""
        await self.close()
        self._tome_resume = resume_tome_id
        self._state = None
        self._agent_tome = None
        self._harness = None
        self._initialized = False
        await self.initialize()

    async def fork_tome(self, entry_id: str | None = None) -> str:
        """Branch current Tome from entry_id (or active leaf) and
        switch to the new Tome.
        """
        if not self._initialized or self._agent_tome is None:
            raise RuntimeError("Agent not initialized")
        new_tome = await self._agent_tome.fork(entry_id)
        if new_tome is None:
            raise RuntimeError("Failed to fork tome")
        self._agent_tome = new_tome
        self._tome_resume = new_tome.tome_id
        if self._harness is not None:
            self._harness.switch_tome(new_tome)
            self._compaction = self._harness.compaction
        if self._state is not None:
            self._state.invocations = self._agent_tome.reconstruct_invocations()
        self._rebind_runner_context()
        return new_tome.tome_id

    async def checkout_leaf(self, leaf_id: str) -> None:
        """Switch active position in the Tome to a specific leaf entry."""
        if (
            not self._initialized
            or self._agent_tome is None
            or self._tome_ledger is None
        ):
            raise RuntimeError("Agent not initialized")
        if self._state is not None and getattr(self._state, "is_streaming", False):
            raise RuntimeError("Cannot checkout leaf while invocation is streaming")
        self._tome_ledger.append_leaf(self._agent_tome.tome_id, leaf_id)
        if self._state is not None:
            self._state.invocations = self._agent_tome.reconstruct_invocations()

    async def list_leaves(self) -> list[str]:
        """List all active leaf entry IDs in the current Tome."""
        if (
            not self._initialized
            or self._agent_tome is None
            or self._tome_ledger is None
        ):
            return []
        return self._tome_ledger.list_leaves(self._agent_tome.tome_id)

    async def undo(self) -> str | None:
        """Revert the most recent summoner invocation by pointing active
        leaf to its parent.
        """
        if (
            not self._initialized
            or self._agent_tome is None
            or self._tome_ledger is None
        ):
            raise RuntimeError("Agent not initialized")
        if self._state is not None and getattr(self._state, "is_streaming", False):
            raise RuntimeError("Cannot undo while invocation is streaming")
        target = self._tome_ledger.get_parent_summoner_entry(
            self._agent_tome.tome_id, self._agent_tome.active_leaf_id
        )
        if target is None:
            raise ValueError("Cannot undo: at root invocation")
        self._tome_ledger.append_leaf(self._agent_tome.tome_id, target.id)
        if self._state is not None:
            self._state.invocations = self._agent_tome.reconstruct_invocations()
        return target.id

    async def compact(self) -> str:
        """Trigger mana pool compaction on the current Tome branch."""
        compaction = self._compaction or (
            self._harness.compaction if self._harness is not None else None
        )
        if (
            not self._initialized
            or self._agent_tome is None
            or compaction is None
            or self._state is None
        ):
            raise RuntimeError("Agent not initialized")
        if getattr(self._state, "is_streaming", False):
            raise RuntimeError("Cannot compact while invocation is streaming")
        if not self._state.invocations:
            return "No invocations to compact"
        replacement = await compaction.force_compact(self._state.invocations)
        if replacement is not None:
            self._state.invocations = replacement
            return "Compaction completed"
        return "Nothing to compact or compaction skipped"

    def get_skills_catalog(self) -> list[dict[str, str]]:
        """List registered skills with metadata."""
        if self._runner is None:
            return []
        skills = self._runner.get_skills()
        return [
            {
                "name": s.name,
                "description": s.description,
                "scope": s.scope.value if s.scope else "unknown",
                "path": str(s.path),
            }
            for s in skills
        ]

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
