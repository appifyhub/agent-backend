from dataclasses import dataclass
from enum import Enum

from features.external_tools.external_tool import ExternalTool, ToolType
from features.external_tools.external_tool_library import (
    CLAUDE_4_6_OPUS,
    CLAUDE_4_6_SONNET,
    CLAUDE_4_7_OPUS,
    CRYPTO_CURRENCY_EXCHANGE,
    FIAT_CURRENCY_EXCHANGE,
    GEMINI_FLASH_LATEST,
    GPT_4O_MINI_TRANSCRIBE,
    GPT_4O_TRANSCRIBE,
    GPT_5_2,
    GPT_5_4,
    GPT_5_NANO,
    IMAGE_GEN_EDIT_FLUX_2_PRO,
    IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA_PRO,
    IMAGE_GEN_EDIT_SEEDREAM_4,
    TEXT_EMBEDDING_3_SMALL,
    TEXT_EMBEDDING_5_LARGE,
    TRANSFER_TOOL,
    WHISPER_1,
    X_READ_POST,
)
from util.error_codes import UNEXPECTED_ERROR
from util.errors import InternalError


class IntelligencePreset(str, Enum):
    lowest_price = "lowest_price"
    highest_price = "highest_price"
    agent_choice = "agent_choice"


@dataclass(frozen = True)
class PresetChoices:
    chat: ExternalTool
    copywriting: ExternalTool
    reasoning: ExternalTool
    vision: ExternalTool
    hearing: ExternalTool
    images_gen: ExternalTool
    images_edit: ExternalTool
    search: ExternalTool
    embedding: ExternalTool
    api_fiat_exchange: ExternalTool
    api_crypto_exchange: ExternalTool
    api_twitter: ExternalTool
    credit_transfer: ExternalTool

    def as_dict(self) -> dict[str, str]:
        return {
            ToolType.chat.value: self.chat.id,
            ToolType.copywriting.value: self.copywriting.id,
            ToolType.reasoning.value: self.reasoning.id,
            ToolType.vision.value: self.vision.id,
            ToolType.hearing.value: self.hearing.id,
            ToolType.images_gen.value: self.images_gen.id,
            ToolType.images_edit.value: self.images_edit.id,
            ToolType.search.value: self.search.id,
            ToolType.embedding.value: self.embedding.id,
            ToolType.api_fiat_exchange.value: self.api_fiat_exchange.id,
            ToolType.api_crypto_exchange.value: self.api_crypto_exchange.id,
            ToolType.api_twitter.value: self.api_twitter.id,
        }


INTELLIGENCE_PRESETS: dict[IntelligencePreset, PresetChoices] = {

    IntelligencePreset.lowest_price: PresetChoices(
        chat = GPT_5_NANO,
        copywriting = GPT_5_NANO,
        reasoning = GPT_5_NANO,
        vision = GPT_5_NANO,
        hearing = WHISPER_1,
        images_gen = IMAGE_GEN_EDIT_SEEDREAM_4,
        images_edit = IMAGE_GEN_EDIT_SEEDREAM_4,
        search = GEMINI_FLASH_LATEST,
        embedding = TEXT_EMBEDDING_3_SMALL,
        api_fiat_exchange = FIAT_CURRENCY_EXCHANGE,
        api_crypto_exchange = CRYPTO_CURRENCY_EXCHANGE,
        api_twitter = X_READ_POST,
        credit_transfer = TRANSFER_TOOL,
    ),

    IntelligencePreset.highest_price: PresetChoices(
        chat = CLAUDE_4_7_OPUS,
        copywriting = CLAUDE_4_7_OPUS,
        reasoning = CLAUDE_4_6_OPUS,
        vision = GPT_5_2,
        hearing = GPT_4O_TRANSCRIBE,
        images_gen = IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA_PRO,
        images_edit = IMAGE_GEN_EDIT_GOOGLE_NANO_BANANA_PRO,
        search = GEMINI_FLASH_LATEST,
        embedding = TEXT_EMBEDDING_5_LARGE,
        api_fiat_exchange = FIAT_CURRENCY_EXCHANGE,
        api_crypto_exchange = CRYPTO_CURRENCY_EXCHANGE,
        api_twitter = X_READ_POST,
        credit_transfer = TRANSFER_TOOL,
    ),

    IntelligencePreset.agent_choice: PresetChoices(
        chat = GPT_5_4,
        copywriting = GPT_5_4,
        reasoning = CLAUDE_4_6_SONNET,
        vision = GPT_5_2,
        hearing = GPT_4O_MINI_TRANSCRIBE,
        images_gen = IMAGE_GEN_EDIT_FLUX_2_PRO,
        images_edit = IMAGE_GEN_EDIT_FLUX_2_PRO,
        search = GEMINI_FLASH_LATEST,
        embedding = TEXT_EMBEDDING_3_SMALL,
        api_fiat_exchange = FIAT_CURRENCY_EXCHANGE,
        api_crypto_exchange = CRYPTO_CURRENCY_EXCHANGE,
        api_twitter = X_READ_POST,
        credit_transfer = TRANSFER_TOOL,
    ),

}


def default_tool_for(tool_type: ToolType) -> ExternalTool:
    if tool_type == ToolType.deprecated:
        raise InternalError("Deprecated tool type cannot be requested", UNEXPECTED_ERROR)
    choices = INTELLIGENCE_PRESETS[IntelligencePreset.agent_choice]
    tool: ExternalTool | None = getattr(choices, tool_type.value, None)
    if tool is None:
        raise InternalError(f"No default tool configured for '{tool_type.value}'", UNEXPECTED_ERROR)
    return tool


def get_all_presets() -> dict[str, dict[str, str]]:
    return {preset.value: choices.as_dict() for preset, choices in INTELLIGENCE_PRESETS.items()}
