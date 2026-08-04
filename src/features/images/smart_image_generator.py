from dataclasses import replace
from threading import BoundedSemaphore, Thread
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from db.model.chat_config import ChatConfigDB
from db.sql import get_detached_session
from di.di import DI
from features.announcements.sys_announcements_service import SysAnnouncementsService
from features.chat.attachment.chat_attachment import ChatAttachment
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.intelligence_presets import default_tool_for
from features.images.image_api_utils import (
    UnifiedImageParameters,
    map_to_model_parameters,
)
from features.images.image_size_utils import calculate_image_size_category
from features.integrations import prompt_resolvers
from util import log
from util.error_codes import IMAGE_GENERATION_FAILED, MISSING_CONTENT
from util.errors import ExternalServiceError, ServiceError, ValidationError
from util.functions import parse_ai_message_content

IMAGE_GENERATION_SLOTS = BoundedSemaphore(16)


class SmartImageGenerator:

    COPYWRITER_TOOL_TYPE: ToolType = ToolType.copywriting
    IMAGE_GEN_TOOL_TYPE: ToolType = ToolType.images_gen

    __raw_prompt: str
    __all_attachments: list[ChatAttachment]
    __copywriter: BaseChatModel
    __image_gen_tool: ConfiguredTool
    __aspect_ratio: str | None
    __output_size: str | None
    __di: DI

    def __init__(
        self,
        raw_prompt: str,
        attachment_ids: list[str],
        urls: list[str],
        configured_copywriter_tool: ConfiguredTool,
        configured_image_gen_tool: ConfiguredTool,
        di: DI,
        aspect_ratio: str | None = None,
        output_size: str | None = None,
    ):
        self.__copywriter = di.chat_langchain_model(configured_copywriter_tool)
        self.__image_gen_tool = configured_image_gen_tool
        self.__aspect_ratio = aspect_ratio
        self.__output_size = output_size
        self.__di = di
        self.__raw_prompt = raw_prompt.strip()
        if not self.__raw_prompt:
            raise ValidationError("Image prompt cannot be empty", MISSING_CONTENT)
        self.__all_attachments = []
        if attachment_ids or urls:
            self.__all_attachments = di.chat_attachment_service.resolve_image_attachments(attachment_ids, urls)

    def execute(self) -> dict[str, str | int]:
        # first, we prepare the model parameters
        max_user_images = self.__image_gen_tool.definition.max_input_images
        attachments = self.__all_attachments[:max_user_images]
        attachment_urls = [
            self.__di.chat_attachment_service.create_public_url(attachment).url
            for attachment in attachments
        ]
        input_image_sizes = self.__resolve_input_image_sizes(attachments)
        parameters = map_to_model_parameters(
            tool = self.__image_gen_tool.definition,
            prompt = self.__raw_prompt,
            aspect_ratio = self.__aspect_ratio,
            output_size = self.__output_size,
            input_urls = attachment_urls,
        )
        output_image_sizes = [parameters.size]

        # then, we check if the cost will allow us to proceed with the generation
        self.__di.spending_service.validate_pre_flight(
            self.__image_gen_tool,
            input_image_sizes = input_image_sizes,
            output_image_sizes = output_image_sizes,
        )

        # we also need to upscale the raw prompt to ensure best results
        log.t("Starting image prompt upscaling")
        invoker_chat = self.__di.require_invoker_chat()
        system_prompt = prompt_resolvers.copywriting_image_prompt_upscaler(invoker_chat.chat_type, len(attachments))
        response = self.__copywriter.invoke([SystemMessage(system_prompt), HumanMessage(self.__raw_prompt)])
        upscaled_prompt = parse_ai_message_content(response)
        parameters = replace(parameters, prompt = upscaled_prompt)
        log.t(f"Finished image prompt correction, new size is {len(upscaled_prompt)} characters")

        # and finally, we launch an asynchronous worker to generate the image
        if not IMAGE_GENERATION_SLOTS.acquire(blocking = False):
            raise ExternalServiceError("Image generation service is busy. Please try again later.", IMAGE_GENERATION_FAILED)
        try:
            worker = Thread(
                name = f"image-generator-{invoker_chat.chat_id.hex[:8]}",
                target = _run_image_worker,
                kwargs = {
                    "configured_image_gen_tool": self.__image_gen_tool,
                    "parameters": parameters,
                    "input_attachments": attachments,
                    "input_image_urls": attachment_urls,
                    "input_image_sizes": input_image_sizes,
                    "output_image_sizes": output_image_sizes,
                    "invoker_id": self.__di.invoker.id,
                    "invoker_chat_id": invoker_chat.chat_id,
                    "external_chat_id": str(invoker_chat.external_id or "-1"),
                    "media_mode": invoker_chat.media_mode,
                },
                daemon = True,
            )
            worker.start()
        except Exception as e:
            IMAGE_GENERATION_SLOTS.release()
            raise ExternalServiceError("Could not start image generation", IMAGE_GENERATION_FAILED) from e

        return {
            "status": "started",
            "description": "Image generation has started. You will receive a notification when the image is ready.",
            "used_reference_images": len(attachments),
            "ignored_reference_images": len(self.__all_attachments) - len(attachments),
        }

    def __resolve_input_image_sizes(self, attachments: list[ChatAttachment]) -> list[str] | None:
        input_image_sizes = []
        for attachment in attachments:
            try:
                with self.__di.attachment_storage.open(attachment) as stream:
                    input_image_sizes.append(calculate_image_size_category(file_contents = stream))
            except Exception as e:
                log.e(f"Failed to calculate input image size, will proceed without it: {e}")
        return input_image_sizes or None


