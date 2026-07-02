from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_perplexity import ChatPerplexity
from langchain_xai import ChatXAI

from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ExternalTool, ToolType
from features.external_tools.external_tool_library import CLAUDE_5_FABLE, CLAUDE_5_SONNET
from features.external_tools.external_tool_provider_library import (
    ANTHROPIC,
    GOOGLE_AI,
    OPEN_AI,
    PERPLEXITY,
    XAI,
)
from util.config import config
from util.error_codes import UNSUPPORTED_PROVIDER
from util.errors import ConfigurationError

NO_TEMPERATURE_MODELS = {
    CLAUDE_5_SONNET.id,
    CLAUDE_5_FABLE.id,
}


def create(configured_tool: ConfiguredTool, max_tokens: int) -> BaseChatModel:
    definition = configured_tool.definition
    purpose = configured_tool.purpose

    temperature = __normalize_temperature(purpose.temperature_percent, definition)
    model_args = {
        "model": definition.id,
        "max_tokens": max_tokens,
        "timeout": __get_timeout(purpose, definition),
        "max_retries": config.web_retries,
        "api_key": configured_tool.token,
    }
    if temperature is not None:
        model_args["temperature"] = temperature

    match definition.provider.id:
        case OPEN_AI.id:
            return ChatOpenAI(**model_args)
        case ANTHROPIC.id:
            return ChatAnthropic(**model_args)
        case PERPLEXITY.id:
            return ChatPerplexity(**model_args)
        case GOOGLE_AI.id:
            return ChatGoogleGenerativeAI(**model_args)
        case XAI.id:
            return ChatXAI(**model_args)
    raise ConfigurationError(f"{definition.provider.name}/{definition.name} does not support LLMs", UNSUPPORTED_PROVIDER)


def __normalize_temperature(temperature_percent: float, tool: ExternalTool) -> float | None:
    if tool.id in NO_TEMPERATURE_MODELS:
        return None
    match tool.provider.id:
        case OPEN_AI.id:
            return temperature_percent * 2
        case ANTHROPIC.id:
            return temperature_percent * 1
        case PERPLEXITY.id:
            return temperature_percent * 2
        case GOOGLE_AI.id:
            return temperature_percent * 2
        case XAI.id:
            return temperature_percent * 2
    raise ConfigurationError(f"{tool.provider.name}/{tool.provider.id} does not support temperature", UNSUPPORTED_PROVIDER)


def __get_timeout(tool_type: ToolType, tool: ExternalTool) -> float:
    match tool_type:
        case ToolType.chat:
            if ToolType.reasoning in tool.types:
                return float(config.web_timeout_s) * 3
            return float(config.web_timeout_s)
        case ToolType.reasoning:
            return float(config.web_timeout_s) * 3
        case ToolType.copywriting:
            return float(config.web_timeout_s)
        case ToolType.vision:
            return float(config.web_timeout_s) * 2
        case ToolType.search:
            return float(config.web_timeout_s) * 3
    raise ConfigurationError(f"{tool_type} does not support text timeouts", UNSUPPORTED_PROVIDER)
