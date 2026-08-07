import unittest

from features.social_cards.card_utils import (
    EMOJI_FONT_NAME,
    FONT_NAME,
    emoji_split,
    escape_xml,
    render_text_segments,
    rounded_rect_path,
    segment_width,
    text_width,
    trim_trailing_sep,
    word_wrap_truncate,
)


class CardUtilsTest(unittest.TestCase):

    def test_escape_xml_special_chars(self):
        assert escape_xml('a & b < c > d "e"') == "a &amp; b &lt; c &gt; d &quot;e&quot;"

    def test_escape_xml_no_special_chars(self):
        assert escape_xml("hello world") == "hello world"

    def test_escape_xml_empty(self):
        assert escape_xml("") == ""

    def test_trim_trailing_sep_dashes(self):
        assert trim_trailing_sep("hello -") == "hello"

    def test_trim_trailing_sep_pipes(self):
        assert trim_trailing_sep("title | ") == "title"

    def test_trim_trailing_sep_mixed(self):
        assert trim_trailing_sep("text —/") == "text"

    def test_trim_trailing_sep_no_sep(self):
        assert trim_trailing_sep("clean text") == "clean text"

    def test_text_width_returns_positive(self):
        width = text_width("hello", 20)
        assert width > 0

    def test_text_width_longer_text_wider(self):
        short = text_width("hi", 20)
        long = text_width("hello world", 20)
        assert long > short

    def test_text_width_larger_font_wider(self):
        small = text_width("test", 12)
        large = text_width("test", 24)
        assert large > small

    def test_rounded_rect_path_format(self):
        path = rounded_rect_path(10, 20, 100, 50, 5, 5, 5, 5)
        assert path.startswith("M 15,20")
        assert "Z" in path

    def test_rounded_rect_path_asymmetric_corners(self):
        path = rounded_rect_path(0, 0, 100, 100, 10, 0, 10, 0)
        assert "M 10,0" in path

    def test_word_wrap_truncate_short_text(self):
        lines = word_wrap_truncate("short", 500, 20, 3)
        assert lines == ["short"]

    def test_word_wrap_truncate_single_line_limit(self):
        lines = word_wrap_truncate("a b c d e f g h i j k l m n", 50, 20, 1)
        assert len(lines) == 1
        assert lines[0].endswith("…")

    def test_word_wrap_truncate_respects_max_lines(self):
        long_text = " ".join(["word"] * 50)
        lines = word_wrap_truncate(long_text, 100, 14, 3)
        assert len(lines) <= 3
        assert lines[-1].endswith("…")

    def test_word_wrap_truncate_no_truncation_needed(self):
        lines = word_wrap_truncate("hello world", 500, 20, 5)
        assert "…" not in lines[0]

    def test_word_wrap_truncate_empty_text(self):
        lines = word_wrap_truncate("", 500, 20, 3)
        assert lines == [""]

    def test_word_wrap_truncate_trims_trailing_sep(self):
        lines = word_wrap_truncate("title - this is a very long description that wraps", 80, 14, 1)
        assert len(lines) == 1
        assert not lines[0].endswith("- …")
        assert not lines[0].endswith(" -…")

    # emoji_split tests

    def test_emoji_split_no_emoji(self):
        result = emoji_split("hello world")
        assert result == [("hello world", False)]

    def test_emoji_split_only_emoji(self):
        result = emoji_split("🔥")
        assert len(result) == 1
        assert result[0][0] == "🔥"
        assert result[0][1] is True

    def test_emoji_split_mixed(self):
        result = emoji_split("hello 🌍 world")
        assert len(result) == 3
        assert result[0] == ("hello ", False)
        assert result[1][1] is True
        assert result[2] == (" world", False)

    def test_emoji_split_multiple_emoji(self):
        result = emoji_split("🎉🎊")
        assert all(is_emoji for _, is_emoji in result)

    def test_emoji_split_empty_string(self):
        result = emoji_split("")
        assert result == [("", False)]

    # segment_width tests

    def test_segment_width_text(self):
        w = segment_width("hello", 20, False)
        assert w > 0
        assert w == text_width("hello", 20)

    def test_segment_width_emoji(self):
        w = segment_width("🔥", 20, True)
        assert w > 0

    # render_text_segments tests

    def test_render_text_segments_single_text(self):
        segments = [("hello", "#ffffff", "", False)]
        elems, end_x = render_text_segments(segments, 10, 50, 20, "#ffffff")
        assert len(elems) == 1
        assert f'font-family="{FONT_NAME}"' in elems[0]
        assert 'fill="#ffffff"' in elems[0]
        assert "hello" in elems[0]
        assert end_x > 10

    def test_render_text_segments_emoji_uses_emoji_font(self):
        segments = [("🔥", "#000000", "", True)]
        elems, _ = render_text_segments(segments, 0, 0, 20, "#000000")
        assert len(elems) == 1
        assert f'font-family="{EMOJI_FONT_NAME}"' in elems[0]

    def test_render_text_segments_bold(self):
        segments = [("bold", "#111111", "", False)]
        elems, _ = render_text_segments(segments, 0, 0, 20, "#111111", weight = 700)
        assert 'stroke="#111111"' in elems[0]
        assert 'stroke-width="0.7"' in elems[0]

    def test_render_text_segments_multiple(self):
        segments = [
            ("hello ", "#ffffff", "", False),
            ("🌍", "#ffffff", "", True),
            (" world", "#ffffff", "", False),
        ]
        elems, end_x = render_text_segments(segments, 0, 0, 20, "#ffffff")
        assert len(elems) == 3
        assert end_x > 0

    def test_render_text_segments_escapes_xml(self):
        segments = [("<script>", "#fff", "", False)]
        elems, _ = render_text_segments(segments, 0, 0, 20, "#fff")
        assert "&lt;script&gt;" in elems[0]

    def test_render_text_segments_custom_fill(self):
        segments = [("link", "#ff0000", "", False)]
        elems, _ = render_text_segments(segments, 0, 0, 20, "#ffffff")
        assert 'fill="#ff0000"' in elems[0]

    def test_render_text_segments_empty_fill_uses_default(self):
        segments = [("text", "", "", False)]
        elems, _ = render_text_segments(segments, 0, 0, 20, "#aabbcc")
        assert 'fill="#aabbcc"' in elems[0]
