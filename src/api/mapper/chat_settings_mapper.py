from api.model.chat_config_response import ChatConfigResponse
from api.model.chat_settings_response import ChatSettingsResponse
from api.model.user_chat_config_response import UserChatConfigResponse
from features.chat.config.chat_config import ChatConfig
from features.chat.membership.chat_membership import ChatMembership


def domain_to_api(chat: ChatConfig, membership: ChatMembership, is_own: bool) -> ChatSettingsResponse:
    return ChatSettingsResponse(
        chat_config = ChatConfigResponse(
            chat_id = chat.chat_id.hex,
            title = chat.title,
            platform = chat.chat_type.value,
            language_name = chat.language_name,
            language_iso_code = chat.language_iso_code,
            reply_chance_percent = chat.reply_chance_percent,
            release_notifications = chat.release_notifications.value,
            media_mode = chat.media_mode.value,
            is_private = chat.is_private,
            is_own = is_own,
            is_admin = membership.is_admin,
        ),
        user_chat_config = UserChatConfigResponse(
            use_about_me = membership.use_about_me,
            use_custom_prompt = membership.use_custom_prompt,
            max_output_tokens = membership.max_output_tokens,
            max_chat_history_depth = membership.max_chat_history_depth,
            max_iterations = membership.max_iterations,
        ),
    )
