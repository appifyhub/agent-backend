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
from features.integrations import prompt_resolvers
from features.videos.video_api_utils import UnifiedVideoParameters, map_to_model_parameters
from util import log
from util.error_codes import MISSING_CONTENT, VIDEO_GENERATION_FAILED
from util.errors import ExternalServiceError, ServiceError, ValidationError
from util.functions import parse_ai_message_content

VIDEO_GENERATION_SLOTS = BoundedSemaphore(16)


class SmartVideoGenerator:

    COPYWRITER_TOOL_TYPE: ToolType = ToolType.copywriting
    VIDEO_GEN_TOOL_TYPE: ToolType = ToolType.videos_gen

    __raw_prompt: str
    __all_attachments: list[ChatAttachment]
    __duration: str | None
    __aspect_ratio: str | None
    __output_size: str | None
    __copywriter: BaseChatModel
    __video_gen_tool: ConfiguredTool
    __di: DI

    def __init__(
        self,
        raw_prompt: str,
        attachment_ids: list[str],
        urls: list[str],
        configured_copywriter_tool: ConfiguredTool,
        configured_video_gen_tool: ConfiguredTool,
        di: DI,
        duration: str | None = None,
        aspect_ratio: str | None = None,
        output_size: str | None = None,
    ):
        self.__raw_prompt = raw_prompt.strip()
        if not self.__raw_prompt:
            raise ValidationError("Video prompt cannot be empty", MISSING_CONTENT)
        self.__copywriter = di.chat_langchain_model(configured_copywriter_tool)
        self.__video_gen_tool = configured_video_gen_tool
        self.__duration = duration
        self.__aspect_ratio = aspect_ratio
        self.__output_size = output_size
        self.__di = di
        self.__all_attachments = []
        if attachment_ids or urls:
            self.__all_attachments = di.chat_attachment_service.resolve_image_attachments(attachment_ids, urls)

    def execute(self) -> dict[str, str | int]:
        # first, we prepare the model parameters
        max_user_images = self.__video_gen_tool.definition.max_input_images
        attachments = self.__all_attachments[:max_user_images]  # we can only keep a limited number
        attachment_urls = [self.__di.chat_attachment_service.create_public_url(attachment).url for attachment in attachments]
        parameters = map_to_model_parameters(
            tool = self.__video_gen_tool.definition,
            prompt = self.__raw_prompt,
            duration = self.__duration,
            aspect_ratio = self.__aspect_ratio,
            output_size = self.__output_size,
            reference_image_urls = attachment_urls,
        )

        # then, we check if the cost will allow us to proceed with the generation
        self.__di.spending_service.validate_pre_flight(
            self.__video_gen_tool,
            output_video_size = parameters.size,
            output_video_duration_seconds = parameters.duration,
        )

        # we also need to upscale the raw prompt to ensure best results
        log.t("Starting video prompt upscaling")
        system_prompt = prompt_resolvers.copywriting_video_screenwriter(self.__di.require_invoker_chat_type(), len(attachments))  # noqa: E501
        response = self.__copywriter.invoke([SystemMessage(system_prompt), HumanMessage(self.__raw_prompt)])
        upscaled_prompt = parse_ai_message_content(response)
        parameters = replace(parameters, prompt = upscaled_prompt)
        log.t(f"Finished video prompt correction, new size is {len(upscaled_prompt)} characters")

        # and finally, we launch an asynchronous worker to generate the video
        if not VIDEO_GENERATION_SLOTS.acquire(blocking = False):
            raise ExternalServiceError("Video generation service is busy. Please try again later.", VIDEO_GENERATION_FAILED)
        try:
            invoker_chat = self.__di.require_invoker_chat()
            worker = Thread(
                name = f"video-generator-{invoker_chat.chat_id.hex[:8]}",
                target = _run_video_worker,
                kwargs = {
                    "configured_video_gen_tool": self.__video_gen_tool,
                    "parameters": parameters,
                    "invoker_id": self.__di.invoker.id,
                    "invoker_chat_id": invoker_chat.chat_id,
                    "external_chat_id": str(invoker_chat.external_id or "-1"),
                    "media_mode": invoker_chat.media_mode,
                },
                daemon = True,
            )
            worker.start()
        except Exception as e:
            VIDEO_GENERATION_SLOTS.release()
            raise ExternalServiceError("Could not start video generation", VIDEO_GENERATION_FAILED) from e

        return {
            "status": "started",
            "description": "Video generation has started. You will receive a notification when the video is ready.",
            "used_reference_images": len(attachments),
            "ignored_reference_images": len(self.__all_attachments) - len(attachments),
        }


def _run_video_worker(
    configured_video_gen_tool: ConfiguredTool,
    parameters: UnifiedVideoParameters,
    invoker_id: UUID,
    invoker_chat_id: UUID,
    external_chat_id: str,
    media_mode: ChatConfigDB.MediaMode,
) -> None:
    try:
        with get_detached_session() as db:
            worker_di = DI(db, invoker_id.hex, invoker_chat_id.hex)

            # generation releases its preflight transaction before polling, but accounting acquires a new one
            video_url = worker_di.simple_video_generator(configured_video_gen_tool, parameters).execute()
            log.t(f"Video generated successfully for chat '{invoker_chat_id.hex}'")

            # we need to release the DB here because sending video can also block the transaction
            worker_di.rollback_db_session()
            # now that the video is ready, we finally send it back to the user
            worker_di.platform_bot_sdk().smart_send_video(media_mode = media_mode, chat_id = external_chat_id, video_url = video_url)  # noqa: E501
            log.i(f"Video generated and sent successfully to chat '{invoker_chat_id.hex}'")
    except Exception as e:
        log.e(f"Background video generation failed for chat '{invoker_chat_id.hex}'", e)

        failure = e if isinstance(e, ServiceError) \
                  else ExternalServiceError(f"Unexpected video generation or delivery failure: {e}", VIDEO_GENERATION_FAILED)
        try:
            # we should notify the user about this failure
            with get_detached_session() as db:
                notification_di = DI(db, invoker_id.hex, invoker_chat_id.hex)
                configured_copywriter_tool = notification_di.tool_choice_resolver.require_tool(
                    purpose = SysAnnouncementsService.TOOL_TYPE,
                    default_tool = default_tool_for(SysAnnouncementsService.TOOL_TYPE),
                )
                raw_message = f"Your video could not be generated or delivered.\n\n{str(failure)}"
                _, notification = notification_di.sys_announcements_service(
                    raw_information = raw_message,
                    target_chat = notification_di.require_invoker_chat(),
                    configured_tool = configured_copywriter_tool,
                ).execute()
                notification_di.platform_bot_sdk().send_text_message(chat_id = external_chat_id, text = str(notification.content))
        except Exception as notification_error:
            log.e(f"Could not notify chat '{invoker_chat_id.hex}' of video generation failure", notification_error)
    finally:
        VIDEO_GENERATION_SLOTS.release()
