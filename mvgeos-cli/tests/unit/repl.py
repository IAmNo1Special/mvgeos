from __future__ import annotations

from mvgeos_cli.commands.repl import _StreamFilter


class TestChannelTagStripping:
    def test_channel_tag_stripped_from_content(self) -> None:
        f = _StreamFilter()
        assert f.feed("Let me list <channel|list>\n") == "Let me list\n"

    def test_channel_tag_alone_yields_empty(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|list>\n") == ""

    def test_empty_channel_tag_stripped(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|>\n") == ""

    def test_channel_tag_stripped_before_newline(self) -> None:
        f = _StreamFilter()
        assert f.feed("text<channel|commentary>\n") == "text\n"

    def test_channel_tag_after_content(self) -> None:
        f = _StreamFilter()
        assert f.feed("done <channel|>\n") == "done\n"

    def test_channel_tag_partial_across_chunks(self) -> None:
        f = _StreamFilter()
        assert f.feed("see <channel|") == "see "
        assert f.feed("list>\n") == ""
        assert f.feed("Done\n") == "Done\n"

    def test_multiple_channel_tags_on_one_line(self) -> None:
        f = _StreamFilter()
        result = f.feed("start <channel|x> middle <channel|y> end\n")
        assert result == "start  middle  end\n"

    def test_channel_tag_case_insensitive(self) -> None:
        f = _StreamFilter()
        assert f.feed("text <CHANNEL|LIST>\n") == "text\n"


class TestReasoningChannelSuppression:
    def test_reasoning_channel_enters_suppression(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|reasoning>\n") == ""
        assert f.feed("secret thought\n") == ""
        assert f.feed("<channel|list>\n") == ""
        assert f.feed("Here is the answer\n") == "Here is the answer\n"

    def test_thinking_channel_enters_suppression(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|thinking>\n") == ""
        assert f.feed("thinking hard\n") == ""
        assert f.feed("<channel|>\n") == ""
        assert f.feed("result\n") == "result\n"

    def test_thought_channel_enters_suppression(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|thought>\n") == ""
        assert f.feed("pondering\n") == ""
        assert f.feed("<channel|>\n") == ""
        assert f.feed("result\n") == "result\n"

    def test_commentary_channel_exits_reasoning(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|reasoning>\n") == ""
        assert f.feed("hidden\n") == ""
        assert f.feed("<channel|commentary>\n") == ""
        assert f.feed("visible\n") == "visible\n"

    def test_empty_channel_exits_reasoning(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|reasoning>\n") == ""
        assert f.feed("hidden\n") == ""
        assert f.feed("<channel|>\n") == ""
        assert f.feed("visible\n") == "visible\n"

    def test_list_channel_exits_reasoning(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|thinking>\n") == ""
        assert f.feed("hidden\n") == ""
        assert f.feed("<channel|list>\n") == ""
        assert f.feed("visible\n") == "visible\n"

    def test_reasoning_channel_with_inline_text_suppressed(self) -> None:
        f = _StreamFilter()
        assert f.feed("prefix <channel|reasoning>body\n") == "prefix\n"
        assert f.feed("hidden\n") == ""
        assert f.feed("<channel|>\n") == ""
        assert f.feed("after\n") == "after\n"

    def test_open_and_close_on_same_line_not_stuck(self) -> None:
        f = _StreamFilter()
        assert f.feed("x<channel|reasoning>y<channel|list>z\n") == "xz\n"
        assert f.feed("leak check\n") == "leak check\n"

    def test_close_tag_inline_suppresses_reasoning_prefix(self) -> None:
        f = _StreamFilter()
        f.feed("<channel|reasoning>\n")
        assert f.feed("secret <channel|list>visible\n") == "visible\n"
        assert f.feed("more after close\n") == "more after close\n"

    def test_close_tag_only_line_does_not_leak(self) -> None:
        f = _StreamFilter()
        f.feed("<channel|reasoning>\n")
        assert f.feed("<channel|list>\n") == ""
        assert f.feed("visible now\n") == "visible now\n"


class TestMarkdownHeadingPreservation:
    def test_thinking_heading_lowercase_preserved(self) -> None:
        f = _StreamFilter()
        assert f.feed("# thinking\n") == "# thinking\n"

    def test_thought_heading_preserved(self) -> None:
        f = _StreamFilter()
        assert f.feed("# Thought\n") == "# Thought\n"

    def test_reasoning_heading_preserved(self) -> None:
        f = _StreamFilter()
        assert f.feed("# Reasoning\n") == "# Reasoning\n"

    def test_thinking_heading_no_space_preserved(self) -> None:
        f = _StreamFilter()
        assert f.feed("#thinking\n") == "#thinking\n"

    def test_markdown_heading_after_reasoning_channel_preserved(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|reasoning>\n") == ""
        assert f.feed("reasoning content\n") == ""
        assert f.feed("<channel|>\n") == ""
        assert f.feed("# Summary\n") == "# Summary\n"

    def test_markdown_heading_inside_reasoning_suppressed(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|reasoning>\n") == ""
        assert f.feed("# Summary\n") == ""
        assert f.feed("after heading\n") == ""
        assert f.feed("<channel|>\n") == ""
        assert f.feed("visible\n") == "visible\n"


class TestStandaloneWordPreservation:
    def test_standalone_thought_preserved(self) -> None:
        f = _StreamFilter()
        assert f.feed("thought\n") == "thought\n"

    def test_standalone_thinking_preserved(self) -> None:
        f = _StreamFilter()
        assert f.feed("thinking\n") == "thinking\n"

    def test_standalone_reasoning_preserved(self) -> None:
        f = _StreamFilter()
        assert f.feed("reasoning\n") == "reasoning\n"


class TestNormalContent:
    def test_normal_markdown_preserved(self) -> None:
        f = _StreamFilter()
        assert f.feed("# Title\n") == "# Title\n"
        assert f.feed("body\n") == "body\n"

    def test_empty_lines_preserved(self) -> None:
        f = _StreamFilter()
        assert f.feed("a\n\nb\n") == "a\n\nb\n"

    def test_multiline_content(self) -> None:
        f = _StreamFilter()
        text = "Line1\nLine2\nLine3\n"
        assert f.feed(text) == text

    def test_inline_channel_tag_in_markdown(self) -> None:
        f = _StreamFilter()
        result = f.feed("Some text <channel|list> more text\n")
        assert result == "Some text  more text\n"


class TestFlush:
    def test_flush_pending(self) -> None:
        f = _StreamFilter()
        assert f.feed("Hello") == "Hello"
        assert f.flush() == ""

    def test_flush_suppresses_reasoning(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|reasoning>\n") == ""
        assert f.feed("suppressed text") == ""
        assert f.flush() == ""

    def test_flush_clean_line(self) -> None:
        f = _StreamFilter()
        assert f.feed("see <channel|list>") == "see "
        assert f.flush() == ""

    def test_flush_incomplete_channel_tag(self) -> None:
        f = _StreamFilter()
        f.feed("before <channel|")
        result = f.flush()
        assert result == "<channel|"

    def test_flush_whitespace_leftover(self) -> None:
        f = _StreamFilter()
        f.feed("   ")
        assert f.flush() == ""

    def test_flush_markdown_preserved(self) -> None:
        f = _StreamFilter()
        assert f.feed("# thinking") == "# thinking"
        assert f.flush() == ""


class TestReset:
    def test_reset_clears_reasoning_state(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|reasoning>\n") == ""
        f.reset()
        assert f.feed("clean\n") == "clean\n"

    def test_reset_clears_pending(self) -> None:
        f = _StreamFilter()
        f.feed("partial")
        f.reset()
        assert f.feed("rest\n") == "rest\n"


class TestStreamingEdgeCases:
    def test_thinking_heading_then_real_channel(self) -> None:
        f = _StreamFilter()
        assert f.feed("# thinking\n") == "# thinking\n"
        assert f.feed("This is real content\n") == "This is real content\n"
        assert f.feed("<channel|reasoning>\n") == ""
        assert f.feed("suppressed\n") == ""
        assert f.feed("<channel|list>\n") == ""
        assert f.feed("back to normal\n") == "back to normal\n"

    def test_channel_tag_escaped_angle_brackets(self) -> None:
        f = _StreamFilter()
        assert f.feed("x < y and z > w\n") == "x < y and z > w\n"

    def test_nested_looking_tags_not_treated_as_channels(self) -> None:
        f = _StreamFilter()
        assert f.feed("<div>not a channel</div>\n") == "<div>not a channel</div>\n"

    def test_reasoning_channel_case_insensitive(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|REASONING>\n") == ""
        assert f.feed("hidden\n") == ""
        assert f.feed("<channel|LIST>\n") == ""
        assert f.feed("visible\n") == "visible\n"

    def test_nested_reasoning_channel_keeps_suppression(self) -> None:
        f = _StreamFilter()
        assert f.feed("<channel|reasoning>\n") == ""
        assert f.feed("<channel|thinking>\n") == ""
        assert f.feed("still hidden\n") == ""
        assert f.feed("<channel|list>\n") == ""
        assert f.feed("visible\n") == "visible\n"

    def test_reasoning_tag_in_unterminated_chunk_keeps_prefix(self) -> None:
        f = _StreamFilter()
        assert f.feed("see <channel|reasoning>body") == "see "
        assert f.feed("hidden\n") == ""
        assert f.feed("<channel|>\n") == ""
        assert f.feed("after\n") == "after\n"
