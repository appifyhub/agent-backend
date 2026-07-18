from enum import Enum

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.integrations import prompt_resolvers
from util import log
from util.functions import parse_ai_message_content


class SmartImageGenerator:

    class Result(Enum):
        success = "Success"
        failed = "Failed"

    COPYWRITER_TOOL_TYPE: ToolType = ToolType.copywriting
    IMAGE_GEN_TOOL_TYPE: ToolType = ToolType.images_gen

    error: str | None = None
    __llm_input: list[BaseMessage]
    __image_gen_tool: ConfiguredTool
    __copywriter: BaseChatModel
    __aspect_ratio: str | None
    __output_size: str | None
    __di: DI

    def __init__(
        self,
        raw_prompt: str,
        configured_copywriter_tool: ConfiguredTool,
        configured_image_gen_tool: ConfiguredTool,
        di: DI,
        aspect_ratio: str | None = None,
        output_size: str | None = None,
    ):
        system_prompt = prompt_resolvers.copywriting_image_prompt_upscaler(di.require_invoker_chat_type())
        self.__llm_input = [SystemMessage(system_prompt), HumanMessage(raw_prompt)]
        self.__copywriter = di.chat_langchain_model(configured_copywriter_tool)
        self.__image_gen_tool = configured_image_gen_tool
        self.__aspect_ratio = aspect_ratio
        self.__output_size = output_size
        self.__di = di

    def execute(self) -> Result:
        invoker_chat = self.__di.require_invoker_chat()
        log.d(f"Generating image for chat '{invoker_chat.chat_id}' in aspect ratio {self.__aspect_ratio}")
        self.error = None

        # let's correct/prettify and translate the prompt first
        try:
            log.t("Starting prompt upscaling")
            response = self.__copywriter.invoke(self.__llm_input)
            prompt = parse_ai_message_content(response)
            log.t(f"Finished prompt correction, new size is {len(prompt)} characters")
        except Exception as e:
            self.error = f"Error correcting raw prompt: {str(e)}"
            log.e("Error correcting raw prompt", e)
            return SmartImageGenerator.Result.failed

        # let's generate the image now using the corrected prompt
        try:
            log.t("Starting image generation")
            generator = self.__di.simple_image_generator(
                configured_tool = self.__image_gen_tool, prompt = prompt,
                aspect_ratio = self.__aspect_ratio, output_size = self.__output_size,
            )
            image_url = generator.execute()
            if generator.error:
                self.error = f"Image generator failure: {generator.error}"
                log.e("Image generator failure", generator.error)
                return SmartImageGenerator.Result.failed
            if not image_url:
                self.error = "Image generator failure (no image URL found)"
                log.e(self.error)
                return SmartImageGenerator.Result.failed
        except Exception as e:
            self.error = f"Error generating image: {str(e)}"
            log.e("Error generating image", e)
            return SmartImageGenerator.Result.failed

        # let's send the image to the chat
        try:
            log.t("Starting image sending")
            self.__di.platform_bot_sdk().smart_send_photo(
                media_mode = invoker_chat.media_mode,
                chat_id = int(invoker_chat.external_id or "-1"),
                photo_url = image_url,
                thumbnail = image_url,
            )
        except Exception as e:
            self.error = f"Error sending image: {str(e)}"
            log.e("Error sending image", e)
            return SmartImageGenerator.Result.failed

        log.i("Image generated and sent successfully")
        return SmartImageGenerator.Result.success