def _run_image_worker(
    configured_image_gen_tool: ConfiguredTool,
    parameters: UnifiedImageParameters,
    input_attachments: list[ChatAttachment],
    input_image_urls: list[str],
    input_image_sizes: list[str] | None,
    output_image_sizes: list[str] | None,
    invoker_id: UUID,
    invoker_chat_id: UUID,
    external_chat_id: str,
    media_mode: ChatConfigDB.MediaMode,
) -> None:
    try:
        with get_detached_session() as db:
            worker_di = DI(db, invoker_id.hex, invoker_chat_id.hex)
            generator = worker_di.simple_image_generator(
                configured_tool = configured_image_gen_tool,
                parameters = parameters,
                input_attachments = input_attachments,
                input_image_urls = input_image_urls,
                input_image_sizes = input_image_sizes,
                output_image_sizes = output_image_sizes,
            )
            image_url = generator.execute()
            if generator.error:
                raise ExternalServiceError(f"Image generator failure: {generator.error}", IMAGE_GENERATION_FAILED)
            if not image_url:
                raise ExternalServiceError("Image generator failure (no image URL found)", IMAGE_GENERATION_FAILED)
            log.t(f"Image generated successfully for chat '{invoker_chat_id.hex}'")

            worker_di.rollback_db_session()
            platform_sdk = worker_di.platform_bot_sdk()
            platform_sdk.set_chat_action(chat_id = external_chat_id, action = "upload_photo")
            platform_sdk.smart_send_photo(
                media_mode = media_mode,
                chat_id = external_chat_id,
                photo_url = image_url,
                thumbnail = image_url,
            )
            log.i(f"Image generated and sent successfully to chat '{invoker_chat_id.hex}'")
    except Exception as e:
        log.e(f"Background image generation failed for chat '{invoker_chat_id.hex}'", e)

        failure = e if isinstance(e, ServiceError) \
                  else ExternalServiceError(f"Unexpected image generation or delivery failure: {e}", IMAGE_GENERATION_FAILED)
        try:
            with get_detached_session() as db:
                notification_di = DI(db, invoker_id.hex, invoker_chat_id.hex)
                configured_copywriter_tool = notification_di.tool_choice_resolver.require_tool(
                    purpose = SysAnnouncementsService.TOOL_TYPE,
                    default_tool = default_tool_for(SysAnnouncementsService.TOOL_TYPE),
                )
                raw_message = f"Your image could not be generated or delivered.\n\n{str(failure)}"
                _, notification = notification_di.sys_announcements_service(
                    raw_information = raw_message,
                    target_chat = notification_di.require_invoker_chat(),
                    configured_tool = configured_copywriter_tool,
                ).execute()
                notification_di.platform_bot_sdk().send_text_message(
                    chat_id = external_chat_id,
                    text = str(notification.content),
                )
        except Exception as notification_error:
            log.e(f"Could not notify chat '{invoker_chat_id.hex}' of image generation failure", notification_error)
    finally:
        IMAGE_GENERATION_SLOTS.release()
