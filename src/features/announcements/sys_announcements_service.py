from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.integrations import prompt_resolvers
from util import log
from util.functions import parse_ai_message_content


# Not tested as it's just a proxy
class SysAnnouncementsService:

    TOOL_TYPE: ToolType = ToolType.copywriting

    __llm_input: list[BaseMessage]
    __copywriter: BaseChatModel
    __resolved_chat: ChatConfig

    def __init__(
        self,
        raw_information: str,
        target_chat: ChatConfig,
        configured_tool: ConfiguredTool,
        di: DI,
    ):
        validated_chat = di.authorization_service.validate_chat(target_chat)
        self.__resolved_chat = validated_chat
        system_prompt = prompt_resolvers.copywriting_new_system_event(validated_chat)
        self.__llm_input = []
        self.__llm_input.append(SystemMessage(system_prompt))
        self.__llm_input.append(HumanMessage(raw_information))
        self.__copywriter = di.chat_langchain_model(configured_tool)

    def execute(self) -> tuple[ChatConfig, AIMessage]:
        log.t(f"Starting information announcer for {str(self.__llm_input[-1].content).replace('\n', ' \\n ')}")
        try:
            response = self.__copywriter.invoke(self.__llm_input)
            content = parse_ai_message_content(response)
            log.d(f"Finished announcement creation, summary size is {len(content)} characters")
            return self.__resolved_chat, response.model_copy(update = {"content": content})
        except Exception as e:
            log.e("Information announcement failed", e)
            raise e
