"""Unit tests for autocomplete logic in mvgeos-gui input dock."""

from __future__ import annotations

import tempfile
from pathlib import Path

from mvgeos_runes.types import SkillManifest, SkillScope

from mvgeos_gui.autocomplete import (
    AutocompleteMode,
    AutocompleteService,
    CommandKind,
    MentionIndex,
    MentionItem,
    MentionKind,
    SlashCommandItem,
    SlashCommandRegistry,
    detect_trigger,
    fuzzy_filter,
    get_last_word,
)

# ---------------------------------------------------------------------------
# Fuzzy filter
# ---------------------------------------------------------------------------


def test_fuzzy_filter_empty_query_returns_all() -> None:
    items = [
        MentionItem(MentionKind.FILE, "a.py", "a.py"),
        MentionItem(MentionKind.FILE, "b.py", "b.py"),
    ]
    assert fuzzy_filter(items, "") == items


def test_fuzzy_filter_exact_match() -> None:
    items = [
        MentionItem(MentionKind.FILE, "main.py", "main.py"),
        MentionItem(MentionKind.FILE, "utils.py", "utils.py"),
    ]
    result = fuzzy_filter(items, "main")
    assert len(result) == 1
    assert result[0].label == "main.py"


def test_fuzzy_filter_subsequence_match() -> None:
    items = [
        MentionItem(MentionKind.FILE, "src/app.py", "src/app.py"),
        MentionItem(MentionKind.FILE, "test.py", "test.py"),
    ]
    result = fuzzy_filter(items, "sap")
    assert len(result) == 1
    assert result[0].label == "src/app.py"


def test_fuzzy_filter_no_match() -> None:
    items = [
        MentionItem(MentionKind.FILE, "main.py", "main.py"),
    ]
    assert fuzzy_filter(items, "zzz") == []


def test_fuzzy_filter_case_insensitive() -> None:
    items = [
        MentionItem(MentionKind.FILE, "Main.PY", "Main.PY"),
    ]
    result = fuzzy_filter(items, "main")
    assert len(result) == 1


def test_fuzzy_filter_prefix_matches_first() -> None:
    items = [
        MentionItem(MentionKind.FILE, "abc.py", "abc.py"),
        MentionItem(MentionKind.FILE, "xabc.py", "xabc.py"),
    ]
    result = fuzzy_filter(items, "abc")
    assert result[0].label == "abc.py"
    assert result[1].label == "xabc.py"


# ---------------------------------------------------------------------------
# Trigger detection
# ---------------------------------------------------------------------------


def test_detect_trigger_mention_at_start() -> None:
    result = detect_trigger("@main")
    assert result is not None
    mode, query = result
    assert mode == AutocompleteMode.MENTION
    assert query == "main"


def test_detect_trigger_mention_after_space() -> None:
    result = detect_trigger("hello @main")
    assert result is not None
    assert result[0] == AutocompleteMode.MENTION
    assert result[1] == "main"


def test_detect_trigger_command() -> None:
    result = detect_trigger("/help")
    assert result is not None
    assert result[0] == AutocompleteMode.COMMAND
    assert result[1] == "help"


def test_detect_trigger_mention_empty_query() -> None:
    result = detect_trigger("hello @")
    assert result is not None
    assert result[0] == AutocompleteMode.MENTION
    assert result[1] == ""


def test_detect_trigger_command_empty_query() -> None:
    result = detect_trigger("/")
    assert result is not None
    assert result[0] == AutocompleteMode.COMMAND
    assert result[1] == ""


def test_detect_trigger_no_trigger() -> None:
    assert detect_trigger("hello world") is None


def test_detect_trigger_not_at_word_boundary() -> None:
    assert detect_trigger("hello@main") is None


def test_detect_trigger_space_after_trigger() -> None:
    assert detect_trigger("hello @ world") is None


def test_detect_trigger_command_with_args() -> None:
    result = detect_trigger("/model nvidia")
    # The last word is "nvidia" which has no trigger prefix
    assert result is None


def test_detect_trigger_tab_as_boundary() -> None:
    result = detect_trigger("hello\t@main")
    assert result is not None
    assert result[0] == AutocompleteMode.MENTION
    assert result[1] == "main"


# ---------------------------------------------------------------------------
# get_last_word
# ---------------------------------------------------------------------------


def test_get_last_word_simple() -> None:
    word, start, end = get_last_word("hello @main")
    assert word == "@main"
    assert start == 6
    assert end == 11


