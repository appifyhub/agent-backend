import unittest
from dataclasses import fields

from features.external_tools.external_tool import ExternalTool, ToolType
from features.external_tools.external_tool_library import (
    VIDEO_GEN_P_VIDEO,
    VIDEO_GEN_RAY_3_2,
    VIDEO_GEN_SEEDANCE_2_0_FAST,
)
from features.external_tools.intelligence_presets import (
    INTELLIGENCE_PRESETS,
    IntelligencePreset,
    PresetChoices,
    default_tool_for,
    get_all_presets,
)
from util.errors import InternalError


class IntelligencePresetsTest(unittest.TestCase):

    def test_preset_choices_covers_all_tool_types(self):
        preset_field_names = {f.name for f in fields(PresetChoices)}
        tool_type_names = {t.value for t in ToolType if t != ToolType.deprecated}
        self.assertEqual(
            preset_field_names,
            tool_type_names,
            f"PresetChoices fields {preset_field_names} should match ToolTypes {tool_type_names}",
        )

    def test_all_presets_exist(self):
        self.assertIn(IntelligencePreset.lowest_price, INTELLIGENCE_PRESETS)
        self.assertIn(IntelligencePreset.highest_price, INTELLIGENCE_PRESETS)
        self.assertIn(IntelligencePreset.agent_choice, INTELLIGENCE_PRESETS)

    def test_preset_choices_as_dict_uses_tool_type_values(self):
        choices = INTELLIGENCE_PRESETS[IntelligencePreset.agent_choice]
        result = choices.as_dict()
        self.assertEqual(result["chat"], choices.chat.id)
        self.assertEqual(result["search"], choices.search.id)
        self.assertEqual(result["embedding"], choices.embedding.id)
        self.assertEqual(result["api_stock_quote"], choices.api_stock_quote.id)
        self.assertEqual(result["videos_gen"], VIDEO_GEN_SEEDANCE_2_0_FAST.id)

    def test_get_all_presets_returns_dict_with_all_presets(self):
        result = get_all_presets()
        self.assertIsInstance(result, dict)
        self.assertIn("lowest_price", result)
        self.assertIn("highest_price", result)
        self.assertIn("agent_choice", result)

    def test_get_all_presets_values_are_dicts(self):
        result = get_all_presets()
        for preset_name, choices in result.items():
            self.assertIsInstance(choices, dict, f"Preset {preset_name} should be a dict")
            for tool_type, tool_id in choices.items():
                self.assertIsInstance(tool_type, str)
                self.assertIsInstance(tool_id, str)

    def test_all_presets_have_required_tool_types(self):
        required_types = ["chat", "reasoning", "vision", "hearing", "videos_gen", "search", "embedding"]
        result = get_all_presets()
        for preset_name, choices in result.items():
            for tool_type in required_types:
                self.assertIn(
                    tool_type,
                    choices,
                    f"Preset {preset_name} missing required tool type {tool_type}",
                )

    def test_preset_tool_ids_are_non_empty(self):
        result = get_all_presets()
        for preset_name, choices in result.items():
            for tool_type, tool_id in choices.items():
                self.assertTrue(
                    len(tool_id) > 0,
                    f"Preset {preset_name} has empty tool_id for {tool_type}",
                )

    def test_default_tool_for_returns_external_tool(self):
        tool = default_tool_for(ToolType.chat)
        self.assertIsInstance(tool, ExternalTool)
        self.assertEqual(tool, INTELLIGENCE_PRESETS[IntelligencePreset.agent_choice].chat)

    def test_default_tool_for_all_non_deprecated_types(self):
        for tool_type in ToolType:
            if tool_type == ToolType.deprecated:
                continue
            tool = default_tool_for(tool_type)
            self.assertIsInstance(tool, ExternalTool)

    def test_video_generation_presets(self):
        self.assertEqual(
            INTELLIGENCE_PRESETS[IntelligencePreset.lowest_price].videos_gen,
            VIDEO_GEN_P_VIDEO,
        )
        self.assertEqual(
            INTELLIGENCE_PRESETS[IntelligencePreset.highest_price].videos_gen,
            VIDEO_GEN_RAY_3_2,
        )
        self.assertEqual(
            INTELLIGENCE_PRESETS[IntelligencePreset.agent_choice].videos_gen,
            VIDEO_GEN_SEEDANCE_2_0_FAST,
        )
        self.assertEqual(default_tool_for(ToolType.videos_gen), VIDEO_GEN_SEEDANCE_2_0_FAST)

    def test_default_tool_for_deprecated_raises(self):
        with self.assertRaises(InternalError) as context:
            default_tool_for(ToolType.deprecated)
        self.assertIn("Deprecated tool type", str(context.exception))
