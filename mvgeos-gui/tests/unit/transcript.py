"""Unit tests for the InvocationTranscript module.

Freezes the observable assembly behaviour of assistant Invocation bubbles:
part merging, contemplation tag decoding, spell step categorization, ID-based
spell-result pairing, projections over parts, and Tome replay reconstruction.
"""

from typing import Any

from mvgeos_gui.models import Artifact, MessagePartType, StepType
from mvgeos_gui.transcript import InvocationTranscript, format_duration


def part_types(transcript: InvocationTranscript) -> list[MessagePartType]:
    return [p.part_type for p in transcript.message.parts]


def texts_of(transcript: InvocationTranscript, kind: MessagePartType) -> list[str]:
    return [p.text for p in transcript.message.parts if p.part_type == kind and p.text]


def test_text_deltas_merge_into_single_part() -> None:
    t = InvocationTranscript()
    t.apply_message_update({"text": "Hello"})
    t.apply_message_update({"text": ", world"})
    assert part_types(t) == [MessagePartType.TEXT]
    assert texts_of(t, MessagePartType.TEXT) == ["Hello, world"]
    assert t.message.content == "Hello, world"


def test_thought_then_text_keeps_chronological_order() -> None:
    t = InvocationTranscript()
    t.apply_message_update({"text": "pondering", "kind": "contemplation"})
    t.apply_message_update({"text": "answer"})
    assert part_types(t) == [MessagePartType.CONTEMPLATION, MessagePartType.TEXT]
    assert t.message.contemplation == ["pondering"]
    assert t.message.content == "answer"


def test_contemplation_deltas_merge_into_last_part() -> None:
    t = InvocationTranscript()
    t.apply_message_update({"text": "thin", "kind": "contemplation"})
    t.apply_message_update({"text": "king", "kind": "contemplation"})
    t.apply_message_update({"text": "done", "kind": "text"})
    t.apply_message_update({"text": " more", "kind": "contemplation"})
    assert part_types(t) == [
        MessagePartType.CONTEMPLATION,
        MessagePartType.TEXT,
        MessagePartType.CONTEMPLATION,
    ]
    assert texts_of(t, MessagePartType.CONTEMPLATION) == ["thinking", " more"]


def test_empty_text_delta_is_ignored() -> None:
    t = InvocationTranscript()
    t.apply_message_update({"text": ""})
    assert t.message.parts == []


def test_inline_think_tags_decode_to_parts() -> None:
    t = InvocationTranscript()
    t.apply_message_update({"text": "<think>musing</think>visible"})
    assert part_types(t) == [MessagePartType.CONTEMPLATION, MessagePartType.TEXT]
    assert texts_of(t, MessagePartType.CONTEMPLATION) == ["musing"]
    assert t.message.content == "visible"


def test_unclosed_think_tag_at_stream_end_becomes_contemplation() -> None:
    t = InvocationTranscript()
    t.apply_message_update({"text": "<think>still going"})
    assert part_types(t) == [MessagePartType.CONTEMPLATION]
    assert t.message.content == ""


def test_begin_spell_bash_creates_commands_step() -> None:
    t = InvocationTranscript()
    step = t.begin_spell(
        {
            "spellCastId": "a1",
            "spellName": "bash",
            "arguments": {"command": "pytest -q"},
        }
    )
    assert step.step_type is StepType.COMMANDS
    assert part_types(t) == [MessagePartType.STEP]
    assert len(step.commands) == 1
    assert step.commands[0].command == "pytest -q"
    assert step.title == "Ran 1 command(s)"


def test_begin_spell_reader_creates_files_step() -> None:
    t = InvocationTranscript()
    step = t.begin_spell(
        {
            "spellCastId": "f1",
            "spellName": "read",
            "arguments": {"path": "src/x.py", "lines": "12"},
        }
    )
    assert step.step_type is StepType.FILES
    assert len(step.files) == 1
    assert step.files[0].path == "src/x.py"
    assert step.files[0].operation == "read"
    assert step.files[0].lines == "12"
    assert step.title == "Explored 1 file(s)"


