from dataclasses import replace
from uuid import UUID

from db.model.chat_message import ChatMessageDB
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_remote_data import ChatMessageRemoteData


def domain(db_model: ChatMessageDB | None) -> ChatMessage | None:
    if db_model is None:
        return None

    return ChatMessage(
        chat_id = db_model.chat_id,
        message_id = db_model.message_id,
        author_id = db_model.author_id,
        sent_at = db_model.sent_at,
        text = db_model.text,
        is_temporary = db_model.is_temporary,
    )


def db(domain_model: ChatMessage | None) -> ChatMessageDB | None:
    if domain_model is None:
        return None

    return ChatMessageDB(
        chat_id = domain_model.chat_id,
        message_id = domain_model.message_id,
        author_id = domain_model.author_id,
        sent_at = domain_model.sent_at,
        text = domain_model.text,
        is_temporary = domain_model.is_temporary,
    )


def apply_to_db_model(
    domain_model: ChatMessage,
    db_model: ChatMessageDB,
) -> None:
    db_model.author_id = domain_model.author_id
    db_model.sent_at = domain_model.sent_at
    db_model.text = domain_model.text
    db_model.is_temporary = domain_model.is_temporary


def from_remote_data(
    remote_data: ChatMessageRemoteData,
    chat_id: UUID,
    author_id: UUID | None,
) -> ChatMessage:
    return ChatMessage(
        chat_id = chat_id,
        message_id = remote_data.message_id,
        author_id = author_id,
        sent_at = remote_data.sent_at,
        text = remote_data.text,
    )


def apply_remote_data(
    message: ChatMessage,
    remote_data: ChatMessageRemoteData,
    author_id: UUID | None,
) -> ChatMessage:
    return replace(
        message,
        author_id = author_id if author_id is not None else message.author_id,
        sent_at = remote_data.sent_at,
        text = remote_data.text,
    )
