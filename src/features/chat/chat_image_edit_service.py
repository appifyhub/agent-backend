from enum import Enum

from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.chat_attachment_utils import resolve_all_attachments
from features.external_tools.intelligence_presets import default_tool_for
from features.images.image_editor import ImageEditor
from util import log

URLList = list[str | None]
ErrorList = list[str | None]


class ChatImageEditService:

    class Result(Enum):
        success = "success"
        failed = "failed"
        partial = "partial"

    __attachments: list[ChatMessageAttachment]
    __operation_guidance: str | None
    __aspect_ratio: str | None
    __output_size: str | None
    __di: DI

    def __init__(
        self,
        attachment_ids: list[str] | None,
        urls: list[str] | None,
        operation_guidance: str | None,
        aspect_ratio: str | None,
        output_size: str | None,
        di: DI,
    ):
        self.__di = di
        self.__attachments = resolve_all_attachments(attachment_ids, urls, self.__di)
        self.__operation_guidance = operation_guidance
        self.__aspect_ratio = aspect_ratio
        self.__output_size = output_size

    def __edit_image(self) -> tuple[Result, URLList, ErrorList]:
        log.t(f"Editing {len(self.__attachments)} images in aspect ratio {self.__aspect_ratio}")

        # Collect valid attachments; track missing URLs as partial failures
        image_urls: list[str] = []
        mime_types: list[str | None] = []
        skip_errors: list[str | None] = []
        for attachment in self.__attachments:
            if not attachment.last_url:
                message = f"Attachment '{attachment.id}' has no URL, skipping"
                log.w(message)
                skip_errors.append(message)
            else:
                image_urls.append(attachment.last_url)
                mime_types.append(attachment.mime_type)
                skip_errors.append(None)

        if not image_urls:
            return ChatImageEditService.Result.failed, [None], ["No valid attachment URLs found"]

        try:
            configured_tool = self.__di.tool_choice_resolver.require_tool(
                ImageEditor.TOOL_TYPE, default_tool_for(ImageEditor.TOOL_TYPE),
            )
            editor = self.__di.image_editor(
                image_urls = image_urls,
                configured_tool = configured_tool,
                prompt = self.__operation_guidance or "<empty>",
                input_mime_types = mime_types,
                aspect_ratio = self.__aspect_ratio,
                output_size = self.__output_size,
            )
            editing_result = editor.execute()
            if editor.error:
                log.w("Error editing images", editor.error)
                return ChatImageEditService.Result.failed, [None], [editor.error]
            if not editing_result:
                return ChatImageEditService.Result.failed, [None], ["Failed to edit images"]
            log.t("Images edited successfully")
            had_skips = any(e is not None for e in skip_errors)
            result = ChatImageEditService.Result.partial if had_skips else ChatImageEditService.Result.success
            return result, [editing_result], [None]
        except Exception as e:
            log.w("Failed to edit images", e)
            return ChatImageEditService.Result.failed, [None], [str(e)]

    def execute(self) -> tuple[Result, list[dict[str, str | None]]]:
        invoker_chat = self.__di.require_invoker_chat()
        log.t(f"Editing images for chat '{invoker_chat.chat_id}'")

        result, urls, errors = self.__edit_image()
        urls = self.__clean_urls(urls)
        output_editing_urls: list[dict[str, str | None]] = []
        for image_url, error in zip(urls, errors):
            if image_url is None:
                output_editing_urls.append({"url": None, "error": error})
                continue
            external_id = str(invoker_chat.external_id)
            log.t(f"Sending edited image to chat '{external_id}': {image_url}")
            self.__di.platform_bot_sdk().smart_send_photo(
                media_mode = invoker_chat.media_mode,
                chat_id = external_id,
                photo_url = image_url,
                thumbnail = image_url,
            )
            log.t("Image edited and sent successfully")
            output_editing_urls.append({"url": image_url, "error": None, "status": "delivered"})
        return result, output_editing_urls

    @staticmethod  # why? because python has no real types
    def __clean_urls(urls: list) -> URLList:
        result: list = []
        for url in urls:
            if isinstance(url, list):
                if url and isinstance(url[0], str):
                    result.append(url[0])
                continue
            elif isinstance(url, str):
                result.append(url)
            elif url is not None:
                result.append(str(url))
            else:
                result.append(None)
            continue
        return result
