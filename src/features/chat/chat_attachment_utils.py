from di.di import DI
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from util.error_codes import ATTACHMENT_NOT_FOUND, MALFORMED_ATTACHMENT_ID, MISSING_ATTACHMENT_IDS
from util.errors import NotFoundError, ValidationError


def resolve_all_attachments(
    attachment_ids: list[str] | None,
    urls: list[str] | None,
    di: DI,
) -> list[ChatMessageAttachment]:
    if not attachment_ids and not urls:
        raise ValidationError("Malformed LLM Input Error: No attachment IDs provided. You may retry only once!", MISSING_ATTACHMENT_IDS)  # noqa: E501
    return resolve_local_attachments(attachment_ids or [], di) + resolve_remote_attachments(urls or [], di)


def resolve_remote_attachments(urls: list[str], di: DI) -> list[ChatMessageAttachment]:
    return [di.url_attachment_resolver(url).execute() for url in urls]


def resolve_local_attachments(attachment_ids: list[str], di: DI) -> list[ChatMessageAttachment]:
    stale: list[ChatMessageAttachment] = []
    for attachment_id in attachment_ids:
        if not attachment_id:
            raise ValidationError("Malformed LLM Input Error: Attachment ID cannot be empty. You may retry only once!", MALFORMED_ATTACHMENT_ID)  # noqa: E501
        attachment = di.chat_message_attachment_repo.get(attachment_id)
        if not attachment:
            raise NotFoundError(f"Malformed LLM Input Error: Attachment '{attachment_id}' not found in DB. You may retry only once!", ATTACHMENT_NOT_FOUND)  # noqa: E501
        stale.append(attachment)
    return di.platform_bot_sdk().refresh_attachment_instances(stale)
