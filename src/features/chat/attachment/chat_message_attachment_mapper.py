from dataclasses import replace
from uuid import UUID

from db.model.chat_message_attachment import ChatMessageAttachmentDB
from features.chat.attachment.chat_message_attachment import ChatMessageAttachment
from features.chat.attachment.chat_message_attachment_remote_data import ChatMessageAttachmentRemoteData
from util.functions import generate_deterministic_short_uuid


def domain(db_model: ChatMessageAttachmentDB | None) -> ChatMessageAttachment | None:
    if db_model is None:
        return None

    return ChatMessageAttachment(
        id = db_model.id,
        external_id = db_model.external_id,
        chat_id = db_model.chat_id,
        message_id = db_model.message_id,
        size = db_model.size,
        last_url = db_model.last_url,
        last_url_until = db_model.last_url_until,
        extension = db_model.extension,
        mime_type = db_model.mime_type,
    )


def db(domain_model: ChatMessageAttachment | None) -> ChatMessageAttachmentDB | None:
    if domain_model is None:
        return None

    return ChatMessageAttachmentDB(
        id = domain_model.id,
        external_id = domain_model.external_id,
        chat_id = domain_model.chat_id,
        message_id = domain_model.message_id,
        size = domain_model.size,
        last_url = domain_model.last_url,
        last_url_until = domain_model.last_url_until,
        extension = domain_model.extension,
        mime_type = domain_model.mime_type,
    )


def from_remote_data(
    remote_data: ChatMessageAttachmentRemoteData,
    chat_id: UUID,
) -> ChatMessageAttachment:
    return ChatMessageAttachment(
        id = id_from_remote_data(remote_data),
        external_id = remote_data.external_id,
        chat_id = chat_id,
        message_id = remote_data.message_id,
        size = remote_data.size,
        last_url = remote_data.last_url,
        last_url_until = remote_data.last_url_until,
        extension = remote_data.extension,
        mime_type = remote_data.mime_type,
    )


def id_from_remote_data(remote_data: ChatMessageAttachmentRemoteData) -> str:
    return generate_deterministic_short_uuid(remote_data.external_id)


def apply_remote_data(
    attachment: ChatMessageAttachment,
    remote_data: ChatMessageAttachmentRemoteData,
) -> ChatMessageAttachment:
    return replace(
        attachment,
        external_id = remote_data.external_id,
        message_id = remote_data.message_id,
        size = remote_data.size or attachment.size,
        last_url = remote_data.last_url or attachment.last_url,
        last_url_until = remote_data.last_url_until or attachment.last_url_until,
        extension = remote_data.extension or attachment.extension,
        mime_type = remote_data.mime_type or attachment.mime_type,
    )
