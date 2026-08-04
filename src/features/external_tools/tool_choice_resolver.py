from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ExternalTool, ExternalToolProvider, ToolType
from features.external_tools.external_tool_library import ALL_EXTERNAL_TOOLS
from util import log
from util.error_codes import TOOL_NOT_FOUND
from util.errors import NotFoundError

ToolsByProvider = dict[ExternalToolProvider, list[ExternalTool]]


class ToolResolutionError(NotFoundError):

    def __init__(self, purpose: ToolType, user_id: str):
        message = f"Unable to resolve a tool for '{purpose.value}' for user '{user_id}'. "
        message += "Open your profile settings page to configure your tool choices and tokens."
        super().__init__(message, TOOL_NOT_FOUND)


class ToolChoiceResolver:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def get_tool(self, purpose: ToolType, default_tool: str | ExternalTool | None = None) -> ConfiguredTool | None:
        log.t(f"Resolving tool for type '{purpose.value}' for user '{self.__di.invoker.id.hex}'")

        # 1. find the user's choice for this purpose
        user_choice_tool_id: str | None = self.__get_user_tool_choice(purpose)
        user_choice_tool: ExternalTool | None = None
        if user_choice_tool_id:
            log.t(f"  User's tool choice: '{user_choice_tool_id}'")
            user_choice_tool = ToolChoiceResolver.find_tool_by_id(user_choice_tool_id)

        # 2. get prioritized tools (user choice > default tool > others)
        prioritized_tools = ToolChoiceResolver.get_prioritized_tools(purpose, user_choice_tool, default_tool)
        log.t(f"Finished prioritizing {len(prioritized_tools)} tools")

        # 3. try tools in order of priority until one with access is found
        for tool in prioritized_tools:
            resolved_token = self.__di.access_token_resolver.get_access_token_for_tool(tool)
            if resolved_token:
                default_tool_id = (
                    default_tool.id
                    if isinstance(default_tool, ExternalTool)
                    else (default_tool if isinstance(default_tool, str) else "<none>")
                )
                log.t(f"Found available tool '{tool.id}' from provider '{tool.provider.name}'")
                log.t(f"  · Matches user choice '{user_choice_tool_id}'? {'Yes' if tool.id == user_choice_tool else 'No'}")
                log.t(f"  · Matches default tool '{default_tool_id}'? {'Yes' if tool.id == default_tool_id else 'No'}")
                return ConfiguredTool(
                    definition = tool,
                    token = resolved_token.token,
                    purpose = purpose,
                    payer_id = resolved_token.payer_id,
                    uses_credits = resolved_token.uses_credits,
                )
            log.t(f"No access to tool '{tool.id}' from provider '{tool.provider.name}'")

        log.t(f"No available tools found for type '{purpose.value}'")
        return None

    def require_tool(self, purpose: ToolType, default_tool: str | ExternalTool | None = None) -> ConfiguredTool:
        result = self.get_tool(purpose, default_tool)
        if result is None:
            raise ToolResolutionError(purpose, self.__di.invoker.id.hex)
        return result

    def __get_user_tool_choice(self, purpose: ToolType) -> str | None:
        match purpose:
            case ToolType.chat:
                return self.__di.invoker.tool_choice_chat
            case ToolType.reasoning:
                return self.__di.invoker.tool_choice_reasoning
            case ToolType.copywriting:
                return self.__di.invoker.tool_choice_copywriting
            case ToolType.vision:
                return self.__di.invoker.tool_choice_vision
            case ToolType.hearing:
                return self.__di.invoker.tool_choice_hearing
            case ToolType.images_gen:
                return self.__di.invoker.tool_choice_images_gen
            case ToolType.videos_gen:
                return self.__di.invoker.tool_choice_videos_gen
            case ToolType.search:
                return self.__di.invoker.tool_choice_search
            case ToolType.embedding:
                return self.__di.invoker.tool_choice_embedding
            case ToolType.api_fiat_exchange:
                return self.__di.invoker.tool_choice_api_fiat_exchange
            case ToolType.api_crypto_exchange:
                return self.__di.invoker.tool_choice_api_crypto_exchange
            case ToolType.api_stock_quote:
                return self.__di.invoker.tool_choice_api_stock_quote
            case ToolType.api_twitter:
                return self.__di.invoker.tool_choice_api_twitter
        log.w(f"Unknown purpose '{purpose.value}'")
        return None

    @staticmethod
    def find_tool_by_id(tool_id: str) -> ExternalTool | None:
        for tool in ALL_EXTERNAL_TOOLS:
            if tool.id == tool_id:
                return tool
        log.w(f"Tool with ID '{tool_id}' not found")
        return None

    @staticmethod
    def get_prioritized_tools(
        purpose: ToolType,
        user_choice_tool: str | ExternalTool | None = None,
        default_tool: str | ExternalTool | None = None,
    ) -> list[ExternalTool]:
        # materialize tools if they are IDs
        resolved_user_choice_tool: ExternalTool | None = (
            ToolChoiceResolver.find_tool_by_id(user_choice_tool) if isinstance(user_choice_tool, str) else user_choice_tool
        )
        resolved_default_tool: ExternalTool | None = (
            ToolChoiceResolver.find_tool_by_id(default_tool) if isinstance(default_tool, str) else default_tool
        )

        prioritized_tools: list[ExternalTool] = []

        # 1. user choice tool (highest priority), if compatible
        if resolved_user_choice_tool and purpose in resolved_user_choice_tool.types:
            prioritized_tools.append(resolved_user_choice_tool)

        # 2. default tool, if compatible and different from user choice
        if (
            resolved_default_tool
            and purpose in resolved_default_tool.types
            and resolved_default_tool != resolved_user_choice_tool
        ):
            prioritized_tools.append(resolved_default_tool)

        # 3. all other tools
        eligible_tools = [tool for tool in ALL_EXTERNAL_TOOLS if purpose in tool.types]
        for tool in eligible_tools:
            if tool not in prioritized_tools:
                prioritized_tools.append(tool)

        return prioritized_tools