def test_get_last_word_trailing_space() -> None:
    word, start, end = get_last_word("hello @main ")
    assert word == ""
    assert start == 12
    assert end == 12


def test_get_last_word_empty() -> None:
    word, start, end = get_last_word("")
    assert word == ""
    assert start == 0
    assert end == 0


def test_get_last_word_single_word() -> None:
    word, start, end = get_last_word("hello")
    assert word == "hello"
    assert start == 0
    assert end == 5


# ---------------------------------------------------------------------------
# SlashCommandRegistry
# ---------------------------------------------------------------------------


def test_slash_command_registry_includes_cli_commands() -> None:
    registry = SlashCommandRegistry()
    commands = registry.get_commands()
    names = [c.name for c in commands]
    assert "/help" in names
    assert "/new" in names
    assert "/quit" in names


def test_slash_command_registry_includes_rune_commands() -> None:
    rune_cmds = [
        SlashCommandItem(
            kind=CommandKind.RUNE,
            name="/debug",
            description="Debug current state",
        ),
    ]
    registry = SlashCommandRegistry(rune_commands=rune_cmds)
    commands = registry.get_commands()
    names = [c.name for c in commands]
    assert "/debug" in names
    assert "/help" in names


def test_slash_command_registry_cli_commands_have_descriptions() -> None:
    registry = SlashCommandRegistry()
    commands = registry.get_commands()
    help_cmd = next(c for c in commands if c.name == "/help")
    assert help_cmd.description != ""


def test_slash_command_registry_filter_by_name() -> None:
    registry = SlashCommandRegistry()
    commands = registry.get_commands()
    filtered = SlashCommandRegistry._filter_by_name(commands, "model")
    names = [c.name for c in filtered]
    assert "/model" in names
    assert "/refresh-models" in names
    assert "/help" not in names


def test_slash_command_registry_filter_empty_query() -> None:
    registry = SlashCommandRegistry()
    commands = registry.get_commands()
    filtered = SlashCommandRegistry._filter_by_name(commands, "")
    assert filtered == commands


# ---------------------------------------------------------------------------
# MentionIndex
# ---------------------------------------------------------------------------


def _make_temp_project(files: dict[str, str]) -> Path:
    tmp = Path(tempfile.mkdtemp())
    for rel_path, content in files.items():
        fpath = tmp / rel_path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
    return tmp


def test_mention_index_files_returns_known_extensions() -> None:
    proj = _make_temp_project(
        {
            "src/main.py": "print('hello')",
            "README.md": "# Project",
        }
    )
    index = MentionIndex(proj)
    file_items = index.index_files()
    labels = [item.label for item in file_items]
    assert "src/main.py" in labels
    assert "README.md" in labels


def test_mention_index_files_skips_hidden_dirs() -> None:
    proj = _make_temp_project(
        {
            "src/main.py": "code",
            ".git/config": "git",
            "__pycache__/mod.cpython": "cache",
            "node_modules/pkg/index.js": "js",
            ".venv/lib/python3/site.py": "venv",
        }
    )
    index = MentionIndex(proj)
    file_items = index.index_files()
    labels = [item.label for item in file_items]
    assert "src/main.py" in labels
    assert not any(".git" in label for label in labels)
    assert not any("__pycache__" in label for label in labels)
    assert not any("node_modules" in label for label in labels)
    assert not any(".venv" in label for label in labels)


def test_mention_index_files_empty_for_nonexistent_path() -> None:
    index = MentionIndex(Path("/nonexistent/path/12345"))
    assert index.index_files() == []


def test_mention_index_files_respects_max_files() -> None:
    proj = _make_temp_project({f"file{i}.py": "code" for i in range(20)})
    index = MentionIndex(proj, max_files=5)
    file_items = index.index_files()
    assert len(file_items) == 5


def test_mention_index_skills_returns_skill_items() -> None:
    skills = [
        SkillManifest(
            name="debug-skill",
            description="Debug assistant",
            scope=SkillScope.PROJECT,
            path="/skills/debug-skill",
        ),
        SkillManifest(
            name="test-runner",
            description="Run tests",
            scope=SkillScope.PROJECT,
            path="/skills/test-runner",
        ),
    ]
    index = MentionIndex(Path("/tmp"), skills=skills)
    skill_items = index.index_skills()
    assert len(skill_items) == 2
    labels = [item.label for item in skill_items]
    assert "debug-skill" in labels
    assert "test-runner" in labels
    for item in skill_items:
        assert item.kind == MentionKind.SKILL


