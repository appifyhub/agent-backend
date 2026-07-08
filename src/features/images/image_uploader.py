import base64
import binascii
import re

from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from util import log
from util.error_codes import FILE_UPLOAD_FAILED, INVALID_IMAGE_FORMAT, MISSING_CONTENT, MISSING_IMAGE_INPUTS
from util.errors import ExternalServiceError, ValidationError


class ImageUploader:

    __di: DI
    __content: bytes
    __name: str | None

    def __init__(
        self,
        di: DI,
        binary_image: bytes | None = None,
        base64_image: str | None = None,
        expiration_s: int | None = None,
        name: str | None = None,
    ):
        self.__di = di
        if binary_image is None and base64_image is None:
            raise ValidationError("Either binary_image or base64_image must be provided", MISSING_IMAGE_INPUTS)
        if binary_image is not None:
            self.__content = binary_image
        else:
            base64_image = re.sub(r"^data:image/[^;]+;base64,", "", base64_image or "")
            try:
                self.__content = base64.b64decode(base64_image)
            except binascii.Error as e:
                raise ValidationError("Invalid base64 image input", INVALID_IMAGE_FORMAT) from e
        if not self.__content:
            raise ValidationError("Image content must be provided", MISSING_CONTENT)
        self.__name = name
        image_size_kb = len(self.__content) / 1024
        log.t(f"Ready to upload image! Size: {image_size_kb:.2f} KB")

    def execute(self) -> str:
        try:
            log.t("Uploading image to attachment storage...")
            chat = self.__di.require_invoker_chat()
            attachment: ChatMessageAttachment = self.__di.chat_message_attachment_service.save(
                ChatMessageAttachment(
                    chat_id = chat.chat_id,
                    uploader_user_id = self.__di.invoker.id,
                ),
                self.__content,
                remote_url = self.__name,
            )
            if not attachment.last_url:
                raise ExternalServiceError("Image upload failed: No image URL returned", FILE_UPLOAD_FAILED)
            public_url = self.__di.chat_message_attachment_service.create_public_url(attachment)
            log.t(f"Image uploaded successfully as attachment '{attachment.id}'")
            return public_url.url
        except ExternalServiceError:
            raise  # don't re-wrap intentional errors in the generic handler below
        except Exception as e:
            log.w("Image upload failed!", e)
            raise ExternalServiceError("Image upload failed", FILE_UPLOAD_FAILED) from e