def test_begin_spell_other_creates_worked_step_with_params() -> None:
    t = InvocationTranscript()
    step = t.begin_spell(
        {"spellCastId": "w1", "spellName": "edit", "arguments": {"file": "a.py"}}
    )
    assert step.step_type is StepType.WORKED
    assert step.spell_name == "edit"
    assert step.params == {"file": "a.py"}
    assert any("Executing edit" in d for d in step.details)


def test_end_spell_pairs_by_spell_id_not_position() -> None:
    t = InvocationTranscript()
    first = t.begin_spell(
        {"spellCastId": "a", "spellName": "bash", "arguments": {"command": "one"}}
    )
    second = t.begin_spell(
        {"spellCastId": "b", "spellName": "bash", "arguments": {"command": "two"}}
    )
    t.end_spell({"spellCastId": "b", "result": "b-output"}, duration_seconds=0.5)
    t.end_spell({"spellCastId": "a", "result": "a-output"}, duration_seconds=1.0)
    assert first.commands[0].output == "a-output"
    assert second.commands[0].output == "b-output"
    assert first.commands[0].is_error is False
    assert first.commands[0].duration_seconds == 1.0


def test_end_spell_marks_errors_on_command_entry() -> None:
    t = InvocationTranscript()
    step = t.begin_spell({"spellCastId": "e1", "spellName": "bash", "arguments": {}})
    t.end_spell({"spellCastId": "e1", "error": "boom"}, duration_seconds=0.2)
    assert step.commands[0].is_error is True
    assert step.commands[0].output == "boom"


def test_end_spell_files_step_fills_details() -> None:
    t = InvocationTranscript()
    step = t.begin_spell(
        {"spellCastId": "r1", "spellName": "grep", "arguments": {"path": "x"}}
    )
    t.end_spell({"spellCastId": "r1", "result": "match!"}, duration_seconds=0.3)
    assert step.files[0].details == "match!"
    assert step.files[0].is_error is False


def test_end_spell_worked_step_sets_result_and_duration() -> None:
    t = InvocationTranscript()
    step = t.begin_spell({"spellCastId": "w9", "spellName": "edit"})
    t.end_spell({"spellCastId": "w9", "result": "patched"}, duration_seconds=2.0)
    assert step.result == "patched"
    assert step.duration_seconds == 2.0
    assert step.is_complete is False


def test_end_spell_unknown_id_is_noop() -> None:
    t = InvocationTranscript()
    t.begin_spell({"spellCastId": "k1", "spellName": "bash", "arguments": {}})
    t.end_spell({"spellCastId": "ghost", "result": "?"}, duration_seconds=0.1)
    assert t.message.steps[0].commands[0].output == ""
    t.end_spell({"spellCastId": "k1", "result": "ok"}, duration_seconds=0.1)
    assert t.message.steps[0].commands[0].output == "ok"


def test_finish_completes_worked_steps_and_stops_streaming() -> None:
    t = InvocationTranscript()
    step = t.begin_spell({"spellCastId": "w1", "spellName": "edit"})
    t.apply_message_update({"text": "done"})
    t.finish()
    assert step.is_complete is True
    assert t.message.is_streaming is False


def test_worked_title_formats_elapsed_time() -> None:
    t = InvocationTranscript()
    step = t.begin_spell({"spellCastId": "t1", "spellName": "edit"})
    t.end_spell(
        {"spellCastId": "t1", "result": "r"},
        duration_seconds=1.0,
        elapsed_seconds=65.0,
    )
    assert step.title == "Worked for 1m 5s"


def test_format_duration_variants() -> None:
    """Verify duration labels render as ms, seconds, and minutes."""
    assert format_duration(0.4) == "400ms"
    assert format_duration(25.3) == "25.3s"
    assert format_duration(125.0) == "2m 5s"