def test_mention_index_get_all_items() -> None:
    proj = _make_temp_project({"src/main.py": "code"})
    skills = [
        SkillManifest(
            name="my-skill",
            description="A skill",
            scope=SkillScope.PROJECT,
            path="/skills/my-skill",
        ),
    ]
    index = MentionIndex(proj, skills=skills)
    all_items = index.get_all_items()
    has_file = any(i.kind == MentionKind.FILE for i in all_items)
    has_skill = any(i.kind == MentionKind.SKILL for i in all_items)
    assert has_file
    assert has_skill


def test_mention_index_search_filters_by_query() -> None:
    proj = _make_temp_project(
        {
            "src/main.py": "code",
            "test/test_main.py": "test",
            "README.md": "read",
        }
    )
    index = MentionIndex(proj)
    results = index.search("main")
    labels = [item.label for item in results]
    assert "src/main.py" in labels
    assert "test/test_main.py" in labels
    assert "README.md" not in labels


def test_mention_index_search_empty_returns_all() -> None:
    proj = _make_temp_project({"src/main.py": "code"})
    index = MentionIndex(proj)
    all_items = index.get_all_items()
    results = index.search("")
    assert len(results) == len(all_items)


def test_mention_index_invalidate_clears_cache() -> None:
    proj = _make_temp_project({"src/main.py": "code"})
    index = MentionIndex(proj)
    first = index.get_all_items()
    # Add a new file
    (proj / "new_file.py").write_text("new", encoding="utf-8")
    index.invalidate()
    second = index.get_all_items()
    assert len(second) == len(first) + 1


# ---------------------------------------------------------------------------
# AutocompleteService
# ---------------------------------------------------------------------------


def _make_service(
    project_files: dict[str, str] | None = None,
    skills: list[SkillManifest] | None = None,
    rune_commands: list[SlashCommandItem] | None = None,
) -> AutocompleteService:
    files = project_files or {"main.py": "code", "utils.py": "util"}
    proj = _make_temp_project(files)
    index = MentionIndex(proj, skills=skills or [])
    registry = SlashCommandRegistry(rune_commands=rune_commands or [])
    return AutocompleteService(index, registry)


def test_autocomplete_process_input_opens_mention_popup() -> None:
    service = _make_service()
    changed = service.process_input("hello @main")
    assert changed
    assert service.is_open
    assert service.mode == AutocompleteMode.MENTION
    assert service.query == "main"


def test_autocomplete_process_input_opens_command_popup() -> None:
    service = _make_service()
    changed = service.process_input("/help")
    assert changed
    assert service.is_open
    assert service.mode == AutocompleteMode.COMMAND
    assert service.query == "help"


def test_autocomplete_process_input_closes_when_no_trigger() -> None:
    service = _make_service()
    service.process_input("@main")  # open
    assert service.is_open
    changed = service.process_input("hello")  # no trigger
    assert changed
    assert not service.is_open


def test_autocomplete_process_input_no_change_when_already_closed() -> None:
    service = _make_service()
    changed = service.process_input("hello")
    assert not changed
    assert not service.is_open


def test_autocomplete_process_input_updates_query_and_filters() -> None:
    service = _make_service(
        project_files={"main.py": "1", "utils.py": "2", "test_main.py": "3"}
    )
    service.process_input("@m")
    labels = [service.get_item_label(item) for item in service.get_visible_items()]
    assert "main.py" in labels
    assert "test_main.py" in labels
    assert "utils.py" not in labels


def test_autocomplete_get_visible_items_mention() -> None:
    service = _make_service(project_files={"main.py": "1", "utils.py": "2"})
    service.process_input("@")
    items = service.get_visible_items()
    assert len(items) == 2


def test_autocomplete_get_visible_items_command() -> None:
    service = _make_service()
    service.process_input("/")
    items = service.get_visible_items()
    assert len(items) > 0
    assert all(isinstance(i, SlashCommandItem) for i in items)


def test_autocomplete_get_item_label_mention_file() -> None:
    service = _make_service()
    item = MentionItem(
        MentionKind.FILE, "src/main.py", "src/main.py", path=Path("/src/main.py")
    )
    assert service.get_item_label(item) == "src/main.py"


