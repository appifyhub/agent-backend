import unittest

from features.prompting.prompt_composer import (
    SECTIONS_DIVIDER,
    PromptComposer,
    PromptFragment,
    PromptSection,
    PromptVar,
    build,
)
from util.errors import ValidationError


class FunctionsTest(unittest.TestCase):

    def test_composer_add_and_render_basic(self):
        frag1 = PromptFragment(id = "f1", section = PromptSection.context, content = "Hello {agent_name}")
        frag2 = PromptFragment(id = "f2", section = PromptSection.format, content = "Format {language_name}")
        prompt = (
            PromptComposer()
            .add_fragments(frag1, frag2)
            .add_variables((PromptVar.agent_name, "World"), (PromptVar.language_name, "Y"))
            .render()
        )
        self.assertIn("[Context]\nHello World", prompt)
        self.assertIn("[Format]\nFormat Y", prompt)

    def test_composer_append_and_combine(self):
        a = PromptComposer().add_fragments(PromptFragment(id = "a", section = PromptSection.appendix, content = "A"))
        b = PromptComposer().add_fragments(PromptFragment(id = "b", section = PromptSection.appendix, content = "B"))
        ab = a.append(b)
        abc = PromptComposer.combine(a, b, PromptComposer())
        expected_grouped = "[Appendix]\nA\nB"
        self.assertEqual(ab.render(), expected_grouped)
        self.assertEqual(abc.render(), expected_grouped)

    def test_prompt_var_enum_keys(self):
        frag = PromptFragment(
            id = "f",
            section = PromptSection.meta,
            content = "Bot {agent_name}",
        )

        prompt = (
            PromptComposer()
            .add_fragments(frag)
            .add_variables((PromptVar.agent_name, "AgentX"))
            .render()
        )
        self.assertIn("[Metadata]\nBot AgentX", prompt)

    def test_multiple_variables(self):
        frag = PromptFragment(
            id = "mixed",
            section = PromptSection.context,
            content = "Agent {agent_name} in {language_name}",
        )
        composer = PromptComposer().add_fragments(frag).add_variables(
            (PromptVar.agent_name, "BotX"),
            (PromptVar.language_name, "English"),
        )
        result = composer.render()
        self.assertEqual(result, "[Context]\nAgent BotX in English")

    def test_sections_render_in_enum_order(self):
        composer = (
            PromptComposer()
            .add_fragments(
                PromptFragment(id = "a1", section = PromptSection.appendix, content = "A1"),
                PromptFragment(id = "f1", section = PromptSection.format, content = "F1"),
                PromptFragment(id = "c1", section = PromptSection.context, content = "C1"),
            )
        )
        result = composer.render()
        expected = SECTIONS_DIVIDER.join(
            [
                "[Context]\nC1",
                "[Format]\nF1",
                "[Appendix]\nA1",
            ],
        )
        self.assertEqual(result, expected)

    def test_bodies_group_in_insertion_order_within_section(self):
        composer = (
            PromptComposer()
            .add_fragments(
                PromptFragment(id = "s1", section = PromptSection.style, content = "one"),
            )
            .add_fragments(
                PromptFragment(id = "s2", section = PromptSection.style, content = "two"),
                PromptFragment(id = "s3", section = PromptSection.style, content = "three"),
            )
        )
        result = composer.render()
        self.assertEqual(result, "[Style]\none\ntwo\nthree")

    def test_missing_variables_raise_by_default(self):
        fragment = PromptFragment(id = "x", section = PromptSection.context, content = "Hi {agent_name}")
        comp = PromptComposer().add_fragments(fragment)
        with self.assertRaises(ValidationError) as context:
            comp.render()
        self.assertIn("Missing prompt variable", str(context.exception))

    def test_build_function_creates_composer(self):
        frag1 = PromptFragment(id = "f1", section = PromptSection.context, content = "Hello {agent_name}")
        frag2 = PromptFragment(id = "f2", section = PromptSection.style, content = "Style {language_name}")
        composer = build(frag1, frag2).add_variables((PromptVar.agent_name, "World"), (PromptVar.language_name, "Bold"))
        result = composer.render()
        self.assertIn("[Context]\nHello World", result)
        self.assertIn("[Style]\nStyle Bold", result)

    def test_empty_composer_renders_empty_string(self):
        result = PromptComposer().render()
        self.assertEqual(result, "")

    def test_empty_content_fragments_are_filtered_out(self):
        frag1 = PromptFragment(id = "empty", section = PromptSection.context, content = "")
        frag2 = PromptFragment(id = "whitespace", section = PromptSection.context, content = "   ")
        frag3 = PromptFragment(id = "real", section = PromptSection.context, content = "Real content")
        composer = PromptComposer().add_fragments(frag1, frag2, frag3)
        result = composer.render()
        self.assertEqual(result, "[Context]\nReal content")