def test_begin_spell_reader_without_path_produces_no_card() -> None:
    t = InvocationTranscript()
    step = t.begin_spell({"spellCastId": "n1", "spellName": "read"})
    assert step is None
    assert t.message.parts == []


def test_set_text_replaces_parts_with_single_text_part() -> None:
    t = InvocationTranscript()
    t.apply_message_update({"text": "partial", "kind": "contemplation"})
    t.set_text("Fatal error occurred")
    assert part_types(t) == [MessagePartType.TEXT]
    assert texts_of(t, MessagePartType.TEXT) == ["Fatal error occurred"]


def test_append_text_merges_into_text_projection() -> None:
    t = InvocationTranscript()
    t.apply_message_update({"text": "partial answer"})
    t.append_text("\n\n*(Cancelled by summoner)*")
    assert t.message.content == "partial answer\n\n*(Cancelled by summoner)*"


def test_add_artifact_appends_part_and_backref() -> None:
    t = InvocationTranscript()
    artifact = Artifact(id="af1", title="Review")
    t.add_artifact(artifact)
    assert part_types(t) == [MessagePartType.ARTIFACT]
    assert t.message.parts[0].artifact is artifact
    assert t.message.artifacts == [artifact]


def test_projections_derive_from_parts() -> None:
    t = InvocationTranscript()
    t.apply_message_update({"text": "intro"})
    step = t.begin_spell({"spellCastId": "p1", "spellName": "bash", "arguments": {}})
    t.apply_message_update({"text": "<think>why</think>outro"})
    assert t.message.content == "introoutro"
    assert t.message.contemplation == ["why"]
    assert t.message.steps == [step]


def test_from_tome_content_string_with_tags() -> None:
    t = InvocationTranscript.from_tome_content("<think>plan</think>Result text")
    assert part_types(t) == [MessagePartType.CONTEMPLATION, MessagePartType.TEXT]
    assert t.message.content == "Result text"
    assert t.message.contemplation == ["plan"]


def test_from_tome_content_list_shapes() -> None:
    content: list[dict[str, Any]] = [
        {"type": "contemplation", "text": "c-thought"},
        {"type": "thinking", "thinking": "k-thought"},
        {"type": "text", "text": "plain <think>t</think> words"},
        {"type": "tool_call", "name": "bash", "arguments": {"command": "ls"}},
        {"type": "tool_use", "name": "read", "arguments": {"path": "/a/b"}},
        {"type": "unknown", "text": "fallback text"},
        "bare string item",
    ]
    t = InvocationTranscript.from_tome_content(content)
    assert part_types(t) == [
        MessagePartType.CONTEMPLATION,
        MessagePartType.CONTEMPLATION,
        MessagePartType.CONTEMPLATION,
        MessagePartType.TEXT,
        MessagePartType.STEP,
        MessagePartType.STEP,
        MessagePartType.TEXT,
        MessagePartType.TEXT,
    ]
    steps = t.message.steps
    assert len(steps) == 2
    assert all(s.is_complete for s in steps)
    assert steps[0].step_type is StepType.COMMANDS
    assert steps[0].spell_name == "bash"
    assert steps[0].params == {"command": "ls"}
    assert steps[1].step_type is StepType.FILES
    assert t.message.content.endswith("bare string item")


def test_from_tome_content_tool_call_without_arguments() -> None:
    t = InvocationTranscript.from_tome_content([{"type": "tool_call", "name": "edit"}])
    step = t.message.steps[0]
    assert step.step_type is StepType.WORKED
    assert step.params == {}
    assert step.is_complete is True


def test_from_tome_content_empty_inputs() -> None:
    for empty in ("", None, []):
        t = InvocationTranscript.from_tome_content(empty)
        assert t.message.parts == []
        assert t.message.content == ""


def test_replayed_steps_render_completed_state() -> None:
    t = InvocationTranscript.from_tome_content(
        [{"type": "tool_use", "name": "find", "arguments": {"path": "z"}}]
    )
    step = t.message.steps[0]
    assert step.step_type is StepType.FILES
    assert step.is_complete is True
    assert step.title == ""
