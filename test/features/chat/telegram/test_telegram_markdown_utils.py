import unittest

from features.chat.telegram.telegram_markdown_utils import calculate_rendered_length, escape_markdown


class TelegramMarkdownUtilsTest(unittest.TestCase):

    def test_calculate_rendered_length_plain_text_and_unicode(self):
        self.assertEqual(calculate_rendered_length("Hello 😀"), 7)

    def test_calculate_rendered_length_excludes_legacy_markdown(self):
        self.assertEqual(calculate_rendered_length("Use *bold*, _italic_, and `code`."), 27)
        self.assertEqual(calculate_rendered_length("```python\nprint('hi')\n```"), 12)

    def test_calculate_rendered_length_counts_escaped_literals(self):
        text = "snake_case [value]"
        self.assertEqual(calculate_rendered_length(text), len(text))

    def test_escape_markdown_preserves_bold(self):
        # Telegram uses *bold* (single asterisk, not double!)
        self.assertEqual(escape_markdown("This is *bold* text"), "This is *bold* text")
        self.assertEqual(escape_markdown("*bold*"), "*bold*")

    def test_escape_markdown_preserves_italic(self):
        # Even count of _, should preserve formatting
        self.assertEqual(escape_markdown("This is _italic_ text"), "This is _italic_ text")
        self.assertEqual(escape_markdown("_italic_"), "_italic_")

    def test_escape_markdown_preserves_code(self):
        # Even count of `, should preserve formatting
        self.assertEqual(escape_markdown("Use `code` here"), "Use `code` here")
        self.assertEqual(escape_markdown("`code`"), "`code`")

    def test_escape_markdown_escapes_snake_case(self):
        # Mid-word underscores should be escaped
        self.assertEqual(escape_markdown("snake_case"), "snake\\_case")
        self.assertEqual(escape_markdown("version_1.0.0"), "version\\_1.0.0")
        self.assertEqual(escape_markdown("my_var_name"), "my\\_var\\_name")

    def test_escape_markdown_escapes_mid_word_asterisks(self):
        # Mid-word asterisks should be escaped
        self.assertEqual(escape_markdown("2*3*4"), "2\\*3\\*4")
        self.assertEqual(escape_markdown("a*b*c"), "a\\*b\\*c")

    def test_escape_markdown_escapes_unmatched_asterisk(self):
        # Odd count of *, should escape all
        self.assertEqual(escape_markdown("Plan A/B* testing"), "Plan A/B\\* testing")
        self.assertEqual(escape_markdown("Cost: $100*"), "Cost: $100\\*")

    def test_escape_markdown_escapes_unmatched_underscore(self):
        # Odd count of _, should escape all
        self.assertEqual(escape_markdown("Check the _config file"), "Check the \\_config file")
        self.assertEqual(escape_markdown("_test"), "\\_test")

    def test_escape_markdown_escapes_unmatched_backtick(self):
        # Odd count of `, should escape all
        self.assertEqual(escape_markdown("Use ` as separator"), "Use \\` as separator")
        self.assertEqual(escape_markdown("`test"), "\\`test")

    def test_escape_markdown_always_escapes_brackets(self):
        # Brackets are always escaped
        self.assertEqual(escape_markdown("array[0]"), "array\\[0]")
        self.assertEqual(escape_markdown("[test]"), "\\[test]")

    def test_escape_markdown_escapes_backslashes(self):
        # Backslashes should always be escaped
        self.assertEqual(escape_markdown("path\\to\\file"), "path\\\\to\\\\file")
        self.assertEqual(escape_markdown("C:\\Users"), "C:\\\\Users")

    def test_escape_markdown_mixed_formatting(self):
        # Complex cases with multiple formatting types
        text = "Use *bold* and _italic_ with snake_case"
        expected = "Use *bold* and _italic_ with snake\\_case"
        self.assertEqual(escape_markdown(text), expected)

    def test_escape_markdown_release_notes_style(self):
        # Typical release notes content
        text = "RELEASE v4.14.21 - Users can now see all AI and non-AI tool prices!"
        expected = "RELEASE v4.14.21 - Users can now see all AI and non-AI tool prices!"
        self.assertEqual(escape_markdown(text), expected)

    def test_escape_markdown_code_with_underscores(self):
        # Code blocks with snake_case (even backticks, even underscores)
        text = "Run `my_function()` now"
        expected = "Run `my_function()` now"
        self.assertEqual(escape_markdown(text), expected)

    def test_escape_markdown_empty_string(self):
        self.assertEqual(escape_markdown(""), "")

    def test_escape_markdown_only_special_chars(self):
        # Edge case: only special characters
        self.assertEqual(escape_markdown("***"), "\\*\\*\\*")
        self.assertEqual(escape_markdown("___"), "\\_\\_\\_")

    def test_escape_markdown_preserves_mixed_bold_italic(self):
        # Multiple formatting types together
        text = "*bold* and _italic_ and more *bold*"
        expected = "*bold* and _italic_ and more *bold*"
        self.assertEqual(escape_markdown(text), expected)

    def test_escape_markdown_real_world_failure_case(self):
        # Simulating the kind of content that might have caused HTTP 400
        text = "Version 4.14.21 adds `async` support for snake_case_vars (2*3*4 faster!)"
        expected = "Version 4.14.21 adds `async` support for snake\\_case\\_vars (2\\*3\\*4 faster!)"
        self.assertEqual(escape_markdown(text), expected)

    def test_escape_markdown_preserves_code_block(self):
        # Triple backticks for code blocks (multi-line)
        text = "Example:\n```python\nmy_var = 42\n```\nDone"
        expected = "Example:\n```python\nmy_var = 42\n```\nDone"
        self.assertEqual(escape_markdown(text), expected)

    def test_escape_markdown_preserves_code_block_with_special_chars(self):
        # Code blocks should preserve all special characters
        text = "```\nuse *this* and _that_\n```"
        expected = "```\nuse *this* and _that_\n```"
        self.assertEqual(escape_markdown(text), expected)

    def test_escape_markdown_mixed_inline_and_block_code(self):
        # Mix of inline code and code blocks
        text = "Use `inline` or:\n```\nblock code\n```"
        expected = "Use `inline` or:\n```\nblock code\n```"
        self.assertEqual(escape_markdown(text), expected)

    def test_escape_markdown_double_asterisk_bold(self):
        # Standard markdown double asterisk (should be preserved)
        self.assertEqual(escape_markdown("**bold text**"), "**bold text**")
        self.assertEqual(escape_markdown("**bold**"), "**bold**")
        self.assertEqual(escape_markdown("This is **bold text** here"), "This is **bold text** here")

    def test_escape_markdown_multi_word_single_asterisk(self):
        # Telegram format with spaces inside (should be preserved)
        self.assertEqual(escape_markdown("*multi word bold*"), "*multi word bold*")
        self.assertEqual(escape_markdown("*Ova verzija donosi poboljšanja*"), "*Ova verzija donosi poboljšanja*")

    def test_escape_markdown_multi_word_italic(self):
        # Italic with spaces inside (should be preserved)
        self.assertEqual(escape_markdown("_italic text_"), "_italic text_")
        self.assertEqual(escape_markdown("_multi word italic_"), "_multi word italic_")

    def test_escape_markdown_real_release_title(self):
        # Real-world release title from user's screenshot
        text = "**🚀 Verzija 5.0.6: Čišći Digitalni Otisak**"
        expected = "**🚀 Verzija 5.0.6: Čišći Digitalni Otisak**"
        self.assertEqual(escape_markdown(text), expected)

    def test_escape_markdown_bold_adjacent_to_punctuation(self):
        # Bold text adjacent to punctuation should be preserved
        self.assertEqual(escape_markdown("*bold*."), "*bold*.")
        self.assertEqual(escape_markdown("*bold*,"), "*bold*,")
        self.assertEqual(escape_markdown("*bold*!"), "*bold*!")
        self.assertEqual(escape_markdown("*bold*?"), "*bold*?")
        self.assertEqual(escape_markdown("(*bold*)"), "(*bold*)")

    def test_escape_markdown_bold_at_start_with_punctuation(self):
        # Bold at start of string adjacent to punctuation
        self.assertEqual(escape_markdown("*Hello.*"), "*Hello.*")
        self.assertEqual(escape_markdown("*Done*,"), "*Done*,")

    def test_escape_markdown_bold_in_sentence_with_punctuation(self):
        # Bold embedded in a sentence with trailing punctuation
        self.assertEqual(escape_markdown("Say *Hello.* right now"), "Say *Hello.* right now")
        self.assertEqual(escape_markdown("I am *very happy*, you know"), "I am *very happy*, you know")
