from dataclasses import replace

from db.model.chat_config import ChatConfigDB
from features.chat.config.chat_config import ChatConfig
from features.chat.config.chat_config_remote_data import ChatConfigRemoteData


def domain(db_model: ChatConfigDB | None) -> ChatConfig | None:
    if db_model is None:
        return None

    return ChatConfig(
        chat_id = db_model.chat_id,
        external_id = db_model.external_id,
        language_iso_code = db_model.language_iso_code,
        language_name = db_model.language_name,
        title = db_model.title,
        is_private = db_model.is_private,
        reply_chance_percent = db_model.reply_chance_percent,
        release_notifications = db_model.release_notifications,
        media_mode = db_model.media_mode,
        chat_type = db_model.chat_type,
    )


def db(domain_model: ChatConfig | None) -> ChatConfigDB | None:
    if domain_model is None:
        return None

    return ChatConfigDB(
        chat_id = domain_model.chat_id,
        external_id = domain_model.external_id,
        language_iso_code = domain_model.language_iso_code,
        language_name = domain_model.language_name,
        title = domain_model.title,
        is_private = domain_model.is_private,
        reply_chance_percent = domain_model.reply_chance_percent,
        release_notifications = domain_model.release_notifications,
        media_mode = domain_model.media_mode,
        chat_type = domain_model.chat_type,
    )


def apply_to_db_model(
    domain_model: ChatConfig,
    db_model: ChatConfigDB,
) -> None:
    db_model.external_id = domain_model.external_id
    db_model.language_iso_code = domain_model.language_iso_code
    db_model.language_name = domain_model.language_name
    db_model.title = domain_model.title
    db_model.is_private = domain_model.is_private
    db_model.reply_chance_percent = domain_model.reply_chance_percent
    db_model.release_notifications = domain_model.release_notifications
    db_model.media_mode = domain_model.media_mode
    db_model.chat_type = domain_model.chat_type


def from_remote_data(remote_data: ChatConfigRemoteData) -> ChatConfig:
    is_private = remote_data.is_private if remote_data.is_private is not None else True
    return ChatConfig(
        external_id = remote_data.external_id,
        language_iso_code = remote_data.language_iso_code,
        title = remote_data.title,
        is_private = is_private,
        reply_chance_percent = 100,
        release_notifications = (
            ChatConfigDB.ReleaseNotifications.major
            if is_private
            else ChatConfigDB.ReleaseNotifications.none
        ),
        media_mode = ChatConfigDB.MediaMode.photo,
        chat_type = remote_data.chat_type,
    )


def apply_remote_data(
    chat_config: ChatConfig,
    remote_data: ChatConfigRemoteData,
) -> ChatConfig:
    overrides = {}
    if remote_data.title is not None:
        overrides["title"] = remote_data.title
    if remote_data.is_private is not None:
        overrides["is_private"] = remote_data.is_private
    return replace(chat_config, **overrides)
