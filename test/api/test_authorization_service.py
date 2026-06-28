import unittest
from dataclasses import replace
from datetime import datetime
from unittest.mock import Mock
from uuid import UUID

from pydantic import SecretStr

from api.authorization_service import AuthorizationService
from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.config.chat_config_repo import ChatConfigRepository
from features.chat.membership.chat_membership import ChatMembership
from features.integrations.platform_bot_sdk import ChatAccess
from features.users.user import User
from features.users.user_repo import UserRepository
from util.error_codes import NOT_CHAT_ADMIN, NOT_CHAT_MEMBER, WAITLIST_ACCOUNT_NOT_ACTIVE, WAITLIST_INVITED_POLICIES_REQUIRED
from util.errors import AuthorizationError, NotFoundError, ValidationError


class AuthorizationServiceTest(unittest.TestCase):

    invoker_user: User
    chat_config: ChatConfig
    mock_user_repo: UserRepository
    mock_chat_config_repo: ChatConfigRepository
    mock_di: DI

    def setUp(self):
        self.invoker_user = User(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
            open_ai_key = SecretStr("invoker_api_key"),
            group = UserDB.Group.developer,
            created_at = datetime.now().date(),
        )
        self.chat_config = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = "test_chat_id",
            language_iso_code = "en",
            language_name = "English",
            reply_chance_percent = 100,
            title = "Test Chat",
            is_private = False,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.mock_user_repo = Mock(spec = UserRepository)
        self.mock_user_repo.get.return_value = self.invoker_user
        self.mock_chat_config_repo = Mock(spec = ChatConfigRepository)
        self.mock_chat_config_repo.get.return_value = self.chat_config
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.user_repo = self.mock_user_repo
        # noinspection PyPropertyAccess
        self.mock_di.chat_config_repo = self.mock_chat_config_repo

    def test_validate_chat_success_with_string(self):
        service = AuthorizationService(self.mock_di)
        result = service.validate_chat(self.chat_config.chat_id)
        self.assertEqual(result.chat_id, self.chat_config.chat_id)

    def test_validate_chat_success_with_instance(self):
        service = AuthorizationService(self.mock_di)
        result = service.validate_chat(self.chat_config)
        self.assertEqual(result.chat_id, self.chat_config.chat_id)
        # Should return the same instance that was passed in
        self.assertIs(result, self.chat_config)

    def test_validate_chat_failure_malformed_id(self):
        service = AuthorizationService(self.mock_di)
        with self.assertRaises(ValidationError) as context:
            service.validate_chat("wrong_chat_id")
        self.assertIn("Malformed chat ID 'wrong_chat_id'", str(context.exception))

    def test_validate_user_success_with_hex_string(self):
        service = AuthorizationService(self.mock_di)
        result = service.validate_user(self.invoker_user.id.hex)
        self.assertEqual(result.id, self.invoker_user.id)

    def test_validate_user_success_with_uuid(self):
        service = AuthorizationService(self.mock_di)
        result = service.validate_user(self.invoker_user.id)
        self.assertEqual(result.id, self.invoker_user.id)

    def test_validate_user_success_with_instance(self):
        service = AuthorizationService(self.mock_di)
        result = service.validate_user(self.invoker_user)
        self.assertEqual(result.id, self.invoker_user.id)
        # Should return the same instance that was passed in
        self.assertIs(result, self.invoker_user)

    def test_validate_user_failure_malformed_id(self):
        service = AuthorizationService(self.mock_di)
        with self.assertRaises(ValidationError) as context:
            service.validate_user("wrong_user_id")
        self.assertIn("Malformed user ID 'wrong_user_id'", str(context.exception))

    def test_validate_user_failure_user_not_found(self):
        # Reset mock to return None for this test
        self.mock_di.user_repo.get.return_value = None
        service = AuthorizationService(self.mock_di)
        with self.assertRaises(NotFoundError) as context:
            service.validate_user("00000000000000000000000000000000")
        self.assertIn("User '00000000000000000000000000000000' not found", str(context.exception))

    def test_authorize_for_user_success(self):
        service = AuthorizationService(self.mock_di)
        result = service.authorize_for_user(self.invoker_user, self.invoker_user.id.hex)
        self.assertEqual(result.id, self.invoker_user.id)

    def test_authorize_for_user_failure_different_user(self):
        other_user = User(
            id = UUID(int = 2),
            full_name = "Other User",
            telegram_username = "other_username",
            telegram_chat_id = "other_chat_id",
            telegram_user_id = 2,
            open_ai_key = SecretStr("other_api_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.mock_user_repo.get.return_value = other_user

        service = AuthorizationService(self.mock_di)
        with self.assertRaises(AuthorizationError) as context:
            service.authorize_for_user(self.invoker_user, other_user.id.hex)
        self.assertIn("is not the allowed user", str(context.exception))

    def test_get_authorized_chats_success_user_is_admin(self):
        chat_config_1 = ChatConfig(
            chat_id = UUID(int = 10),
            external_id = "chat_A_id",
            title = "Chat Alpha",
            is_private = False,
            language_iso_code = "en",
            reply_chance_percent = 50,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        chat_config_2 = ChatConfig(
            chat_id = UUID(int = 11),
            external_id = "chat_B_id",
            title = "Chat Bravo",
            is_private = False,
            language_iso_code = "en",
            reply_chance_percent = 50,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        chat_config_3 = ChatConfig(
            chat_id = UUID(int = 12),
            external_id = "chat_C_id",
            title = "Chat Charlie",
            is_private = False,
            language_iso_code = "en",
            reply_chance_percent = 50,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.mock_chat_config_repo.get_all.return_value = [
            chat_config_1,
            chat_config_2,
            chat_config_3,
        ]
        admin_ids = {chat_config_1.chat_id, chat_config_3.chat_id}
        self.mock_di.platform_bot_sdk.return_value.resolve_chat_access.side_effect = (
            lambda chat, user: ChatAccess.admin if chat.chat_id in admin_ids else None
        )

        service = AuthorizationService(self.mock_di)
        admin_chats = service.get_authorized_chats(self.invoker_user)

        self.assertEqual(len(admin_chats), 2)
        admin_chat_ids = [chat.chat_id for chat in admin_chats]
        self.assertIn(chat_config_1.chat_id, admin_chat_ids)
        self.assertIn(chat_config_3.chat_id, admin_chat_ids)
        self.assertNotIn(chat_config_2.chat_id, admin_chat_ids)

    def test_get_authorized_chats_success_user_administers_multiple_chats(self):
        chat_config1 = ChatConfig(
            chat_id = UUID(int = 21), external_id = "chat_id_1",
            title = "Admin Chat 1", language_iso_code = "en", reply_chance_percent = 50,
            is_private = False, release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        chat_config2 = ChatConfig(
            chat_id = UUID(int = 22), external_id = "chat_id_2",
            title = "Non-Admin Chat", language_iso_code = "es", reply_chance_percent = 70,
            is_private = False, release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        chat_config3 = ChatConfig(
            chat_id = UUID(int = 23), external_id = "chat_id_3",
            title = "Admin Chat 2", language_iso_code = "fr", reply_chance_percent = 60,
            is_private = False, release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.mock_chat_config_repo.get_all.return_value = [chat_config1, chat_config2, chat_config3]
        admin_ids = {chat_config1.chat_id, chat_config3.chat_id}
        self.mock_di.platform_bot_sdk.return_value.resolve_chat_access.side_effect = (
            lambda chat, user: ChatAccess.admin if chat.chat_id in admin_ids else None
        )

        service = AuthorizationService(self.mock_di)
        admin_chats = service.get_authorized_chats(self.invoker_user)

        self.assertEqual(len(admin_chats), 2)
        admin_chat_ids = [chat.chat_id for chat in admin_chats]
        self.assertIn(chat_config1.chat_id, admin_chat_ids)
        self.assertIn(chat_config3.chat_id, admin_chat_ids)
        self.assertNotIn(chat_config2.chat_id, admin_chat_ids)

    def test_get_authorized_chats_user_no_telegram_id(self):
        user_without_telegram_id = User(
            id = UUID(int = 1),
            full_name = "User Without Telegram ID",
            telegram_username = "user_no_telegram",
            telegram_chat_id = None,
            telegram_user_id = None,
            open_ai_key = SecretStr("api_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        self.mock_chat_config_repo.get_all.return_value = []

        service = AuthorizationService(self.mock_di)
        admin_chats = service.get_authorized_chats(user_without_telegram_id)

        self.assertEqual(len(admin_chats), 0)

    def test_get_authorized_chats_sorting_order(self):
        private_chat = ChatConfig(
            chat_id = UUID(int = 2),
            external_id = self.invoker_user.telegram_chat_id or "invoker_chat_id",
            title = "Private Chat",
            is_private = True,
            language_iso_code = "en",
            reply_chance_percent = 100,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        group_chat_z = ChatConfig(
            chat_id = UUID(int = 3),
            external_id = "group_z_id",
            title = "Z Group",
            is_private = False,
            language_iso_code = "en",
            reply_chance_percent = 50,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        group_chat_a = ChatConfig(
            chat_id = UUID(int = 4),
            external_id = "group_a_id",
            title = "A Group",
            is_private = False,
            language_iso_code = "en",
            reply_chance_percent = 50,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        group_chat_no_title = ChatConfig(
            chat_id = UUID(int = 5),
            external_id = "group_no_title_id",
            title = None,
            is_private = False,
            language_iso_code = "en",
            reply_chance_percent = 50,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )

        self.mock_chat_config_repo.get_all.return_value = [
            group_chat_z,
            private_chat,
            group_chat_no_title,
            group_chat_a,
        ]

        self.mock_di.platform_bot_sdk.return_value.resolve_chat_access.return_value = ChatAccess.admin

        service = AuthorizationService(self.mock_di)
        admin_chats = service.get_authorized_chats(self.invoker_user)

        expected_order = [
            private_chat.chat_id,
            group_chat_no_title.chat_id,
            group_chat_a.chat_id,
            group_chat_z.chat_id,
        ]

        actual_order = [chat.chat_id for chat in admin_chats]
        self.assertEqual(actual_order, expected_order)

    def test_authorize_for_user_success_with_uuid(self):
        service = AuthorizationService(self.mock_di)
        result = service.authorize_for_user(self.invoker_user, self.invoker_user.id)
        self.assertEqual(result.id, self.invoker_user.id)

    def test_authorize_for_user_success_with_instance(self):
        service = AuthorizationService(self.mock_di)
        result = service.authorize_for_user(self.invoker_user, self.invoker_user)
        self.assertEqual(result.id, self.invoker_user.id)
        # Should return the same instance that was passed in
        self.assertIs(result, self.invoker_user)

    def test_require_user_is_chat_ready_success(self):
        active_user = replace(
            self.invoker_user,
            is_on_waitlist = False,
            are_policies_accepted = True,
        )
        service = AuthorizationService(self.mock_di)
        service.require_user_is_chat_ready(active_user)

    def test_require_user_is_chat_ready_waitlist_requires_activation(self):
        waitlisted_user = replace(
            self.invoker_user,
            is_on_waitlist = True,
            is_invited_to_start = False,
            are_policies_accepted = False,
        )
        service = AuthorizationService(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            service.require_user_is_chat_ready(waitlisted_user)

        self.assertEqual(context.exception.error_code, WAITLIST_ACCOUNT_NOT_ACTIVE)

    def test_require_user_is_chat_ready_invited_requires_policies(self):
        invited_user = replace(
            self.invoker_user,
            is_on_waitlist = True,
            is_invited_to_start = True,
            are_policies_accepted = False,
        )
        service = AuthorizationService(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            service.require_user_is_chat_ready(invited_user)

        self.assertEqual(context.exception.error_code, WAITLIST_INVITED_POLICIES_REQUIRED)

    def test_require_user_is_chat_ready_non_waitlisted_requires_policies(self):
        inactive_user = replace(
            self.invoker_user,
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = False,
        )
        service = AuthorizationService(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            service.require_user_is_chat_ready(inactive_user)

        self.assertEqual(context.exception.error_code, WAITLIST_INVITED_POLICIES_REQUIRED)

    def test_require_waitlisted_user_can_activate_when_invited(self):
        invited_user = replace(
            self.invoker_user,
            is_on_waitlist = True,
            is_invited_to_start = True,
            are_policies_accepted = False,
        )
        self.mock_user_repo.count.return_value = 999999
        service = AuthorizationService(self.mock_di)

        service.require_waitlisted_user_can_activate(invited_user)

    def test_require_waitlisted_user_can_activate_with_available_capacity(self):
        waitlisted_user = replace(
            self.invoker_user,
            is_on_waitlist = True,
            is_invited_to_start = False,
            are_policies_accepted = False,
        )
        self.mock_user_repo.count.return_value = 0
        service = AuthorizationService(self.mock_di)

        service.require_waitlisted_user_can_activate(waitlisted_user)

    def test_require_waitlisted_user_can_activate_denied_without_invite_or_capacity(self):
        waitlisted_user = replace(
            self.invoker_user,
            is_on_waitlist = True,
            is_invited_to_start = False,
            are_policies_accepted = False,
        )
        self.mock_user_repo.count.return_value = 999999
        service = AuthorizationService(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            service.require_waitlisted_user_can_activate(waitlisted_user)

        self.assertEqual(context.exception.error_code, WAITLIST_ACCOUNT_NOT_ACTIVE)

    # === validate_chat_admin ===

    def test_validate_chat_admin_success_when_admin(self):
        self.mock_di.chat_membership_service.sync.return_value = ChatMembership(
            user_id = self.invoker_user.id,
            chat_id = self.chat_config.chat_id,
            is_admin = True,
            use_about_me = True,
            use_custom_prompt = True,
        )

        service = AuthorizationService(self.mock_di)
        result = service.validate_chat_admin(self.invoker_user, self.chat_config)

        self.assertEqual(result, self.chat_config)
        self.mock_di.chat_membership_service.save.assert_not_called()

    def test_validate_chat_admin_denied_when_not_admin(self):
        existing_membership = ChatMembership(
            user_id = self.invoker_user.id,
            chat_id = self.chat_config.chat_id,
            is_admin = False,
            use_about_me = False,
            use_custom_prompt = False,
        )
        self.mock_di.chat_membership_service.sync.return_value = existing_membership

        service = AuthorizationService(self.mock_di)
        with self.assertRaises(AuthorizationError) as context:
            service.validate_chat_admin(self.invoker_user, self.chat_config)
        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)

    # === update_chat_authorization ===

    def test_update_chat_authorization_delegates_to_sync(self):
        expected = ChatMembership(
            user_id = self.invoker_user.id,
            chat_id = self.chat_config.chat_id,
            is_admin = True,
            use_about_me = True,
            use_custom_prompt = True,
        )
        self.mock_di.chat_membership_service.sync.return_value = expected

        service = AuthorizationService(self.mock_di)
        result = service.update_chat_authorization(self.invoker_user, self.chat_config)

        self.assertIs(result, expected)
        self.mock_di.chat_membership_service.sync.assert_called_once_with(self.invoker_user, self.chat_config)

    def test_update_chat_authorization_propagates_authorization_error(self):
        self.mock_di.chat_membership_service.sync.side_effect = AuthorizationError(
            "not a participant", NOT_CHAT_MEMBER,
        )

        service = AuthorizationService(self.mock_di)
        with self.assertRaises(AuthorizationError) as context:
            service.update_chat_authorization(self.invoker_user, self.chat_config)

        self.assertEqual(context.exception.error_code, NOT_CHAT_MEMBER)

    # === update_all_chat_authorizations ===

    def test_update_all_chat_authorizations_delegates_to_membership_service(self):
        self.mock_chat_config_repo.get_all.return_value = [self.chat_config]
        self.mock_di.platform_bot_sdk.return_value.resolve_chat_access.return_value = ChatAccess.admin
        updated_membership = ChatMembership(
            user_id = self.invoker_user.id,
            chat_id = self.chat_config.chat_id,
            is_admin = True,
            use_about_me = True,
            use_custom_prompt = True,
        )
        self.mock_di.chat_membership_service.refresh_chat_memberships.return_value = [updated_membership]

        service = AuthorizationService(self.mock_di)
        result = service.update_all_chat_authorizations(self.invoker_user)

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_admin)
        self.mock_di.chat_membership_service.refresh_chat_memberships.assert_called_once()
        refresh_args = self.mock_di.chat_membership_service.refresh_chat_memberships.call_args
        self.assertEqual(refresh_args.args[0], self.invoker_user)
        self.assertIn(self.chat_config, refresh_args.args[1])