def test_autocomplete_get_item_label_mention_skill() -> None:
    service = _make_service(
        skills=[
            SkillManifest(
                name="debug-skill",
                description="Debug tool",
                scope=SkillScope.PROJECT,
                path="/skills/debug",
            ),
        ],
    )
    # Skills should NOT appear in @ trigger (MENTION mode)
    service.process_input("@debug")
    items = service.get_visible_items()
    skill_items = [i for i in items if i.kind == MentionKind.SKILL]
    assert len(skill_items) == 0

    # But skills SHOULD appear in / trigger (COMMAND mode)
    service.process_input("/debug")
    items = service.get_visible_items()
    skill_items = [i for i in items if i.kind == MentionKind.SKILL]
    assert len(skill_items) == 1
    assert service.get_item_label(skill_items[0]) == "debug-skill"
    assert service.get_item_description(skill_items[0]) == "Debug tool"


def test_autocomplete_get_item_label_command() -> None:
    service = _make_service()
    item = SlashCommandItem(
        kind=CommandKind.SLASH, name="/help", description="Show help"
    )
    assert service.get_item_label(item) == "/help"
    assert service.get_item_description(item) == "Show help"


def test_autocomplete_get_item_kind() -> None:
    service = _make_service()
    file_item = MentionItem(MentionKind.FILE, "a.py", "a.py")
    skill_item = MentionItem(MentionKind.SKILL, "skill", "skill")
    cmd_item = SlashCommandItem(kind=CommandKind.SLASH, name="/help")
    assert service.get_item_kind(file_item) == "file"
    assert service.get_item_kind(skill_item) == "skill"
    assert service.get_item_kind(cmd_item) == "slash"


def test_autocomplete_get_insertion_text_file() -> None:
    service = _make_service()
    item = MentionItem(MentionKind.FILE, "src/main.py", "src/main.py")
    assert service.get_insertion_text(item) == "@src/main.py"


def test_autocomplete_get_insertion_text_skill() -> None:
    service = _make_service()
    item = MentionItem(
        kind=MentionKind.SKILL, label="debug-skill", value="@debug-skill"
    )
    assert service.get_insertion_text(item) == "@debug-skill"


def test_autocomplete_get_insertion_text_slash_skill_returns_slash_prefix() -> None:
    service = _make_service()
    item = MentionItem(
        kind=MentionKind.SKILL, label="debug-skill", value="@debug-skill"
    )
    service.mode = AutocompleteMode.COMMAND
    assert service.get_insertion_text(item) == "/debug-skill"


def test_autocomplete_get_insertion_text_mention_skill_returns_at_prefix() -> None:
    service = _make_service()
    item = MentionItem(
        kind=MentionKind.SKILL, label="debug-skill", value="@debug-skill"
    )
    service.mode = AutocompleteMode.MENTION
    assert service.get_insertion_text(item) == "@debug-skill"


def test_autocomplete_get_insertion_text_command() -> None:
    service = _make_service()
    item = SlashCommandItem(kind=CommandKind.SLASH, name="/help", value="/help")
    assert service.get_insertion_text(item) == "/help"


def test_autocomplete_create_chip_skill_command_mode() -> None:
    service = _make_service()
    item = MentionItem(
        kind=MentionKind.SKILL, label="debug-skill", value="@debug-skill"
    )
    service.mode = AutocompleteMode.COMMAND
    chip = service.create_chip(item)
    assert chip is not None
    assert chip.text == "/debug-skill"
    assert chip.kind == MentionKind.SKILL
    assert chip.icon == "auto_awesome"


def test_autocomplete_create_chip_skill_mention_mode() -> None:
    service = _make_service()
    item = MentionItem(
        kind=MentionKind.SKILL, label="debug-skill", value="@debug-skill"
    )
    service.mode = AutocompleteMode.MENTION
    chip = service.create_chip(item)
    assert chip is not None
    assert chip.text == "@debug-skill"
    assert chip.kind == MentionKind.SKILL
    assert chip.icon == "auto_awesome"


def test_autocomplete_get_word_range() -> None:
    service = _make_service()
    service.process_input("@main")
    start, end = service.get_word_range("hello @main")
    assert start == 6
    assert end == 11


def test_autocomplete_get_word_range_no_word() -> None:
    service = _make_service()
    start, end = service.get_word_range("hello ")
    assert start == -1
    assert end == -1


def test_autocomplete_move_down() -> None:
    service = _make_service(project_files={"a.py": "1", "b.py": "2", "c.py": "3"})
    service.process_input("@")
    assert service.selected_index == 0
    service.move_down()
    assert service.selected_index == 1
    service.move_down()
    assert service.selected_index == 2
    service.move_down()  # should clamp
    assert service.selected_index == 2


def test_autocomplete_move_up() -> None:
    service = _make_service(project_files={"a.py": "1", "b.py": "2"})
    service.process_input("@")
    service.selected_index = 1
    service.move_up()
    assert service.selected_index == 0
    service.move_up()  # should clamp at 0
    assert service.selected_index == 0


