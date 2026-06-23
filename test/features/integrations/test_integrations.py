from datetime import date, datetime, timedelta
from unittest import TestCase
from unittest.mock import Mock, create_autospec
from uuid import UUID

from pydantic import SecretStr

from db.crud.user import UserCRUD
from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.user import User, UserSave
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.config.chat_config_repo import ChatConfigRepository
from features.chat.message.chat_message import ChatMessage
from features.chat.message.chat_message_repo import ChatMessageRepository
from features.integrations.integrations import (
    WHATSAPP_MESSAGING_WINDOW_HOURS,
    format_handle,
    is_own_chat,
    is_reaction_response,
    is_the_agent,
    lookup_user_by_handle,
    resolve_agent_user,
    resolve_allowed_reactions,
    resolve_any_external_handle,
    resolve_best_notification_chat,
    resolve_external_handle,
    resolve_external_id,
    resolve_private_chat_id,
    resolve_user_link,
    resolve_user_to_save,
)
from features.integrations.platform_bot_sdk import PlatformBotSDK
from util.config import config


class IntegrationsTest(TestCase):

    def test_resolve_agent_user_telegram(self):
        agent = resolve_agent_user(ChatConfigDB.ChatType.telegram)
        self.assertEqual(agent.telegram_username, config.telegram_bot_username)
        self.assertEqual(agent.telegram_user_id, config.telegram_bot_id)
        self.assertEqual(agent.full_name, "The Agent")

    def test_resolve_agent_user_background(self):
        agent = resolve_agent_user(ChatConfigDB.ChatType.background)
        self.assertEqual(agent.full_name, config.background_bot_name)
        self.assertIsNone(agent.telegram_username)
        self.assertIsNone(agent.telegram_user_id)

    def test_resolve_agent_user_github(self):
        agent = resolve_agent_user(ChatConfigDB.ChatType.github)
        self.assertEqual(agent.full_name, "The Agent")
        self.assertEqual(agent.telegram_username, config.telegram_bot_username)
        self.assertEqual(agent.telegram_user_id, config.telegram_bot_id)

    def test_resolve_agent_user_whatsapp(self):
        agent = resolve_agent_user(ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(agent.whatsapp_user_id, config.whatsapp_phone_number_id)
        assert agent.whatsapp_phone_number is not None
        self.assertEqual(agent.whatsapp_phone_number.get_secret_value(), config.whatsapp_bot_phone_number)
        self.assertEqual(agent.full_name, "The Agent")

    def test_resolve_allowed_reactions_telegram(self):
        reactions = resolve_allowed_reactions(ChatConfigDB.ChatType.telegram)
        self.assertIn("👍", reactions)

    def test_resolve_allowed_reactions_github_empty(self):
        self.assertEqual(resolve_allowed_reactions(ChatConfigDB.ChatType.github), [])

    def test_is_reaction_response(self):
        self.assertTrue(is_reaction_response(" 👍 ", ChatConfigDB.ChatType.telegram))

    def test_is_reaction_response_rejects_text(self):
        self.assertFalse(is_reaction_response("👍 ok", ChatConfigDB.ChatType.telegram))

    def test_is_reaction_response_rejects_unsupported_chat_type(self):
        self.assertFalse(is_reaction_response("👍", ChatConfigDB.ChatType.github))

    def test_resolve_external_id_telegram_success(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_user_id = 123456789,
        )
        result = resolve_external_id(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "123456789")

    def test_resolve_external_id_telegram_none(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_user_id = None,
        )
        result = resolve_external_id(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_external_id_unsupported_platform(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_user_id = 123456789,
        )
        result = resolve_external_id(user, ChatConfigDB.ChatType.background)
        self.assertIsNone(result)

    def test_resolve_external_id_whatsapp_success(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_user_id = "15551234567",
        )
        result = resolve_external_id(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "15551234567")

    def test_resolve_external_id_whatsapp_none(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_user_id = None,
        )
        result = resolve_external_id(user, ChatConfigDB.ChatType.whatsapp)
        self.assertIsNone(result)

    def test_resolve_external_handle_telegram_success(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "test_user",
        )
        result = resolve_external_handle(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "test_user")

    def test_resolve_external_handle_telegram_none(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = None,
        )
        result = resolve_external_handle(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_external_handle_unsupported_platform(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "test_user",
        )
        result = resolve_external_handle(user, ChatConfigDB.ChatType.github)
        self.assertIsNone(result)

    def test_resolve_external_handle_whatsapp_success(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_phone_number = SecretStr("15551234567"),
        )
        result = resolve_external_handle(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "15551234567")

    def test_resolve_external_handle_whatsapp_none(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_phone_number = None,
        )
        result = resolve_external_handle(user, ChatConfigDB.ChatType.whatsapp)
        self.assertIsNone(result)

    def test_is_the_agent_true(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = config.telegram_bot_username,
            telegram_user_id = config.telegram_bot_id,
        )
        result = is_the_agent(user, ChatConfigDB.ChatType.telegram)
        self.assertTrue(result)

    def test_is_the_agent_false_different_user(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "other_user",
            telegram_user_id = 987654321,
        )
        result = is_the_agent(user, ChatConfigDB.ChatType.telegram)
        self.assertFalse(result)

    def test_is_the_agent_none_user(self):
        result = is_the_agent(None, ChatConfigDB.ChatType.telegram)
        self.assertFalse(result)

    def test_lookup_user_by_handle_telegram_success(self):
        mock_user_crud = Mock(spec = UserCRUD)
        mock_user_db = UserDB(
            id = UUID(int = 1),
            full_name = "Test User",
            telegram_username = "test_user",
            telegram_chat_id = "test_chat",
            telegram_user_id = 123456789,
            connect_key = "INT-TG-KEY1",
            group = UserDB.Group.standard,
            created_at = date.today(),
            credit_balance = 0.0,
        )
        mock_user_crud.get_by_telegram_username.return_value = mock_user_db

        result = lookup_user_by_handle("test_user", ChatConfigDB.ChatType.telegram, mock_user_crud)

        self.assertEqual(result, mock_user_db)
        mock_user_crud.get_by_telegram_username.assert_called_once_with("test_user")

    def test_lookup_user_by_handle_telegram_not_found(self):
        mock_user_crud = Mock(spec = UserCRUD)
        mock_user_crud.get_by_telegram_username.return_value = None

        result = lookup_user_by_handle("nonexistent_user", ChatConfigDB.ChatType.telegram, mock_user_crud)

        self.assertIsNone(result)
        mock_user_crud.get_by_telegram_username.assert_called_once_with("nonexistent_user")

    def test_lookup_user_by_handle_telegram_with_at(self):
        mock_user_crud = Mock(spec = UserCRUD)
        mock_user_db = UserDB(
            id = UUID(int = 1),
            full_name = "Test User",
            telegram_username = "test_user",
            telegram_chat_id = "test_chat",
            telegram_user_id = 123456789,
            connect_key = "INT-TG-KEY2",
            group = UserDB.Group.standard,
            created_at = date.today(),
            credit_balance = 0.0,
        )
        mock_user_crud.get_by_telegram_username.return_value = mock_user_db

        result = lookup_user_by_handle("@test_user", ChatConfigDB.ChatType.telegram, mock_user_crud)

        self.assertEqual(result, mock_user_db)
        mock_user_crud.get_by_telegram_username.assert_called_once_with("test_user")

    def test_lookup_user_by_handle_unsupported_platform(self):
        mock_user_crud = Mock(spec = UserCRUD)

        result = lookup_user_by_handle("test_user", ChatConfigDB.ChatType.background, mock_user_crud)

        self.assertIsNone(result)
        mock_user_crud.get_by_telegram_username.assert_not_called()

    def test_lookup_user_by_handle_whatsapp_success(self):
        mock_user_crud = Mock(spec = UserCRUD)
        mock_user_db = UserDB(
            id = UUID(int = 1),
            full_name = "Test User",
            whatsapp_user_id = "15551234567",
            whatsapp_phone_number = "15551234567",
            connect_key = "INT-WA-KEY1",
            group = UserDB.Group.standard,
            created_at = date.today(),
            credit_balance = 0.0,
        )
        mock_user_crud.get_by_whatsapp_user_id.return_value = mock_user_db

        result = lookup_user_by_handle("+1 (555) 123-4567", ChatConfigDB.ChatType.whatsapp, mock_user_crud)

        self.assertEqual(result, mock_user_db)
        mock_user_crud.get_by_whatsapp_user_id.assert_called_once_with("15551234567")

    def test_lookup_user_by_handle_whatsapp_not_found(self):
        mock_user_crud = Mock(spec = UserCRUD)
        mock_user_crud.get_by_whatsapp_user_id.return_value = None
        mock_user_crud.get_by_whatsapp_phone_number.return_value = None

        result = lookup_user_by_handle("+1 (555) 999-9999", ChatConfigDB.ChatType.whatsapp, mock_user_crud)

        self.assertIsNone(result)
        mock_user_crud.get_by_whatsapp_user_id.assert_called_once_with("15559999999")
        mock_user_crud.get_by_whatsapp_phone_number.assert_called_once_with("15559999999")

    def test_resolve_user_to_save_telegram_success(self):
        result = resolve_user_to_save("test_user", ChatConfigDB.ChatType.telegram)

        assert result is not None
        self.assertIsInstance(result, UserSave)
        self.assertEqual(result.telegram_username, "test_user")
        self.assertIsNone(result.id)
        self.assertIsNone(result.full_name)
        self.assertIsNone(result.telegram_chat_id)
        self.assertIsNone(result.telegram_user_id)
        self.assertEqual(result.group, UserDB.Group.standard)

    def test_resolve_user_to_save_telegram_with_at(self):
        result = resolve_user_to_save("@test_user", ChatConfigDB.ChatType.telegram)

        assert result is not None
        self.assertIsInstance(result, UserSave)
        self.assertEqual(result.telegram_username, "test_user")

    def test_resolve_user_to_save_telegram_with_spaces_and_symbols(self):
        result = resolve_user_to_save("@ test user +", ChatConfigDB.ChatType.telegram)

        assert result is not None
        self.assertIsInstance(result, UserSave)
        self.assertEqual(result.telegram_username, "testuser")

    def test_resolve_user_to_save_unsupported_platform(self):
        result = resolve_user_to_save("test_user", ChatConfigDB.ChatType.background)

        self.assertIsNone(result)

    def test_resolve_user_to_save_whatsapp_success(self):
        result = resolve_user_to_save("+1 (555) 123-4567", ChatConfigDB.ChatType.whatsapp)

        assert result is not None
        self.assertIsInstance(result, UserSave)
        self.assertEqual(result.whatsapp_user_id, "15551234567")
        assert result.whatsapp_phone_number is not None
        self.assertEqual(result.whatsapp_phone_number.get_secret_value(), "15551234567")
        self.assertIsNone(result.id)
        self.assertIsNone(result.full_name)
        self.assertEqual(result.group, UserDB.Group.standard)

    def test_resolve_any_external_handle_telegram_success(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "test_user",
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertEqual(handle, "test_user")
        self.assertEqual(chat_type, ChatConfigDB.ChatType.telegram)

    def test_resolve_any_external_handle_telegram_with_whitespace(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "  test_user  ",
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertEqual(handle, "test_user")  # Should be stripped
        self.assertEqual(chat_type, ChatConfigDB.ChatType.telegram)

    def test_resolve_any_external_handle_telegram_empty_string(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "",
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertIsNone(handle)
        self.assertIsNone(chat_type)

    def test_resolve_any_external_handle_telegram_whitespace_only(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "   ",
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertIsNone(handle)
        self.assertIsNone(chat_type)

    def test_resolve_any_external_handle_no_handles(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = None,
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertIsNone(handle)
        self.assertIsNone(chat_type)

    def test_resolve_any_external_handle_prioritizes_first_available(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "telegram_user",
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertEqual(handle, "telegram_user")
        self.assertEqual(chat_type, ChatConfigDB.ChatType.telegram)

    def test_resolve_any_external_handle_whatsapp_success(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_phone_number = SecretStr("15551234567"),
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertEqual(handle, "15551234567")
        self.assertEqual(chat_type, ChatConfigDB.ChatType.whatsapp)

    def test_resolve_any_external_handle_whatsapp_with_whitespace(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_phone_number = SecretStr("  15551234567  "),
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertEqual(handle, "15551234567")  # Should be stripped
        self.assertEqual(chat_type, ChatConfigDB.ChatType.whatsapp)

    def test_resolve_any_external_handle_whatsapp_empty_string(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_phone_number = SecretStr(""),
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertIsNone(handle)
        self.assertIsNone(chat_type)

    def test_resolve_any_external_handle_telegram_and_whatsapp_prioritizes_telegram(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "telegram_user",
            whatsapp_phone_number = SecretStr("15551234567"),
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertEqual(handle, "telegram_user")  # Telegram should be prioritized
        self.assertEqual(chat_type, ChatConfigDB.ChatType.telegram)

    def test_format_handle_telegram_plain(self):
        result = format_handle("username", ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "@username")

    def test_format_handle_telegram_with_at(self):
        result = format_handle("@username", ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "@username")

    def test_format_handle_telegram_with_plus(self):
        result = format_handle("+username", ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "@username")

    def test_format_handle_telegram_with_hash(self):
        result = format_handle("#username", ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "@username")

    def test_format_handle_telegram_with_spaces(self):
        result = format_handle("  user name  ", ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "@username")

    def test_format_handle_whatsapp_plain(self):
        result = format_handle("15551234567", ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "+15551234567")

    def test_format_handle_whatsapp_with_plus(self):
        result = format_handle("+15551234567", ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "+15551234567")

    def test_format_handle_whatsapp_with_at(self):
        result = format_handle("@15551234567", ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "+15551234567")

    def test_format_handle_github_plain(self):
        result = format_handle("octocat", ChatConfigDB.ChatType.github)
        self.assertEqual(result, "@octocat")

    def test_format_handle_github_with_at(self):
        result = format_handle("@octocat", ChatConfigDB.ChatType.github)
        self.assertEqual(result, "@octocat")

    def test_format_handle_background_plain(self):
        result = format_handle("agent", ChatConfigDB.ChatType.background)
        self.assertEqual(result, "#agent")

    def test_resolve_user_link_telegram_success(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "test_user",
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "[@test_user](https://t.me/test_user)")

    def test_resolve_user_link_telegram_with_at_prefix(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "@test_user",
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "[@test_user](https://t.me/test_user)")

    def test_resolve_user_link_telegram_with_plus_prefix(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "+test_user",
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "[@test_user](https://t.me/test_user)")

    def test_resolve_user_link_telegram_with_slash_prefix(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "/test_user",
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "[@test_user](https://t.me/test_user)")

    def test_resolve_user_link_telegram_empty_username(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "",
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_user_link_telegram_whitespace_only(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "   ",
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_user_link_telegram_none_username(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = None,
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_user_link_github_no_handle(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "test_user",  # GitHub doesn't use telegram_username
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.github)
        self.assertIsNone(result)  # GitHub handle resolution not implemented yet

    def test_resolve_user_link_background_platform(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_username = "test_user",
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.background)
        self.assertIsNone(result)

    def test_resolve_user_link_whatsapp_success(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_phone_number = SecretStr("15551234567"),
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "[15551234567](https://wa.me/15551234567)")

    def test_resolve_user_link_whatsapp_with_plus_prefix(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_phone_number = SecretStr("+15551234567"),
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "[15551234567](https://wa.me/15551234567)")

    def test_resolve_user_link_whatsapp_formatted_phone(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_phone_number = SecretStr("+1 (555) 123-4567"),
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "[15551234567](https://wa.me/15551234567)")

    def test_resolve_user_link_whatsapp_empty_phone_number(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_phone_number = SecretStr(""),
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.whatsapp)
        self.assertIsNone(result)

    def test_resolve_user_link_whatsapp_none_phone_number(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_phone_number = None,
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.whatsapp)
        self.assertIsNone(result)

    def test_resolve_private_chat_id_telegram_success(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_chat_id = "123456789",
        )
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "123456789")

    def test_resolve_private_chat_id_telegram_none(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_chat_id = None,
        )
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_private_chat_id_background_platform(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_chat_id = "123456789",
        )
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.background)
        self.assertIsNone(result)

    def test_resolve_private_chat_id_github_platform(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_chat_id = "123456789",
        )
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.github)
        self.assertIsNone(result)

    def test_resolve_private_chat_id_whatsapp_success(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_user_id = "15551234567",
        )
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "15551234567")

    def test_resolve_private_chat_id_whatsapp_none(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_user_id = None,
        )
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.whatsapp)
        self.assertIsNone(result)

    def test_is_own_chat_whatsapp_success(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_user_id = "15551234567",
        )
        chat_config = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = "15551234567",
            is_private = True,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertTrue(result)

    def test_is_own_chat_whatsapp_different_user(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_user_id = "15551234567",
        )
        chat_config = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = "15559999999",
            is_private = True,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertFalse(result)

    def test_is_own_chat_whatsapp_missing_user_id(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_user_id = None,
        )
        chat_config = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = "15551234567",
            is_private = True,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertFalse(result)

    def test_is_own_chat_whatsapp_missing_external_id(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_user_id = "15551234567",
        )
        chat_config = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = None,
            is_private = True,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertFalse(result)

    def test_is_own_chat_whatsapp_not_private(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_user_id = "15551234567",
        )
        chat_config = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = "15551234567",
            is_private = False,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertFalse(result)

    def test_is_own_chat_whatsapp_phone_number_normalization(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_user_id = "15551234567",
        )
        chat_config = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = "+1 (555) 123-4567",
            is_private = True,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertTrue(result)

    def test_is_own_chat_whatsapp_phone_number_normalization_different(self):
        user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            whatsapp_user_id = "15551234567",
        )
        chat_config = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = "+1 (555) 999-9999",
            is_private = True,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertFalse(result)

    def test_all_mode_sends_both_photo_and_document(self):
        """Test that 'all' mode sends both photo (resized) and document (original)"""
        sdk_mock = create_autospec(PlatformBotSDK, instance = True)
        sdk_mock.send_photo = Mock(return_value = "photo-sent")
        sdk_mock.send_document = Mock(return_value = "document-sent")
        # Call the actual smart_send_photo method
        result = PlatformBotSDK.smart_send_photo(
            sdk_mock,
            media_mode = ChatConfigDB.MediaMode.all,
            chat_id = 1,
            photo_url = "http://example.com/img.png",
            caption = "test",
        )
        # Verify photo was sent
        sdk_mock.send_photo.assert_called_once_with(1, "http://example.com/img.png", "test")
        # Verify document was sent with original URL
        sdk_mock.send_document.assert_called_once_with(1, "http://example.com/img.png", "test", thumbnail = None)
        # Return value should be from document (last message sent)
        self.assertEqual(result, "document-sent")

    def test_all_mode_continues_with_document_when_photo_fails(self):
        """Test that 'all' mode still sends document even if photo send fails"""
        sdk_mock = create_autospec(PlatformBotSDK, instance = True)
        sdk_mock.send_photo = Mock(side_effect = Exception("photo send failed"))
        sdk_mock.send_document = Mock(return_value = "document-sent")
        result = PlatformBotSDK.smart_send_photo(
            sdk_mock,
            media_mode = ChatConfigDB.MediaMode.all,
            chat_id = 1,
            photo_url = "http://example.com/img.png",
        )
        # Verify photo was attempted
        sdk_mock.send_photo.assert_called_once_with(1, "http://example.com/img.png", None)
        # Verify document was still sent despite photo failure
        sdk_mock.send_document.assert_called_once_with(1, "http://example.com/img.png", None, thumbnail = None)
        # Return value should be from document
        self.assertEqual(result, "document-sent")

    def test_file_mode_sends_document_only(self):
        """Test that 'file' mode sends document directly"""
        sdk_mock = create_autospec(PlatformBotSDK, instance = True)
        sdk_mock.send_document = Mock(return_value = "document-sent")
        sdk_mock.send_photo = Mock()
        result = PlatformBotSDK.smart_send_photo(
            sdk_mock,
            media_mode = ChatConfigDB.MediaMode.file,
            chat_id = 1,
            photo_url = "http://example.com/img.png",
            caption = "test",
        )
        # Verify document was sent with original URL
        sdk_mock.send_document.assert_called_once_with(1, "http://example.com/img.png", "test", thumbnail = None)
        # Verify photo was not called
        sdk_mock.send_photo.assert_not_called()
        self.assertEqual(result, "document-sent")

    def test_photo_mode_sends_photo_with_fallback(self):
        """Test that 'photo' mode sends photo, falls back to document on failure"""
        sdk_mock = create_autospec(PlatformBotSDK, instance = True)
        sdk_mock.send_photo = Mock(side_effect = Exception("photo failed"))
        sdk_mock.send_document = Mock(return_value = "document-sent")
        result = PlatformBotSDK.smart_send_photo(
            sdk_mock,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_id = 1,
            photo_url = "http://example.com/img.png",
        )
        # Verify photo was attempted
        sdk_mock.send_photo.assert_called_once()
        # Verify document was sent as fallback
        sdk_mock.send_document.assert_called_once_with(1, "http://example.com/img.png", None, thumbnail = None)
        self.assertEqual(result, "document-sent")


class NotificationChatResolutionTest(TestCase):

    mock_di: DI
    user: User

    def setUp(self):
        self.mock_di = Mock(spec = DI)
        self.mock_di.chat_config_repo = Mock(spec = ChatConfigRepository)
        self.mock_di.chat_message_repo = Mock(spec = ChatMessageRepository)

        self.user = User(
            id = UUID(int = 1),
            created_at = date.today(),
            full_name = "Test User",
            telegram_user_id = 12345,
            telegram_chat_id = "telegram_chat_123",
            whatsapp_user_id = "whatsapp_user_123",
            whatsapp_phone_number = SecretStr("+1234567890"),
            group = UserDB.Group.standard,
        )

    def _make_chat(self, chat_type: ChatConfigDB.ChatType, external_id: str) -> ChatConfig:
        return ChatConfig(
            chat_id = UUID(int = hash(external_id) % (2 ** 32)),
            external_id = external_id,
            title = f"Test {chat_type.value} Chat",
            is_private = True,
            reply_chance_percent = 100,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            language_name = "English",
            language_iso_code = "en",
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = chat_type,
        )

    def _make_message(self, chat_id: UUID, author_id: UUID, sent_at: datetime) -> ChatMessage:
        return ChatMessage(
            chat_id = chat_id,
            author_id = author_id,
            message_id = f"msg_{sent_at.timestamp()}",
            sent_at = sent_at,
            text = "Test message",
        )

    def test_no_platforms_available(self):
        self.mock_di.chat_config_repo.get_by_external_identifiers = Mock(return_value = None)
        result = resolve_best_notification_chat(self.user, self.mock_di)
        self.assertIsNone(result)

    def test_telegram_only(self):
        telegram_chat = self._make_chat(ChatConfigDB.ChatType.telegram, "telegram_chat_123")
        self.mock_di.chat_config_repo.get_by_external_identifiers = Mock(side_effect = lambda external_id, chat_type: (
            telegram_chat if chat_type == ChatConfigDB.ChatType.telegram else None
        ))
        self.mock_di.chat_message_repo.get_latest_by_chat = Mock(return_value = [])

        result = resolve_best_notification_chat(self.user, self.mock_di)
        self.assertIsNotNone(result)
        self.assertEqual(result.chat_type, ChatConfigDB.ChatType.telegram)

    def test_telegram_no_messages_still_selected(self):
        telegram_chat = self._make_chat(ChatConfigDB.ChatType.telegram, "telegram_chat_123")
        self.mock_di.chat_config_repo.get_by_external_identifiers = Mock(side_effect = lambda external_id, chat_type: (
            telegram_chat if chat_type == ChatConfigDB.ChatType.telegram else None
        ))
        self.mock_di.chat_message_repo.get_latest_by_chat = Mock(return_value = [])

        result = resolve_best_notification_chat(self.user, self.mock_di)
        self.assertIsNotNone(result)
        self.assertEqual(result.chat_type, ChatConfigDB.ChatType.telegram)

    def test_whatsapp_within_window(self):
        whatsapp_chat = self._make_chat(ChatConfigDB.ChatType.whatsapp, "whatsapp_user_123")
        recent_msg = self._make_message(whatsapp_chat.chat_id, self.user.id, datetime.now() - timedelta(hours = 12))

        self.mock_di.chat_config_repo.get_by_external_identifiers = Mock(side_effect = lambda external_id, chat_type: (
            whatsapp_chat if chat_type == ChatConfigDB.ChatType.whatsapp else None
        ))
        self.mock_di.chat_message_repo.get_latest_by_chat = Mock(return_value = [recent_msg])

        result = resolve_best_notification_chat(self.user, self.mock_di)
        self.assertIsNotNone(result)
        self.assertEqual(result.chat_type, ChatConfigDB.ChatType.whatsapp)

    def test_whatsapp_outside_window(self):
        whatsapp_chat = self._make_chat(ChatConfigDB.ChatType.whatsapp, "whatsapp_user_123")
        old_msg = self._make_message(
            whatsapp_chat.chat_id, self.user.id,
            datetime.now() - timedelta(hours = WHATSAPP_MESSAGING_WINDOW_HOURS + 1),
        )

        self.mock_di.chat_config_repo.get_by_external_identifiers = Mock(side_effect = lambda external_id, chat_type: (
            whatsapp_chat if chat_type == ChatConfigDB.ChatType.whatsapp else None
        ))
        self.mock_di.chat_message_repo.get_latest_by_chat = Mock(return_value = [old_msg])

        result = resolve_best_notification_chat(self.user, self.mock_di)
        self.assertIsNone(result)

    def test_both_eligible_whatsapp_more_recent(self):
        telegram_chat = self._make_chat(ChatConfigDB.ChatType.telegram, "telegram_chat_123")
        whatsapp_chat = self._make_chat(ChatConfigDB.ChatType.whatsapp, "whatsapp_user_123")
        telegram_msg = self._make_message(telegram_chat.chat_id, self.user.id, datetime.now() - timedelta(hours = 10))
        whatsapp_msg = self._make_message(whatsapp_chat.chat_id, self.user.id, datetime.now() - timedelta(hours = 2))

        self.mock_di.chat_config_repo.get_by_external_identifiers = Mock(side_effect = lambda external_id, chat_type: (
            telegram_chat if chat_type == ChatConfigDB.ChatType.telegram
            else whatsapp_chat if chat_type == ChatConfigDB.ChatType.whatsapp
            else None
        ))
        self.mock_di.chat_message_repo.get_latest_by_chat = Mock(side_effect = lambda chat_id, limit: (
            [telegram_msg] if chat_id == telegram_chat.chat_id
            else [whatsapp_msg] if chat_id == whatsapp_chat.chat_id
            else []
        ))

        result = resolve_best_notification_chat(self.user, self.mock_di)
        self.assertEqual(result.chat_type, ChatConfigDB.ChatType.whatsapp)

    def test_both_eligible_telegram_more_recent(self):
        telegram_chat = self._make_chat(ChatConfigDB.ChatType.telegram, "telegram_chat_123")
        whatsapp_chat = self._make_chat(ChatConfigDB.ChatType.whatsapp, "whatsapp_user_123")
        telegram_msg = self._make_message(telegram_chat.chat_id, self.user.id, datetime.now() - timedelta(hours = 2))
        whatsapp_msg = self._make_message(whatsapp_chat.chat_id, self.user.id, datetime.now() - timedelta(hours = 10))

        self.mock_di.chat_config_repo.get_by_external_identifiers = Mock(side_effect = lambda external_id, chat_type: (
            telegram_chat if chat_type == ChatConfigDB.ChatType.telegram
            else whatsapp_chat if chat_type == ChatConfigDB.ChatType.whatsapp
            else None
        ))
        self.mock_di.chat_message_repo.get_latest_by_chat = Mock(side_effect = lambda chat_id, limit: (
            [telegram_msg] if chat_id == telegram_chat.chat_id
            else [whatsapp_msg] if chat_id == whatsapp_chat.chat_id
            else []
        ))

        result = resolve_best_notification_chat(self.user, self.mock_di)
        self.assertEqual(result.chat_type, ChatConfigDB.ChatType.telegram)

    def test_whatsapp_outside_window_telegram_available(self):
        telegram_chat = self._make_chat(ChatConfigDB.ChatType.telegram, "telegram_chat_123")
        whatsapp_chat = self._make_chat(ChatConfigDB.ChatType.whatsapp, "whatsapp_user_123")
        telegram_msg = self._make_message(telegram_chat.chat_id, self.user.id, datetime.now() - timedelta(hours = 48))
        whatsapp_msg = self._make_message(
            whatsapp_chat.chat_id, self.user.id,
            datetime.now() - timedelta(hours = WHATSAPP_MESSAGING_WINDOW_HOURS + 2),
        )

        self.mock_di.chat_config_repo.get_by_external_identifiers = Mock(side_effect = lambda external_id, chat_type: (
            telegram_chat if chat_type == ChatConfigDB.ChatType.telegram
            else whatsapp_chat if chat_type == ChatConfigDB.ChatType.whatsapp
            else None
        ))
        self.mock_di.chat_message_repo.get_latest_by_chat = Mock(side_effect = lambda chat_id, limit: (
            [telegram_msg] if chat_id == telegram_chat.chat_id
            else [whatsapp_msg] if chat_id == whatsapp_chat.chat_id
            else []
        ))

        result = resolve_best_notification_chat(self.user, self.mock_di)
        self.assertEqual(result.chat_type, ChatConfigDB.ChatType.telegram)

    def test_non_private_chat_excluded(self):
        public_chat = self._make_chat(ChatConfigDB.ChatType.telegram, "telegram_chat_123")
        public_chat.is_private = False

        self.mock_di.chat_config_repo.get_by_external_identifiers = Mock(side_effect = lambda external_id, chat_type: (
            public_chat if chat_type == ChatConfigDB.ChatType.telegram else None
        ))

        result = resolve_best_notification_chat(self.user, self.mock_di)
        self.assertIsNone(result)
