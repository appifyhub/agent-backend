from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from di.di import DI
from features.chat.supported_files import KNOWN_IMAGE_FORMATS
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.integrations import prompt_resolvers
from util import log
from util.error_codes import AMBIGUOUS_IMAGE_INPUTS, INVALID_IMAGE_FORMAT, MISSING_IMAGE_INPUTS
from util.errors import ValidationError
from util.functions import parse_ai_message_content


# Not tested as it's just a proxy
class ComputerVisionAnalyzer:

    TOOL_TYPE: ToolType = ToolType.vision

    error: str | None = None
    __job_id: str
    __messages: list[BaseMessage]
    __vision_model: BaseChatModel

    def __init__(
        self,
        job_id: str,
        image_mime_types: list[str],
        configured_tool: ConfiguredTool,
        di: DI,
        image_urls: list[str] | None = None,
        image_b64s: list[str] | None = None,
        additional_context: str | None = None,
    ):
        self.__job_id = job_id
        self.__validate_inputs(image_mime_types, image_urls, image_b64s)

        # set up LLM image context
        content: list[str | dict] = []
        if additional_context:
            content.append({"type": "text", "text": additional_context})
        if image_urls is not None:
            for url, mime_type in zip(image_urls, image_mime_types):
                content.append({"type": "image_url", "image_url": {"url": url}})
        else:  # image_b64s is not None
            for b64, mime_type in zip(image_b64s, image_mime_types):
                data_uri = f"data:{mime_type};base64,{b64}"
                content.append({"type": "image_url", "image_url": {"url": data_uri}})

        # initialize the LLM
        system_prompt = prompt_resolvers.computer_vision(di.require_invoker_chat_type())
        self.__messages = [SystemMessage(system_prompt), HumanMessage(content)]
        self.__vision_model = di.chat_langchain_model(configured_tool)

    def __validate_inputs(
        self,
        image_mime_types: list[str],
        image_urls: list[str] | None,
        image_b64s: list[str] | None,
    ) -> None:
        for mime_type in image_mime_types:
            if mime_type not in KNOWN_IMAGE_FORMATS.values():
                raise ValidationError(f"Unsupported image format: {mime_type}", INVALID_IMAGE_FORMAT)
        if image_urls is not None and image_b64s is not None:
            raise ValidationError("Only one of URLs or Base64 values must be provided", AMBIGUOUS_IMAGE_INPUTS)
        if image_urls is None and image_b64s is None:
            raise ValidationError("Either URLs or Base64 values must be provided", MISSING_IMAGE_INPUTS)

    def execute(self) -> str | None:
        log.d(f"Starting computer vision analysis for job '{self.__job_id}'")
        self.error = None
        try:
            answer = self.__vision_model.invoke(self.__messages)
            return parse_ai_message_content(answer)
        except Exception as e:
            self.error = f"Computer vision analysis failed: {str(e)}"
            log.e("Computer vision analysis failed", e)
            return None