def test_autocomplete_close_resets_state() -> None:
    service = _make_service()
    service.process_input("@main")
    assert service.is_open
    service.close()
    assert not service.is_open
    assert service.mode == AutocompleteMode.NONE
    assert service.query == ""
    assert service.items == []
    assert service.selected_index == 0


def test_autocomplete_mode_mention_with_skills() -> None:
    service = _make_service(
        skills=[
            SkillManifest(
                name="my-skill",
                description="A test skill",
                scope=SkillScope.PROJECT,
                path="/skills/my-skill",
            ),
        ],
    )
    # Skills should NOT appear in @ trigger (MENTION mode)
    service.process_input("@my")
    items = service.get_visible_items()
    skill_items = [i for i in items if i.kind == MentionKind.SKILL]
    file_items = [i for i in items if i.kind == MentionKind.FILE]
    assert len(skill_items) == 0  # Skills should not appear in @ trigger
    assert all(i.kind == MentionKind.FILE for i in file_items)

    # But skills SHOULD appear in / trigger (COMMAND mode)
    service.process_input("/my")
    items = service.get_visible_items()
    skill_items = [i for i in items if i.kind == MentionKind.SKILL]
    assert len(skill_items) == 1
    assert skill_items[0].label == "my-skill"


def test_autocomplete_service_command_filtering() -> None:
    service = _make_service()
    service.process_input("/mod")
    items = service.get_visible_items()
    names = [i.name for i in items]
    assert "/model" in names
    assert "/models" in names
    assert "/refresh-models" in names
    assert "/help" not in names


def test_autocomplete_service_rune_command_in_commands() -> None:
    rune_cmds = [
        SlashCommandItem(kind=CommandKind.RUNE, name="/debug", description="Debug"),
    ]
    service = _make_service(rune_commands=rune_cmds)
    service.process_input("/debug")
    items = service.get_visible_items()
    assert len(items) == 1
    assert items[0].name == "/debug"
    assert items[0].kind == CommandKind.RUNE


def test_autocomplete_service_reopen_after_close() -> None:
    service = _make_service()
    service.process_input("@main")
    assert service.is_open
    service.close()
    assert not service.is_open
    service.process_input("@util")
    assert service.is_open
    assert service.query == "util"


def test_autocomplete_service_empty_items_when_no_match() -> None:
    service = _make_service(project_files={"main.py": "1"})
    service.process_input("@zzznomatch")
    items = service.get_visible_items()
    assert items == []


def test_autocomplete_service_command_empty_query_shows_all() -> None:
    service = _make_service()
    service.process_input("/")
    items = service.get_visible_items()
    assert len(items) > 0
    # Should include all CLI commands
    names = [i.name for i in items]
    assert "/help" in names
    assert "/quit" in names


# ---------------------------------------------------------------------------
# MentionChip creation
# ---------------------------------------------------------------------------


def test_autocomplete_create_chip_file() -> None:
    service = _make_service()
    item = MentionItem(
        MentionKind.FILE, "src/main.py", "src/main.py", path=Path("src/main.py")
    )
    chip = service.create_chip(item)
    assert chip is not None
    assert chip.text == "@src/main.py"
    assert chip.kind == MentionKind.FILE
    assert chip.path == Path("src/main.py")


def test_autocomplete_create_chip_skill() -> None:
    service = _make_service()
    item = MentionItem(kind=MentionKind.SKILL, label="debug", value="@debug")
    chip = service.create_chip(item)
    assert chip is not None
    assert chip.text == "@debug"
    assert chip.kind == MentionKind.SKILL
    assert chip.icon == "auto_awesome"


def test_autocomplete_create_chip_slash_command() -> None:
    service = _make_service()
    item = SlashCommandItem(kind=CommandKind.SLASH, name="/help")
    chip = service.create_chip(item)
    assert chip is not None
    assert chip.text == "/help"
    assert chip.kind == CommandKind.SLASH
    assert chip.icon == "slash"


def test_autocomplete_create_chip_rune_command() -> None:
    service = _make_service()
    item = SlashCommandItem(kind=CommandKind.RUNE, name="/debug")
    chip = service.create_chip(item)
    assert chip is not None
    assert chip.text == "/debug"
    assert chip.kind == CommandKind.RUNE
    assert chip.icon == "auto_awesome"


def test_autocomplete_create_chip_unknown_item() -> None:
    service = _make_service()
    chip = service.create_chip("not-an-item")
    assert chip is None
