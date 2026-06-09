from google.genai.types import GenerateContentConfig, GoogleSearch, Tool
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from xai_sdk.chat import system, user
from xai_sdk.tools import web_search, x_search

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_provider_library import GOOGLE_AI, PERPLEXITY, XAI
from features.integrations import prompt_resolvers
from features.web_browsing.search_source_formatter import (
    format_sources_from_google,
    format_sources_from_perplexity,
    format_sources_from_xai,
)
from util import log
from util.config import config
from util.error_codes import EXTERNAL_EMPTY_RESPONSE, LLM_UNEXPECTED_RESPONSE, UNSUPPORTED_PROVIDER
from util.errors import ConfigurationError, ExternalServiceError


class AIWebSearch:

    TOOL_TYPE: ToolType = ToolType.search

    __search_query: str
    __configured_tool: ConfiguredTool
    __di: DI

    def __init__(self, search_query: str, configured_tool: ConfiguredTool, di: DI):
        self.__search_query = search_query
        self.__configured_tool = configured_tool
        self.__di = di

    def execute(self) -> AIMessage:
        log.t(f"Starting AI web search for {self.__search_query.replace(chr(10), ' \\n ')}")
        provider = self.__configured_tool.definition.provider
        if provider == PERPLEXITY:
            return self.__search_with_perplexity()
        elif provider == GOOGLE_AI:
            return self.__search_with_google()
        elif provider == XAI:
            return self.__search_with_xai()
        else:
            raise ConfigurationError(f"Unsupported search provider: '{provider.name}'", UNSUPPORTED_PROVIDER)

    def __search_with_perplexity(self) -> AIMessage:
        system_prompt = prompt_resolvers.sentient_web_search(self.__di.invoker_chat)
        llm_input: list[BaseMessage] = [SystemMessage(system_prompt), HumanMessage(self.__search_query)]
        llm = self.__di.chat_langchain_model(self.__configured_tool)
        response = llm.invoke(llm_input)
        if not isinstance(response, AIMessage):
            raise ExternalServiceError(f"Received a non-AI message from LLM: {response}", LLM_UNEXPECTED_RESPONSE)
        if not response.content:
            raise ExternalServiceError("AI web search returned empty content", EXTERNAL_EMPTY_RESPONSE)
        sources = format_sources_from_perplexity(response.additional_kwargs, self.__di)
        content = str(response.content) + sources
        log.d(f"Finished Perplexity web search, result size is {len(content)} characters")
        return AIMessage(content = content)

    def __search_with_google(self) -> AIMessage:
        client = self.__di.google_search_client(self.__configured_tool)
        response = client.models.generate_content(
            model = self.__configured_tool.definition.id,
            contents = self.__search_query,
            config = GenerateContentConfig(tools = [Tool(google_search = GoogleSearch())]),
        )

        if not response or not response.candidates:
            raise ExternalServiceError("No candidates in Google search response", EXTERNAL_EMPTY_RESPONSE)
        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            raise ExternalServiceError("No content in Google search candidate", EXTERNAL_EMPTY_RESPONSE)

        answer_text = response.text or ""
        if not answer_text:
            raise ExternalServiceError("Google search returned empty answer", EXTERNAL_EMPTY_RESPONSE)

        grounding = candidate.grounding_metadata
        chunks = (grounding.grounding_chunks or []) if grounding else []
        sources = format_sources_from_google(chunks, self.__di)
        content = answer_text + sources
        log.d(f"Finished Google web search, result size is {len(content)} characters")
        return AIMessage(content = content)

    def __search_with_xai(self) -> AIMessage:
        system_prompt = prompt_resolvers.sentient_web_search(self.__di.invoker_chat)
        client = self.__di.x_ai_client(self.__configured_tool, config.web_timeout_s * 6)
        chat = client.chat.create(
            model = self.__configured_tool.definition.id,
            messages = [system(system_prompt), user(self.__search_query)],
            tools = [web_search(), x_search()],
            include = ["inline_citations"],
        )
        response = chat.sample()

        answer_text = getattr(response, "content", None) or ""
        if not answer_text:
            raise ExternalServiceError("xAI search returned empty answer", EXTERNAL_EMPTY_RESPONSE)

        sources = format_sources_from_xai(response, self.__di)
        content = answer_text + sources
        log.d(f"Finished xAI web search, result size is {len(content)} characters")
        return AIMessage(content = content)
