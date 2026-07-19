from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.integrations import prompt_resolvers
from util import log
from util.functions import parse_ai_message_content


# Not tested as it's just a proxy
class ReleaseSummaryService:

    TOOL_TYPE: ToolType = ToolType.copywriting

    __llm_input: list[BaseMessage]
    __copywriter: BaseChatModel

    def __init__(
        self,
        raw_notes: str,
        target_chat: ChatConfig | None,
        configured_tool: ConfiguredTool,
        di: DI,
    ):
        chat_type = target_chat.chat_type if target_chat else ChatConfigDB.ChatType.github
        system_prompt = prompt_resolvers.copywriting_new_release_version(chat_type, target_chat)
        self.__llm_input = []
        self.__llm_input.append(SystemMessage(system_prompt))
        self.__llm_input.append(HumanMessage(raw_notes))
        self.__copywriter = di.chat_langchain_model(configured_tool)

    def execute(self) -> AIMessage:
        log.t(f"Starting release summarizer for {str(self.__llm_input[-1].content).replace('\n', ' \\n ')}")
        try:
            response = self.__copywriter.invoke(self.__llm_input)
            content = parse_ai_message_content(response)
            log.d(f"Finished summarizing, summary size is {len(content)} characters")
            return response.model_copy(update = {"content": content})
        except Exception as e:
            log.e("Release summarization failed", e)
            raise e
