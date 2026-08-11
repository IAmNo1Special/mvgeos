from __future__ import annotations

import dataclasses
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any, cast

from mvgeos_provider.base import Realm
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
    RuneManifest,
    RuneScope,
    RuneShortcut,
    SigilHook,
    SkillDiagnostic,
    SkillManifest,
    SpellDefinition,
)
from mvgeos_runes.watcher import RuneWatcher
from mvgeos_tome.ledger import TomeLedger

from mvgeos_agent.agent_session import MvgeTome
from mvgeos_agent.config_manager import ConfigLayer, ConfigManager, ConfigValue
from mvgeos_agent.constants import (
    DEFAULT_AGENT_NAME,
    DEFAULT_MODEL,
    DEFAULT_TOME_DIR,
    resolve_rune_paths,
)
from mvgeos_agent.event_bus import EventBus
from mvgeos_agent.harness import (
    DEFAULT_COMPACTION_SETTINGS,
    CompactionRunner,
    CompactionSettings,
    MvgeHarness,
)
from mvgeos_agent.loop import MvgeLoop, StreamFn
from mvgeos_agent.prompt_config import DEFAULT_GUIDELINES, DEFAULT_SYSTEM_PROMPT
from mvgeos_agent.prompt_loader import PromptLoader, PromptSource
from mvgeos_agent.snapshot import RuntimeSnapshot, assemble_snapshot
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
        model: str | None = None,
        extension_dir: str | None = None,
        session_dir: Path | None = None,
        session_resume: str | None = None,
        provider_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        contemplation_level: str | None = None,
        contemplation_budget: int | None = None,
        exclude_contemplation: bool | None = None,
        runes_paths: Sequence[str] | None = None,
        compaction: CompactionSettings = DEFAULT_COMPACTION_SETTINGS,
        config_manager: ConfigManager | None = None,
    ) -> None:
        self._api_key = api_key
        self._name = name
        self._extension_dir = extension_dir
        self._session_dir = session_dir or DEFAULT_TOME_DIR
        self._session_resume = session_resume
        self._provider_name = provider_name
        self._compaction_settings = compaction

        self._config_manager: ConfigManager | None = None

        # Use ConfigManager to resolve defaults if provided
        if config_manager is not None:
            self._config_manager = config_manager
            resolved = config_manager.load()

            def _get(
                key: str, default: Any, layer: ConfigLayer = ConfigLayer.DEFAULTS
            ) -> Any:
                return resolved.get(key, ConfigValue(default, layer)).value

            self._model_id = model or _get("model", DEFAULT_MODEL)
            self._temperature = (
                temperature if temperature is not None else _get("temperature", 0.7)
            )
            self._max_tokens = (
                max_tokens if max_tokens is not None else _get("max_tokens", 4096)
            )
            self._contemplation_level = contemplation_level or _get(
                "contemplation_level", "medium"
            )
            self._contemplation_budget = (
                contemplation_budget
                if contemplation_budget is not None
                else _get("contemplation_budget", None)
            )
            self._exclude_contemplation = (
                exclude_contemplation
                if exclude_contemplation is not None
                else _get("exclude_contemplation", False)
            )
            spells_enabled = _get("spells_enabled", [])
            self._spell_names = list(spells_enabled) if spells_enabled else None
            # Rune paths from config if not explicitly provided
            if runes_paths is not None:
                self._runes_paths = [Path(str(p)).expanduser() for p in runes_paths]
            else:
                rune_paths_config = _get("rune_paths", None)
                if rune_paths_config:
                    self._runes_paths = [
                        Path(str(p)).expanduser() for p in rune_paths_config
                    ]
                else:
                    self._runes_paths = resolve_rune_paths(name, extension_dir)
        else:
            # Backward compatibility: use explicit params or hardcoded defaults
            self._model_id = model if model is not None else DEFAULT_MODEL
            self._temperature = temperature if temperature is not None else 0.7
            self._max_tokens = max_tokens if max_tokens is not None else 4096
            self._contemplation_level = (
                contemplation_level if contemplation_level is not None else "medium"
            )
            self._contemplation_budget = contemplation_budget
            self._exclude_contemplation = (
                exclude_contemplation if exclude_contemplation is not None else False
            )
            self._spell_names = None
            if runes_paths is not None:
                self._runes_paths = [Path(str(p)).expanduser() for p in runes_paths]
            else:
                self._runes_paths = resolve_rune_paths(name, extension_dir)

        self._provider_registry = RealmRegistry()
        self._runner: RuneRunner | None = None
        self._watchers: list[RuneWatcher] = []
        self._prompt_source = PromptSource.BUILTIN
        self._model: Model | None = None
        self._realm: Realm | None = None
        self._agent_session: MvgeTome | None = None
        self._tome_ledger: TomeLedger | None = None
        self._loop: MvgeLoop | None = None
        self._harness: MvgeHarness | None = None
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

    def build_snapshot(self) -> RuntimeSnapshot:
        """Assemble a resolved runtime snapshot of the agent's surface.

        Pulls spells (with rune-vs-builtin provenance), runes per scope,
        config values with provenance layers, resolved prompt source,
        loaded skills with source, and accumulated diagnostics into a single
        serializable ``RuntimeSnapshot``.

        Works both before and after ``initialize()`` — absent components
        contribute empty collections.
        """
        spells: list[MvgeSpell | SpellDefinition] = cast(
            list[MvgeSpell | SpellDefinition], self._build_spells()
        )

        rune_manifests: list[RuneManifest] = (
            self._runner.loaded_manifests if self._runner is not None else []
        )
        skills: list[SkillManifest] = (
            self._runner.get_skills() if self._runner is not None else []
        )
        rune_diagnostics: list[Diagnostic] = (
            self._runner.diagnostics if self._runner is not None else []
        )
        skill_diagnostics: list[SkillDiagnostic] = (
            self._runner.skill_diagnostics if self._runner is not None else []
        )

        config_values: dict[str, ConfigValue] = (
            self._config_manager.load() if self._config_manager is not None else {}
        )
        config_source_files: dict[ConfigLayer, Path | None] = {}
        if self._config_manager is not None:
            config_source_files = {
                ConfigLayer.AGENT: self._config_manager.agent_config_path,
                ConfigLayer.LEGACY: self._config_manager.legacy_config_path,
            }

        loader = PromptLoader(agent_name=self._name, config_dir=self.config_dir)
        custom_prompt = getattr(self, "_custom_system_prompt", "")
        resolved_prompt = loader.resolve_system_prompt(
            custom=custom_prompt, default=DEFAULT_SYSTEM_PROMPT
        )
        resolved_guidelines = loader.resolve_guidelines(default=DEFAULT_GUIDELINES)

        return assemble_snapshot(
            agent_name=self._name,
            model=self._model_id,
            spells=spells,
            rune_manifests=rune_manifests,
            config_values=config_values,
            config_source_files=config_source_files,
            resolved_prompt=resolved_prompt,
            resolved_guidelines=resolved_guidelines,
            skills=skills,
            rune_diagnostics=rune_diagnostics,
            skill_diagnostics=skill_diagnostics,
        )

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

    def _render_prompt(
        self, body: str, spell_names: list[str], guidelines: list[str]
    ) -> str:
        """Render a prompt with body, spells, and guidelines."""
        parts = [body]
        if spell_names:
            spell_list = "\n".join(f"  - {s}" for s in spell_names)
        else:
            spell_list = "  (none)"
        parts.append(f"\nActive spells:\n{spell_list}")
        if guidelines:
            parts.append("\nGuidelines:")
            parts.extend(f"- {g}" for g in guidelines)
        parts.append(f"\nCurrent working directory: {Path.cwd()}")
        return "\n".join(parts)

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
            prompt_source=self._prompt_source,
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

        assert self._agent_session is not None
        self._harness = MvgeHarness(
            state=self._state,
            tome=self._agent_session,
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

        # Load skills from standard scopes
        skill_paths = get_default_skill_paths(self._name)
        skill_loads, skill_diagnostics = load_skills_from_paths(skill_paths, self._name)
        if skill_loads:
            self._runner.load_skills(skill_loads, diagnostics=skill_diagnostics)
        if skill_diagnostics:
            for diag in skill_diagnostics:
                logger.warning(
                    "Skill diagnostic: %s (skill=%s, scope=%s, path=%s)",
                    diag.message,
                    diag.skill_name,
                    diag.scope.value if diag.scope else "unknown",
                    diag.path,
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
