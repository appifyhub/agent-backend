from datetime import datetime, timedelta
from unittest import TestCase
from uuid import UUID

import stubs
from pydantic import SecretStr
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
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
    resolve_user_to_create,
)
from features.users.user import User
from features.users.user_repo import UserRepository
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
        user = stubs.domain.user()
        result = resolve_external_id(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "123456789")

    def test_resolve_external_id_telegram_none(self):
        user = stubs.domain.user(telegram_user_id = None)
        result = resolve_external_id(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_external_id_unsupported_platform(self):
        user = stubs.domain.user()
        result = resolve_external_id(user, ChatConfigDB.ChatType.background)
        self.assertIsNone(result)

    def test_resolve_external_id_whatsapp_success(self):
        user = stubs.domain.user(whatsapp_user_id = "15551234567")
        result = resolve_external_id(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "15551234567")

    def test_resolve_external_id_whatsapp_none(self):
        user = stubs.domain.user(whatsapp_user_id = None)
        result = resolve_external_id(user, ChatConfigDB.ChatType.whatsapp)
        self.assertIsNone(result)

    def test_resolve_external_handle_telegram_success(self):
        user = stubs.domain.user(telegram_username = "test_user")
        result = resolve_external_handle(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "test_user")

    def test_resolve_external_handle_telegram_none(self):
        user = stubs.domain.user(telegram_username = None)
        result = resolve_external_handle(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_external_handle_unsupported_platform(self):
        user = stubs.domain.user()
        result = resolve_external_handle(user, ChatConfigDB.ChatType.github)
        self.assertIsNone(result)

    def test_resolve_external_handle_whatsapp_success(self):
        user = stubs.domain.user(whatsapp_phone_number = SecretStr("15551234567"))
        result = resolve_external_handle(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "15551234567")

    def test_resolve_external_handle_whatsapp_none(self):
        user = stubs.domain.user(whatsapp_phone_number = None)
        result = resolve_external_handle(user, ChatConfigDB.ChatType.whatsapp)
        self.assertIsNone(result)

    def test_is_the_agent_true(self):
        user = stubs.domain.user(
            telegram_user_id = config.telegram_bot_id,
        )
        result = is_the_agent(user, ChatConfigDB.ChatType.telegram)
        self.assertTrue(result)

    def test_is_the_agent_false_different_user(self):
        user = stubs.domain.user(
            telegram_user_id = 987654321,
        )
        result = is_the_agent(user, ChatConfigDB.ChatType.telegram)
        self.assertFalse(result)

    def test_is_the_agent_none_user(self):
        result = is_the_agent(None, ChatConfigDB.ChatType.telegram)
        self.assertFalse(result)

    def test_resolve_user_to_create_telegram_success(self):
        result = resolve_user_to_create("test_user", ChatConfigDB.ChatType.telegram)

        assert result is not None
        self.assertIsInstance(result, User)
        self.assertEqual(result.telegram_username, "test_user")
        self.assertIsNone(result.id)
        self.assertIsNone(result.full_name)
        self.assertIsNone(result.telegram_chat_id)
        self.assertIsNone(result.telegram_user_id)
        self.assertEqual(result.group, UserDB.Group.standard)

    def test_resolve_user_to_create_telegram_with_at(self):
        result = resolve_user_to_create("@test_user", ChatConfigDB.ChatType.telegram)

        assert result is not None
        self.assertIsInstance(result, User)
        self.assertEqual(result.telegram_username, "test_user")

    def test_resolve_user_to_create_telegram_with_spaces_and_symbols(self):
        result = resolve_user_to_create("@ test user +", ChatConfigDB.ChatType.telegram)

        assert result is not None
        self.assertIsInstance(result, User)
        self.assertEqual(result.telegram_username, "testuser")

    def test_resolve_user_to_create_unsupported_platform(self):
        result = resolve_user_to_create("test_user", ChatConfigDB.ChatType.background)

        self.assertIsNone(result)

    def test_resolve_user_to_create_whatsapp_success(self):
        result = resolve_user_to_create("+1 (555) 123-4567", ChatConfigDB.ChatType.whatsapp)

        assert result is not None
        self.assertIsInstance(result, User)
        self.assertEqual(result.whatsapp_user_id, "15551234567")
        assert result.whatsapp_phone_number is not None
        self.assertEqual(result.whatsapp_phone_number.get_secret_value(), "15551234567")
        self.assertIsNone(result.id)
        self.assertIsNone(result.full_name)
        self.assertEqual(result.group, UserDB.Group.standard)

    def test_resolve_any_external_handle_telegram_success(self):
        user = stubs.domain.user(telegram_username = "test_user")
        handle, chat_type = resolve_any_external_handle(user)
        self.assertEqual(handle, "test_user")
        self.assertEqual(chat_type, ChatConfigDB.ChatType.telegram)

    def test_resolve_any_external_handle_telegram_with_whitespace(self):
        user = stubs.domain.user(telegram_username = "  test_user  ")
        handle, chat_type = resolve_any_external_handle(user)
        self.assertEqual(handle, "test_user")  # Should be stripped
        self.assertEqual(chat_type, ChatConfigDB.ChatType.telegram)

    def test_resolve_any_external_handle_telegram_empty_string(self):
        user = stubs.domain.user(
            telegram_username = "",
            whatsapp_phone_number = None,
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertIsNone(handle)
        self.assertIsNone(chat_type)

    def test_resolve_any_external_handle_telegram_whitespace_only(self):
        user = stubs.domain.user(
            telegram_username = "   ",
            whatsapp_phone_number = None,
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertIsNone(handle)
        self.assertIsNone(chat_type)

    def test_resolve_any_external_handle_no_handles(self):
        user = stubs.domain.user(
            telegram_username = None,
            whatsapp_phone_number = None,
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertIsNone(handle)
        self.assertIsNone(chat_type)

    def test_resolve_any_external_handle_prioritizes_first_available(self):
        user = stubs.domain.user(telegram_username = "telegram_user")
        handle, chat_type = resolve_any_external_handle(user)
        self.assertEqual(handle, "telegram_user")
        self.assertEqual(chat_type, ChatConfigDB.ChatType.telegram)

    def test_resolve_any_external_handle_whatsapp_success(self):
        user = stubs.domain.user(
            telegram_username = None,
            whatsapp_phone_number = SecretStr("15551234567"),
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertEqual(handle, "15551234567")
        self.assertEqual(chat_type, ChatConfigDB.ChatType.whatsapp)

    def test_resolve_any_external_handle_whatsapp_with_whitespace(self):
        user = stubs.domain.user(
            telegram_username = None,
            whatsapp_phone_number = SecretStr("  15551234567  "),
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertEqual(handle, "15551234567")  # Should be stripped
        self.assertEqual(chat_type, ChatConfigDB.ChatType.whatsapp)

    def test_resolve_any_external_handle_whatsapp_empty_string(self):
        user = stubs.domain.user(
            telegram_username = None,
            whatsapp_phone_number = SecretStr(""),
        )
        handle, chat_type = resolve_any_external_handle(user)
        self.assertIsNone(handle)
        self.assertIsNone(chat_type)

    def test_resolve_any_external_handle_telegram_and_whatsapp_prioritizes_telegram(self):
        user = stubs.domain.user(
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
        user = stubs.domain.user(telegram_username = "test_user")
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "[@test_user](https://t.me/test_user)")

    def test_resolve_user_link_telegram_with_at_prefix(self):
        user = stubs.domain.user(telegram_username = "@test_user")
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "[@test_user](https://t.me/test_user)")

    def test_resolve_user_link_telegram_with_plus_prefix(self):
        user = stubs.domain.user(telegram_username = "+test_user")
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "[@test_user](https://t.me/test_user)")

    def test_resolve_user_link_telegram_with_slash_prefix(self):
        user = stubs.domain.user(telegram_username = "/test_user")
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "[@test_user](https://t.me/test_user)")

    def test_resolve_user_link_telegram_empty_username(self):
        user = stubs.domain.user(telegram_username = "")
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_user_link_telegram_whitespace_only(self):
        user = stubs.domain.user(telegram_username = "   ")
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_user_link_telegram_none_username(self):
        user = stubs.domain.user(telegram_username = None)
        result = resolve_user_link(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_user_link_github_no_handle(self):
        user = stubs.domain.user(
            telegram_username = "test_user",  # GitHub doesn't use telegram_username
        )
        result = resolve_user_link(user, ChatConfigDB.ChatType.github)
        self.assertIsNone(result)  # GitHub handle resolution not implemented yet

    def test_resolve_user_link_background_platform(self):
        user = stubs.domain.user(telegram_username = "test_user")
        result = resolve_user_link(user, ChatConfigDB.ChatType.background)
        self.assertIsNone(result)

    def test_resolve_user_link_whatsapp_success(self):
        user = stubs.domain.user(whatsapp_phone_number = SecretStr("15551234567"))
        result = resolve_user_link(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "[15551234567](https://wa.me/15551234567)")

    def test_resolve_user_link_whatsapp_with_plus_prefix(self):
        user = stubs.domain.user()
        result = resolve_user_link(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "[15551234567](https://wa.me/15551234567)")

    def test_resolve_user_link_whatsapp_formatted_phone(self):
        user = stubs.domain.user(whatsapp_phone_number = SecretStr("+1 (555) 123-4567"))
        result = resolve_user_link(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "[15551234567](https://wa.me/15551234567)")

    def test_resolve_user_link_whatsapp_empty_phone_number(self):
        user = stubs.domain.user(whatsapp_phone_number = SecretStr(""))
        result = resolve_user_link(user, ChatConfigDB.ChatType.whatsapp)
        self.assertIsNone(result)

    def test_resolve_user_link_whatsapp_none_phone_number(self):
        user = stubs.domain.user(whatsapp_phone_number = None)
        result = resolve_user_link(user, ChatConfigDB.ChatType.whatsapp)
        self.assertIsNone(result)

    def test_resolve_private_chat_id_telegram_success(self):
        user = stubs.domain.user()
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.telegram)
        self.assertEqual(result, "123456789")

    def test_resolve_private_chat_id_telegram_none(self):
        user = stubs.domain.user(telegram_chat_id = None)
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.telegram)
        self.assertIsNone(result)

    def test_resolve_private_chat_id_background_platform(self):
        user = stubs.domain.user()
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.background)
        self.assertIsNone(result)

    def test_resolve_private_chat_id_github_platform(self):
        user = stubs.domain.user()
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.github)
        self.assertIsNone(result)

    def test_resolve_private_chat_id_whatsapp_success(self):
        user = stubs.domain.user(whatsapp_user_id = "15551234567")
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.whatsapp)
        self.assertEqual(result, "15551234567")

    def test_resolve_private_chat_id_whatsapp_none(self):
        user = stubs.domain.user(whatsapp_user_id = None)
        result = resolve_private_chat_id(user, ChatConfigDB.ChatType.whatsapp)
        self.assertIsNone(result)

    def test_is_own_chat_whatsapp_success(self):
        user = stubs.domain.user(whatsapp_user_id = "15551234567")
        chat_config = stubs.domain.chat_config(
            external_id = "15551234567",
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertTrue(result)

    def test_is_own_chat_whatsapp_different_user(self):
        user = stubs.domain.user(whatsapp_user_id = "15551234567")
        chat_config = stubs.domain.chat_config(
            external_id = "15559999999",
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertFalse(result)

    def test_is_own_chat_whatsapp_missing_user_id(self):
        user = stubs.domain.user(whatsapp_user_id = None)
        chat_config = stubs.domain.chat_config(
            external_id = "15551234567",
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertFalse(result)

    def test_is_own_chat_whatsapp_missing_external_id(self):
        user = stubs.domain.user(whatsapp_user_id = "15551234567")
        chat_config = stubs.domain.chat_config(
            external_id = None,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertFalse(result)

    def test_is_own_chat_whatsapp_not_private(self):
        user = stubs.domain.user(whatsapp_user_id = "15551234567")
        chat_config = stubs.domain.chat_config(
            external_id = "15551234567",
            is_private = False,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertFalse(result)

    def test_is_own_chat_whatsapp_phone_number_normalization(self):
        user = stubs.domain.user(whatsapp_user_id = "15551234567")
        chat_config = stubs.domain.chat_config(
            external_id = "+1 (555) 123-4567",
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertTrue(result)

    def test_is_own_chat_whatsapp_phone_number_normalization_different(self):
        user = stubs.domain.user(whatsapp_user_id = "15551234567")
        chat_config = stubs.domain.chat_config(
            external_id = "+1 (555) 999-9999",
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        result = is_own_chat(chat_config, user)
        self.assertFalse(result)


class LookupUserByHandleTest(TestCase):

    di: DI
    repo: UserRepository

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.repo = self.di.user_repo

    def test_lookup_user_by_handle_telegram_success(self):
        user = self.repo.save(stubs.domain.user(telegram_username = "test_user"))

        result = lookup_user_by_handle("test_user", ChatConfigDB.ChatType.telegram, self.repo)

        self.assertEqual(result, user)

    def test_lookup_user_by_handle_telegram_not_found(self):
        result = lookup_user_by_handle("nonexistent_user", ChatConfigDB.ChatType.telegram, self.repo)

        self.assertIsNone(result)

    def test_lookup_user_by_handle_telegram_with_at(self):
        user = self.repo.save(stubs.domain.user(telegram_username = "test_user"))

        result = lookup_user_by_handle("@test_user", ChatConfigDB.ChatType.telegram, self.repo)

        self.assertEqual(result, user)

    def test_lookup_user_by_handle_unsupported_platform(self):
        self.repo.save(stubs.domain.user(telegram_username = "test_user"))

        result = lookup_user_by_handle("test_user", ChatConfigDB.ChatType.background, self.repo)

        self.assertIsNone(result)

    def test_lookup_user_by_handle_whatsapp_success(self):
        user = self.repo.save(stubs.domain.user(whatsapp_user_id = "15551234567"))

        result = lookup_user_by_handle("+1 (555) 123-4567", ChatConfigDB.ChatType.whatsapp, self.repo)

        self.assertEqual(result, user)

    def test_lookup_user_by_handle_whatsapp_falls_back_to_phone_number(self):
        user = self.repo.save(stubs.domain.user(
            whatsapp_user_id = None,
            whatsapp_phone_number = SecretStr("15551234567"),
        ))

        result = lookup_user_by_handle("+1 (555) 123-4567", ChatConfigDB.ChatType.whatsapp, self.repo)

        self.assertEqual(result, user)

    def test_lookup_user_by_handle_whatsapp_not_found(self):
        result = lookup_user_by_handle("+1 (555) 999-9999", ChatConfigDB.ChatType.whatsapp, self.repo)

        self.assertIsNone(result)


class NotificationChatResolutionTest(TestCase):

    di: DI
    user: User
    telegram_chat: ChatConfig
    whatsapp_chat: ChatConfig

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.telegram_chat = stubs.domain.chat_config(external_id = str(self.user.telegram_user_id))
        self.whatsapp_chat = stubs.domain.chat_config(
            chat_id = UUID("33333333-3333-4333-8333-c33333333333"),
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = self.user.whatsapp_user_id,
        )

    def test_no_platforms_available(self):
        result = resolve_best_notification_chat(self.user, self.di)

        self.assertIsNone(result)

    def test_telegram_no_messages_still_selected(self):
        chat = self.di.chat_config_repo.save(self.telegram_chat)

        result = resolve_best_notification_chat(self.user, self.di)

        self.assertEqual(result, chat)

    def test_whatsapp_within_window(self):
        chat = self.di.chat_config_repo.save(self.whatsapp_chat)
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = chat.chat_id,
            author_id = self.user.id,
            sent_at = datetime.now() - timedelta(hours = 12),
            ingestion_order = None,
        ))

        result = resolve_best_notification_chat(self.user, self.di)

        self.assertEqual(result, chat)

    def test_whatsapp_outside_window(self):
        chat = self.di.chat_config_repo.save(self.whatsapp_chat)
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = chat.chat_id,
            author_id = self.user.id,
            sent_at = datetime.now() - timedelta(hours = WHATSAPP_MESSAGING_WINDOW_HOURS + 1),
            ingestion_order = None,
        ))

        result = resolve_best_notification_chat(self.user, self.di)

        self.assertIsNone(result)

    def test_both_eligible_whatsapp_more_recent(self):
        telegram_chat = self.di.chat_config_repo.save(self.telegram_chat)
        whatsapp_chat = self.di.chat_config_repo.save(self.whatsapp_chat)
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = telegram_chat.chat_id,
            author_id = self.user.id,
            sent_at = datetime.now() - timedelta(hours = 10),
            ingestion_order = None,
        ))
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = whatsapp_chat.chat_id,
            author_id = self.user.id,
            sent_at = datetime.now() - timedelta(hours = 2),
            ingestion_order = None,
        ))

        result = resolve_best_notification_chat(self.user, self.di)

        self.assertEqual(result, whatsapp_chat)

    def test_both_eligible_telegram_more_recent(self):
        telegram_chat = self.di.chat_config_repo.save(self.telegram_chat)
        whatsapp_chat = self.di.chat_config_repo.save(self.whatsapp_chat)
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = telegram_chat.chat_id,
            author_id = self.user.id,
            sent_at = datetime.now() - timedelta(hours = 2),
            ingestion_order = None,
        ))
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = whatsapp_chat.chat_id,
            author_id = self.user.id,
            sent_at = datetime.now() - timedelta(hours = 10),
            ingestion_order = None,
        ))

        result = resolve_best_notification_chat(self.user, self.di)

        self.assertEqual(result, telegram_chat)

    def test_whatsapp_outside_window_telegram_available(self):
        telegram_chat = self.di.chat_config_repo.save(self.telegram_chat)
        whatsapp_chat = self.di.chat_config_repo.save(self.whatsapp_chat)
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = telegram_chat.chat_id,
            author_id = self.user.id,
            sent_at = datetime.now() - timedelta(hours = 48),
            ingestion_order = None,
        ))
        self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = whatsapp_chat.chat_id,
            author_id = self.user.id,
            sent_at = datetime.now() - timedelta(hours = WHATSAPP_MESSAGING_WINDOW_HOURS + 2),
            ingestion_order = None,
        ))

        result = resolve_best_notification_chat(self.user, self.di)

        self.assertEqual(result, telegram_chat)

    def test_non_private_chat_excluded(self):
        self.di.chat_config_repo.save(stubs.domain.chat_config(
            external_id = self.telegram_chat.external_id,
            is_private = False,
        ))

        result = resolve_best_notification_chat(self.user, self.di)

        self.assertIsNone(result)
