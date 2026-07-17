from dataclasses import replace
from uuid import UUID

from db.model.chat_attachment import ChatAttachmentDB
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.chat_attachment_remote_data import ChatAttachmentRemoteData
from util.functions import generate_deterministic_short_uuid


def domain(db_model: ChatAttachmentDB | None) -> ChatAttachment | None:
    if db_model is None:
        return None

    return ChatAttachment(
        id = db_model.id,
        external_id = db_model.external_id,
        uploader_user_id = db_model.uploader_user_id,
        created_at = db_model.created_at,
        chat_id = db_model.chat_id,
        message_id = db_model.message_id,
        size = db_model.size,
        last_url = db_model.last_url,
        extension = db_model.extension,
        mime_type = db_model.mime_type,
    )


def db(domain_model: ChatAttachment | None) -> ChatAttachmentDB | None:
    if domain_model is None:
        return None

    return ChatAttachmentDB(
        id = domain_model.id,
        external_id = domain_model.external_id,
        uploader_user_id = domain_model.uploader_user_id,
        created_at = domain_model.created_at,
        chat_id = domain_model.chat_id,
        message_id = domain_model.message_id,
        size = domain_model.size,
        last_url = domain_model.last_url,
        extension = domain_model.extension,
        mime_type = domain_model.mime_type,
    )


def apply_to_db_model(
    domain_model: ChatAttachment,
    db_model: ChatAttachmentDB,
) -> None:
    db_model.external_id = domain_model.external_id
    db_model.chat_id = domain_model.chat_id
    db_model.message_id = domain_model.message_id
    db_model.size = domain_model.size
    db_model.last_url = domain_model.last_url
    db_model.extension = domain_model.extension
    db_model.mime_type = domain_model.mime_type


def from_remote_data(
    remote_data: ChatAttachmentRemoteData,
    chat_id: UUID,
    uploader_user_id: UUID,
) -> ChatAttachment:
    return ChatAttachment(
        id = generate_deterministic_short_uuid(remote_data.external_id),
        external_id = remote_data.external_id,
        uploader_user_id = uploader_user_id,
        chat_id = chat_id,
        message_id = remote_data.message_id,
        size = remote_data.size,
        last_url = remote_data.last_url,
        extension = remote_data.extension,
        mime_type = remote_data.mime_type,
    )


def apply_remote_data(
    attachment: ChatAttachment,
    remote_data: ChatAttachmentRemoteData,
) -> ChatAttachment:
    return replace(
        attachment,
        external_id = remote_data.external_id,
        message_id = remote_data.message_id,
        size = remote_data.size or attachment.size,
        last_url = remote_data.last_url or attachment.last_url,
        extension = remote_data.extension or attachment.extension,
        mime_type = remote_data.mime_type or attachment.mime_type,
    )
