import base64
import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import UUID

from pydantic import SecretStr

from api.authorization_service import AuthorizationService
from api.model.chat_config_payload import ChatConfigPayload
from api.model.chat_settings_payload import ChatSettingsPayload
from api.model.settings_link_response import SettingsLinkResponse
from api.model.user_chat_config_payload import UserChatConfigPayload
from api.model.user_settings_payload import UserSettingsPayload
from api.settings_controller import SettingsController
from db.crud.user import UserCRUD
from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.user import User
from di.di import DI
from features.chat.config.chat_config import ChatConfig as ChatConfigDomain
from features.chat.config.chat_config_repo import ChatConfigRepository
from features.chat.membership.chat_membership import ChatMembership
from features.chat.telegram.model.chat_member import ChatMemberAdministrator
from features.chat.telegram.model.user import User as TelegramUser
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.external_tools.access_token_resolver import AccessTokenResolver
from features.external_tools.external_tool import CostEstimate, ExternalTool, ExternalToolProvider, ToolType
from features.external_tools.external_tool_library import CLAUDE_4_6_SONNET, GPT_4O, IMAGE_GEN_FLUX_1_1, SONAR
from features.sponsorships.sponsorship_repo import SponsorshipRepository
from util.config import ConfiguredProduct
from util.error_codes import (
    NOT_CHAT_ADMIN,
    POLICY_ACCEPTANCE_REVOCATION_FORBIDDEN,
    WAITLIST_ACCOUNT_NOT_ACTIVE,
)
from util.errors import AuthorizationError, ValidationError
from util.functions import mask_secret


class SettingsControllerTest(unittest.TestCase):

    invoker_user: User
    invoker_telegram_user: TelegramUser
    chat_config: ChatConfigDomain
    chat_config_domain: ChatConfigDomain
    mock_di: DI
    mock_user_dao: UserCRUD
    mock_chat_config_repo: ChatConfigRepository
    mock_sponsorship_repo: SponsorshipRepository
    mock_telegram_sdk: TelegramBotSDK
    mock_authorization_service: AuthorizationService
    mock_access_token_resolver: AccessTokenResolver

    def setUp(self):
        self.invoker_telegram_user = TelegramUser(
            id = 123456789,
            is_bot = False,
            first_name = "Test",
            last_name = "User",
            username = "testuser",
            language_code = "en",
        )
        self.invoker_user = User(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Test User",
            telegram_username = "testuser",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
            open_ai_key = SecretStr("test_openai_key"),
            anthropic_key = SecretStr("test_anthropic_key"),
            perplexity_key = SecretStr("test_perplexity_key"),
            replicate_key = SecretStr("test_replicate_key"),
            rapid_api_key = SecretStr("test_rapid_api_key"),
            coinmarketcap_key = SecretStr("test_coinmarketcap_key"),
            tool_choice_chat = "gpt-4o",
            tool_choice_reasoning = "claude-3-7-sonnet-latest",
            tool_choice_vision = "gpt-4o",
            tool_choice_images_gen = "dall-e-3",
            tool_choice_search = "perplexity-search",
            group = UserDB.Group.developer,
            created_at = datetime.now().date(),
        )
        self.chat_config = ChatConfigDomain(
            chat_id = UUID(int = 1),
            external_id = "test_chat_123",
            title = "Test Chat",
            language_iso_code = "en",
            reply_chance_percent = 75,
            is_private = False,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.chat_config_domain = self.chat_config

        # Create mocks
        self.mock_user_dao = MagicMock(spec = UserCRUD)
        self.mock_chat_config_repo = MagicMock(spec = ChatConfigRepository)
        self.mock_sponsorship_repo = MagicMock(spec = SponsorshipRepository)
        self.mock_telegram_sdk = MagicMock(spec = TelegramBotSDK)

        # Configure common mock returns
        self.mock_user_dao.get.return_value = self.invoker_user
        self.mock_chat_config_repo.get.return_value = self.chat_config_domain
        self.mock_chat_config_repo.save.return_value = self.chat_config_domain
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        # Create mock DI container
        self.mock_di = MagicMock(spec = DI)
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = self.invoker_user)
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker_chat = PropertyMock(return_value = self.chat_config)
        # noinspection PyPropertyAccess
        type(self.mock_di).invoker_chat_type = PropertyMock(return_value = ChatConfigDB.ChatType.telegram)
        # noinspection PyPropertyAccess
        self.mock_di.user_crud = self.mock_user_dao
        # noinspection PyPropertyAccess
        self.mock_di.chat_config_repo = self.mock_chat_config_repo
        # noinspection PyPropertyAccess
        self.mock_di.sponsorship_repo = self.mock_sponsorship_repo
        # noinspection PyPropertyAccess
        self.mock_di.telegram_bot_sdk = self.mock_telegram_sdk

        self.membership = ChatMembership(
            user_id = self.invoker_user.id,
            chat_id = self.chat_config.chat_id,
            is_admin = True,
            use_about_me = True,
            use_custom_prompt = True,
        )
        self.mock_membership_repo = MagicMock()
        self.mock_membership_repo.get.return_value = self.membership
        self.mock_membership_repo.save.return_value = self.membership
        self.mock_membership_repo.get_all_for_user.return_value = [self.membership]
        # noinspection PyPropertyAccess
        self.mock_di.chat_membership_repo = self.mock_membership_repo
        # noinspection PyPropertyAccess
        self.mock_di.chat_membership_service.sync.return_value = self.membership
        # noinspection PyPropertyAccess
        self.mock_di.chat_membership_service.get_all_for_user.return_value = [self.membership]
        # noinspection PyPropertyAccess
        self.mock_di.chat_membership_service.save.return_value = self.membership

        # Mock authorization service
        self.mock_authorization_service = MagicMock()
        self.mock_authorization_service.authorize_for_user.return_value = self.invoker_user
        self.mock_authorization_service.validate_chat.return_value = self.chat_config
        self.mock_authorization_service.validate_chat_admin.return_value = self.chat_config
        self.mock_authorization_service.get_authorized_chats.return_value = []
        self.mock_authorization_service.update_all_chat_authorizations.return_value = []
        self.mock_authorization_service.require_waitlisted_user_can_activate.return_value = self.invoker_user
        # noinspection PyPropertyAccess
        self.mock_di.authorization_service = self.mock_authorization_service

        # Mock access token resolver
        self.mock_access_token_resolver = MagicMock()
        self.mock_access_token_resolver.get_access_token_for_tool.return_value = None
        self.mock_access_token_resolver.get_access_token.return_value = None
        self.mock_di.access_token_resolver.return_value = self.mock_access_token_resolver

        # Mock URL shortener to return same URL
        def mock_url_shortener(long_url, **kwargs):
            mock_shortener = MagicMock()
            mock_shortener.execute.return_value = long_url
            return mock_shortener
        self.mock_di.url_shortener = MagicMock(side_effect = mock_url_shortener)

    @staticmethod
    def create_admin_member(telegram_user, is_manager = True):
        return ChatMemberAdministrator(
            user = telegram_user,
            status = "administrator",
            can_be_edited = True,
            can_manage_chat = is_manager,
            can_change_info = True,
            can_delete_messages = True,
            can_invite_users = True,
            can_restrict_members = True,
            can_pin_messages = True,
            can_promote_members = False,
            is_anonymous = False,
            can_manage_video_chats = True,
            can_post_stories = False,
            can_edit_stories = False,
            can_delete_stories = False,
        )

    def test_create_settings_link_default_is_intelligence(self):
        controller = SettingsController(self.mock_di)
        link_response = controller.create_settings_link()

        self.assertIsInstance(link_response, SettingsLinkResponse)
        link = link_response.settings_link
        self.assertIn("user", link)
        self.assertIn("intelligence", link)
        self.assertIn(self.invoker_user.id.hex, link)
        self.assertIn("token=", link)

    def test_create_settings_link_success_user_settings(self):
        controller = SettingsController(self.mock_di)
        link_response = controller.create_settings_link("user")

        self.assertIsInstance(link_response, SettingsLinkResponse)
        link = link_response.settings_link
        self.assertIn("user", link)
        self.assertIn("settings", link)
        self.assertIn(self.invoker_user.id.hex, link)
        self.assertIn("token=", link)

    def test_create_settings_link_success_chat_settings(self):
        controller = SettingsController(self.mock_di)
        # noinspection PyPropertyAccess
        self.mock_di.invoker_chat_id = self.chat_config.chat_id.hex
        # noinspection PyPropertyAccess
        self.mock_di.invoker_chat = self.chat_config
        link_response = controller.create_settings_link("chat")

        self.assertIsInstance(link_response, SettingsLinkResponse)
        link = link_response.settings_link
        self.assertIn("chat", link)
        self.assertIn(self.chat_config.chat_id.hex, link)
        self.assertIn("token=", link)

    def test_create_settings_link_failure_invalid_settings_type(self):
        controller = SettingsController(self.mock_di)

        with self.assertRaises(ValidationError) as context:
            controller.create_settings_link("invalid_type")

        self.assertIn("Invalid settings type", str(context.exception))

    def test_create_settings_link_chat_type_no_chat_context_falls_back_to_user(self):
        controller = SettingsController(self.mock_di)

        # noinspection PyPropertyAccess
        type(self.mock_di).invoker_chat = PropertyMock(return_value = None)
        link_response = controller.create_settings_link("chat")

        self.assertIsInstance(link_response, SettingsLinkResponse)
        link = link_response.settings_link
        self.assertIn("user", link)
        self.assertIn(self.invoker_user.id.hex, link)

    def test_fetch_user_settings_success(self):
        self.mock_user_dao.get.return_value = self.invoker_user

        controller = SettingsController(self.mock_di)
        result = controller.fetch_user_settings(self.invoker_user.id.hex)

        self.assertEqual(result.id, self.invoker_user.id.hex)
        self.assertEqual(result.full_name, self.invoker_user.full_name)
        self.assertEqual(result.telegram_username, self.invoker_user.telegram_username)
        self.assertEqual(result.telegram_chat_id, self.invoker_user.telegram_chat_id)
        self.assertEqual(result.telegram_user_id, self.invoker_user.telegram_user_id)
        self.assertEqual(result.group, self.invoker_user.group.value)
        self.assertFalse(result.is_sponsored)

    def test_fetch_user_settings_is_sponsored_true(self):
        mock_sponsorship = MagicMock()
        mock_sponsorship.receiver_id = self.invoker_user.id
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [mock_sponsorship]

        controller = SettingsController(self.mock_di)
        result = controller.fetch_user_settings(self.invoker_user.id.hex)

        self.assertTrue(result.is_sponsored)

    def test_fetch_user_settings_masks_all_token_fields(self):
        self.mock_user_dao.get.return_value = self.invoker_user

        controller = SettingsController(self.mock_di)
        result = controller.fetch_user_settings(self.invoker_user.id.hex)

        self.assertEqual(result.open_ai_key, mask_secret(self.invoker_user.open_ai_key))
        self.assertEqual(result.anthropic_key, mask_secret(self.invoker_user.anthropic_key))
        self.assertEqual(result.perplexity_key, mask_secret(self.invoker_user.perplexity_key))
        self.assertEqual(result.replicate_key, mask_secret(self.invoker_user.replicate_key))
        self.assertEqual(result.rapid_api_key, mask_secret(self.invoker_user.rapid_api_key))
        self.assertEqual(result.coinmarketcap_key, mask_secret(self.invoker_user.coinmarketcap_key))

    def test_save_user_settings_with_all_tokens(self):
        # Create a proper UserDB mock for the save return value
        saved_user_db = UserDB(
            id = self.invoker_user.id,
            full_name = self.invoker_user.full_name,
            telegram_username = self.invoker_user.telegram_username,
            telegram_chat_id = self.invoker_user.telegram_chat_id,
            telegram_user_id = self.invoker_user.telegram_user_id,
            connect_key = "SAVE-USER-KEY1",
            open_ai_key = SecretStr("new_openai_key"),
            anthropic_key = SecretStr("new_anthropic_key"),
            perplexity_key = SecretStr("new_perplexity_key"),
            replicate_key = SecretStr("new_replicate_key"),
            rapid_api_key = SecretStr("new_rapid_api_key"),
            coinmarketcap_key = SecretStr("new_coinmarketcap_key"),
            tool_choice_chat = CLAUDE_4_6_SONNET.id,
            tool_choice_reasoning = GPT_4O.id,
            tool_choice_vision = CLAUDE_4_6_SONNET.id,
            tool_choice_images_gen = IMAGE_GEN_FLUX_1_1.id,
            tool_choice_search = SONAR.id,
            group = self.invoker_user.group,
            created_at = self.invoker_user.created_at,
            credit_balance = 0.0,
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = True,
        )
        self.mock_user_dao.save.return_value = saved_user_db

        controller = SettingsController(self.mock_di)
        payload = UserSettingsPayload(
            open_ai_key = "new_openai_key",
            anthropic_key = "new_anthropic_key",
            perplexity_key = "new_perplexity_key",
            replicate_key = "new_replicate_key",
            rapid_api_key = "new_rapid_api_key",
            coinmarketcap_key = "new_coinmarketcap_key",
            tool_choice_chat = CLAUDE_4_6_SONNET.id,
            tool_choice_reasoning = GPT_4O.id,
            tool_choice_vision = CLAUDE_4_6_SONNET.id,
            tool_choice_images_gen = IMAGE_GEN_FLUX_1_1.id,
            tool_choice_search = SONAR.id,
        )

        # Should not raise any exception
        controller.save_user_settings(self.invoker_user.id.hex, payload)

        # Verify the save method was called
        # noinspection PyUnresolvedReferences
        self.mock_user_dao.save.assert_called_once()

    def test_save_user_settings_failure_invalid_tool_choice(self):
        controller = SettingsController(self.mock_di)
        payload = UserSettingsPayload(
            tool_choice_chat = "unconfigured-tool",
        )

        with self.assertRaises(ValidationError) as context:
            controller.save_user_settings(self.invoker_user.id.hex, payload)

        self.assertIn("Invalid tool choice", str(context.exception))
        self.assertIn("not recognized", str(context.exception))

    def test_save_user_settings_reject_policy_false(self):
        controller = SettingsController(self.mock_di)
        payload = UserSettingsPayload(are_policies_accepted = False)

        with self.assertRaises(ValidationError) as context:
            controller.save_user_settings(self.invoker_user.id.hex, payload)

        self.assertEqual(context.exception.error_code, POLICY_ACCEPTANCE_REVOCATION_FORBIDDEN)

    def test_save_user_settings_waitlisted_activation_when_capacity_available(self):
        waitlisted_user = self.invoker_user.model_copy(
            update = {
                "is_on_waitlist": True,
                "is_invited_to_start": False,
                "are_policies_accepted": False,
            },
        )
        self.mock_authorization_service.authorize_for_user.return_value = waitlisted_user
        self.mock_authorization_service.require_waitlisted_user_can_activate.return_value = waitlisted_user
        saved_user_db = UserDB(
            id = waitlisted_user.id,
            full_name = waitlisted_user.full_name,
            telegram_username = waitlisted_user.telegram_username,
            telegram_chat_id = waitlisted_user.telegram_chat_id,
            telegram_user_id = waitlisted_user.telegram_user_id,
            connect_key = "SAVE-USER-KEY2",
            group = waitlisted_user.group,
            created_at = waitlisted_user.created_at,
            credit_balance = waitlisted_user.credit_balance,
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = True,
        )
        self.mock_user_dao.save.return_value = saved_user_db

        controller = SettingsController(self.mock_di)
        payload = UserSettingsPayload(are_policies_accepted = True)
        controller.save_user_settings(waitlisted_user.id.hex, payload)

        self.mock_authorization_service.require_waitlisted_user_can_activate.assert_called_once_with(waitlisted_user)
        saved_payload = self.mock_user_dao.save.call_args.args[0]
        self.assertFalse(saved_payload.is_on_waitlist)
        self.assertFalse(saved_payload.is_invited_to_start)
        self.assertTrue(saved_payload.are_policies_accepted)

    def test_save_user_settings_waitlisted_activation_denied_without_invite_or_capacity(self):
        waitlisted_user = self.invoker_user.model_copy(
            update = {
                "is_on_waitlist": True,
                "is_invited_to_start": False,
                "are_policies_accepted": False,
            },
        )
        self.mock_authorization_service.authorize_for_user.return_value = waitlisted_user
        self.mock_authorization_service.require_waitlisted_user_can_activate.side_effect = AuthorizationError(
            "Activation is not available right now because maximum user capacity has been reached. "
            "Your account remains on the waitlist.",
            WAITLIST_ACCOUNT_NOT_ACTIVE,
        )
        controller = SettingsController(self.mock_di)
        payload = UserSettingsPayload(are_policies_accepted = True)

        with self.assertRaises(AuthorizationError) as context:
            controller.save_user_settings(waitlisted_user.id.hex, payload)

        self.assertEqual(context.exception.error_code, WAITLIST_ACCOUNT_NOT_ACTIVE)

    def test_save_chat_settings_failure_language_mismatch(self):
        controller = SettingsController(self.mock_di)
        payload = ChatSettingsPayload(
            chat_config = ChatConfigPayload(
                language_name = "",
                language_iso_code = "es",
                reply_chance_percent = 50,
                release_notifications = "all",
                media_mode = "photo",
            ),
        )

        with self.assertRaises(ValidationError) as context:
            controller.save_chat_settings(self.chat_config.chat_id.hex, payload)

        self.assertIn("Both language_name and language_iso_code must be non-empty", str(context.exception))

    def test_save_chat_settings_failure_reply_chance_private_chat(self):
        private_chat_config = ChatConfigDomain(
            chat_id = UUID(int = 123),
            external_id = "private_chat_123",
            title = "Private Chat",
            language_iso_code = "en",
            reply_chance_percent = 100,
            is_private = True,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.mock_authorization_service.validate_chat.return_value = private_chat_config

        controller = SettingsController(self.mock_di)
        payload = ChatSettingsPayload(
            chat_config = ChatConfigPayload(
                language_name = "English",
                language_iso_code = "en",
                reply_chance_percent = 50,
                release_notifications = "all",
                media_mode = "photo",
            ),
        )

        with self.assertRaises(ValidationError) as context:
            controller.save_chat_settings(private_chat_config.chat_id.hex, payload)

        self.assertIn("Chat is private, reply chance cannot be changed", str(context.exception))

    def test_save_chat_settings_failure_invalid_release_notifications(self):
        controller = SettingsController(self.mock_di)
        payload = ChatSettingsPayload(
            chat_config = ChatConfigPayload(
                language_name = "English",
                language_iso_code = "en",
                reply_chance_percent = 50,
                release_notifications = "invalid_value",
                media_mode = "photo",
            ),
        )

        with self.assertRaises(ValidationError) as context:
            controller.save_chat_settings(self.chat_config.chat_id.hex, payload)

        self.assertIn("Invalid release notifications setting value", str(context.exception))

    def test_save_chat_settings_success_chat_config(self):
        controller = SettingsController(self.mock_di)
        payload = ChatSettingsPayload(
            chat_config = ChatConfigPayload(
                language_name = "Spanish",
                language_iso_code = "es",
                reply_chance_percent = 75,
                release_notifications = "major",
                media_mode = "file",
            ),
        )

        controller.save_chat_settings(self.chat_config.chat_id.hex, payload)

        # noinspection PyUnresolvedReferences
        self.mock_chat_config_repo.save.assert_called_once()
        saved_chat_config = self.mock_chat_config_repo.save.call_args.args[0]
        self.assertIsInstance(saved_chat_config, ChatConfigDomain)
        self.assertEqual(saved_chat_config.chat_id, self.chat_config.chat_id)
        self.assertEqual(saved_chat_config.external_id, self.chat_config.external_id)
        self.assertEqual(saved_chat_config.title, self.chat_config.title)
        self.assertEqual(saved_chat_config.language_name, "Spanish")
        self.assertEqual(saved_chat_config.language_iso_code, "es")
        self.assertEqual(saved_chat_config.reply_chance_percent, 75)
        self.assertEqual(saved_chat_config.is_private, self.chat_config.is_private)
        self.assertEqual(saved_chat_config.release_notifications, ChatConfigDB.ReleaseNotifications.major)
        self.assertEqual(saved_chat_config.media_mode, ChatConfigDB.MediaMode.file)
        self.assertEqual(saved_chat_config.chat_type, self.chat_config.chat_type)

    def test_save_chat_settings_success_user_chat_config(self):
        controller = SettingsController(self.mock_di)
        payload = ChatSettingsPayload(
            user_chat_config = UserChatConfigPayload(
                use_about_me = False,
                use_custom_prompt = True,
                max_output_tokens = 500,
                max_chat_history_depth = 5,
                max_iterations = 3,
            ),
        )

        controller.save_chat_settings(self.chat_config.chat_id.hex, payload)

        # noinspection PyUnresolvedReferences
        self.mock_di.chat_membership_service.save.assert_called_once()
        saved = self.mock_di.chat_membership_service.save.call_args[0][0]
        self.assertFalse(saved.use_about_me)
        self.assertTrue(saved.use_custom_prompt)
        self.assertEqual(saved.max_output_tokens, 500)
        self.assertEqual(saved.max_chat_history_depth, 5)
        self.assertEqual(saved.max_iterations, 3)

    def test_save_chat_settings_failure_non_admin_chat_config_rejected(self):
        self.mock_authorization_service.validate_chat_admin.side_effect = AuthorizationError(
            "Not an admin of this chat",
            NOT_CHAT_ADMIN,
        )
        controller = SettingsController(self.mock_di)
        payload = ChatSettingsPayload(
            chat_config = ChatConfigPayload(
                language_name = "English",
                language_iso_code = "en",
                reply_chance_percent = 50,
                release_notifications = "all",
                media_mode = "photo",
            ),
        )

        with self.assertRaises(AuthorizationError) as context:
            controller.save_chat_settings(self.chat_config.chat_id.hex, payload)

        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)

    def test_save_chat_settings_rejects_empty_payload(self):
        controller = SettingsController(self.mock_di)
        payload = ChatSettingsPayload()

        with self.assertRaises(ValidationError):
            controller.save_chat_settings(self.chat_config.chat_id.hex, payload)

    def test_fetch_all_chat_settings_success(self):
        own_chat_config = ChatConfigDomain(
            chat_id = UUID(int = 2),
            external_id = str(self.invoker_user.telegram_chat_id),
            title = "My Notes",
            language_iso_code = "en",
            reply_chance_percent = 100,
            is_private = True,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        own_membership = ChatMembership(
            user_id = self.invoker_user.id,
            chat_id = own_chat_config.chat_id,
            is_admin = True,
            use_about_me = True,
            use_custom_prompt = True,
        )
        self.mock_authorization_service.update_all_chat_authorizations.return_value = [own_membership]
        self.mock_chat_config_repo.get.return_value = own_chat_config

        controller = SettingsController(self.mock_di)
        result = controller.fetch_all_chat_settings()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].chat_config.chat_id, own_chat_config.chat_id.hex)
        self.assertEqual(result[0].chat_config.title, "My Notes")
        self.assertTrue(result[0].chat_config.is_own)
        self.assertEqual(result[0].chat_config.platform, "telegram")
        self.assertIsNotNone(result[0].user_chat_config)

    def test_fetch_all_chat_settings_sort_order(self):
        private_config = ChatConfigDomain(
            chat_id = UUID(int = 1),
            title = "Private",
            language_iso_code = "en",
            reply_chance_percent = 100,
            is_private = True,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        admin_config = ChatConfigDomain(
            chat_id = UUID(int = 2),
            title = "Admin Group",
            language_iso_code = "en",
            reply_chance_percent = 50,
            is_private = False,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        member_config = ChatConfigDomain(
            chat_id = UUID(int = 3),
            title = "Member Group",
            language_iso_code = "en",
            reply_chance_percent = 50,
            is_private = False,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        private_membership = ChatMembership(
            user_id = self.invoker_user.id,
            chat_id = private_config.chat_id,
            is_admin = True,
            use_about_me = False,
            use_custom_prompt = False,
        )
        admin_membership = ChatMembership(
            user_id = self.invoker_user.id,
            chat_id = admin_config.chat_id,
            is_admin = True,
            use_about_me = False,
            use_custom_prompt = False,
        )
        member_membership = ChatMembership(
            user_id = self.invoker_user.id,
            chat_id = member_config.chat_id,
            is_admin = False,
            use_about_me = False,
            use_custom_prompt = False,
        )
        self.mock_authorization_service.update_all_chat_authorizations.return_value = [
            member_membership, admin_membership, private_membership,
        ]
        config_map = {
            private_config.chat_id: private_config,
            admin_config.chat_id: admin_config,
            member_config.chat_id: member_config,
        }
        self.mock_chat_config_repo.get.side_effect = lambda chat_id: config_map[chat_id]

        controller = SettingsController(self.mock_di)
        result = controller.fetch_all_chat_settings()

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].chat_config.chat_id, private_config.chat_id.hex)
        self.assertEqual(result[1].chat_config.chat_id, admin_config.chat_id.hex)
        self.assertEqual(result[2].chat_config.chat_id, member_config.chat_id.hex)

    def test_fetch_all_chat_settings_empty_memberships(self):
        self.mock_authorization_service.update_all_chat_authorizations.return_value = []

        controller = SettingsController(self.mock_di)
        result = controller.fetch_all_chat_settings()

        self.assertEqual(len(result), 0)

    # === fetch_chat_settings ===

    def test_fetch_chat_settings_success(self):
        self.mock_authorization_service.update_chat_authorization.return_value = self.membership

        controller = SettingsController(self.mock_di)
        result = controller.fetch_chat_settings(self.chat_config.chat_id.hex)

        self.mock_authorization_service.update_chat_authorization.assert_called_once_with(
            self.invoker_user, self.chat_config,
        )
        self.assertIsNotNone(result)

    def test_create_settings_link_with_sponsorship(self):
        mock_sponsorship_db = MagicMock()
        mock_sponsorship_db.receiver_id = self.invoker_user.id

        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [mock_sponsorship_db]

        controller = SettingsController(self.mock_di)
        link_response = controller.create_settings_link()
        self.assertIsInstance(link_response, SettingsLinkResponse)
        link = link_response.settings_link

        self.assertIn("sponsorships", link)
        self.assertIn("user", link)
        self.assertIn(self.invoker_user.id.hex, link)
        self.assertIn("token=", link)

        raw_token = link.split("token=")[1]
        payload_b64 = raw_token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
        self.assertNotIn("sponsored_by", payload)

    def test_create_settings_link_no_telegram_chat_id(self):
        user_without_chat = User(
            id = self.invoker_user.id,
            full_name = self.invoker_user.full_name,
            telegram_username = self.invoker_user.telegram_username,
            telegram_chat_id = None,  # No chat ID
            telegram_user_id = None,  # No user ID
            open_ai_key = self.invoker_user.open_ai_key,
            anthropic_key = self.invoker_user.anthropic_key,
            perplexity_key = self.invoker_user.perplexity_key,
            replicate_key = self.invoker_user.replicate_key,
            rapid_api_key = self.invoker_user.rapid_api_key,
            coinmarketcap_key = self.invoker_user.coinmarketcap_key,
            tool_choice_chat = self.invoker_user.tool_choice_chat,
            tool_choice_reasoning = self.invoker_user.tool_choice_reasoning,
            tool_choice_vision = self.invoker_user.tool_choice_vision,
            tool_choice_images_gen = self.invoker_user.tool_choice_images_gen,
            tool_choice_search = self.invoker_user.tool_choice_search,
            group = self.invoker_user.group,
            created_at = self.invoker_user.created_at,
        )

        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = user_without_chat)
        controller = SettingsController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.create_settings_link()

        self.assertIn("User never sent a private message, cannot create a settings link", str(context.exception))

    def test_fetch_external_tools_success_mixed_configuration(self):
        # Create mock tools and providers
        mock_tool_1 = ExternalTool(
            id = "configured-tool",
            name = "Configured Tool",
            provider = ExternalToolProvider(
                id = "configured-provider",
                name = "Configured Provider",
                token_management_url = "https://example.com",
                token_format = "test-format",
                tools = ["configured-tool"],
            ),
            types = [ToolType.chat],
            cost_estimate = CostEstimate(),
        )
        mock_tool_2 = ExternalTool(
            id = "unconfigured-tool",
            name = "Unconfigured Tool",
            provider = ExternalToolProvider(
                id = "unconfigured-provider",
                name = "Unconfigured Provider",
                token_management_url = "https://example.com",
                token_format = "test-format",
                tools = ["unconfigured-tool"],
            ),
            types = [ToolType.vision],
            cost_estimate = CostEstimate(),
        )
        mock_provider_1 = ExternalToolProvider(
            id = "configured-provider",
            name = "Configured Provider",
            token_management_url = "https://example.com",
            token_format = "test-format",
            tools = ["configured-tool"],
        )
        mock_provider_2 = ExternalToolProvider(
            id = "unconfigured-provider",
            name = "Unconfigured Provider",
            token_management_url = "https://example.com",
            token_format = "test-format",
            tools = ["unconfigured-tool"],
        )

        # Mock the clone method to return a new DI instance
        cloned_di = MagicMock(spec = DI)
        cloned_access_token_resolver = MagicMock()
        cloned_di.access_token_resolver = cloned_access_token_resolver
        self.mock_di.clone.return_value = cloned_di

        # Configure some tools as available, some as not
        def mock_get_token_for_tool(tool):
            return SecretStr("test-token") if tool.id == "configured-tool" else None

        def mock_get_token(provider):
            return SecretStr("test-token") if provider.id == "configured-provider" else None

        cloned_access_token_resolver.get_access_token_for_tool.side_effect = mock_get_token_for_tool
        cloned_access_token_resolver.get_access_token.side_effect = mock_get_token

        with patch("api.settings_controller.ALL_EXTERNAL_TOOLS", [mock_tool_1, mock_tool_2]):
            with patch("api.settings_controller.ALL_PROVIDERS", [mock_provider_1, mock_provider_2]):
                controller = SettingsController(self.mock_di)
                result = controller.fetch_external_tools(self.invoker_user.id.hex)

        # Verify result structure
        self.assertEqual(len(result.tools), 2)
        self.assertEqual(len(result.providers), 2)

        # Verify mixed configuration
        configured_tools = [tool for tool in result.tools if tool.is_configured]
        unconfigured_tools = [tool for tool in result.tools if not tool.is_configured]
        self.assertEqual(len(configured_tools), 1)
        self.assertEqual(len(unconfigured_tools), 1)

        configured_providers = [provider for provider in result.providers if provider.is_configured]
        unconfigured_providers = [provider for provider in result.providers if not provider.is_configured]
        self.assertEqual(len(configured_providers), 1)
        self.assertEqual(len(unconfigured_providers), 1)

        # Verify presets are included with actual content
        self.assertIn("lowest_price", result.presets)
        self.assertIn("highest_price", result.presets)
        self.assertIn("agent_choice", result.presets)

        # Verify preset contents are non-empty dicts with tool type -> tool ID mappings
        for preset_name, preset_choices in result.presets.items():
            self.assertIsInstance(preset_choices, dict, f"Preset {preset_name} should be a dict")
            self.assertGreater(len(preset_choices), 0, f"Preset {preset_name} should not be empty")
            for tool_type, tool_id in preset_choices.items():
                self.assertIsInstance(tool_type, str, f"Tool type in {preset_name} should be str")
                self.assertIsInstance(tool_id, str, f"Tool ID in {preset_name} should be str")
                self.assertGreater(len(tool_id), 0, f"Tool ID in {preset_name}.{tool_type} should not be empty")

    def test_fetch_external_tools_includes_cost_estimate(self):
        """Verify that cost_estimate is properly serialized in API response"""
        # Create tool with actual cost estimate values
        mock_provider = ExternalToolProvider(
            id = "test-provider",
            name = "Test Provider",
            token_management_url = "https://example.com",
            token_format = "test-format",
            tools = ["test-tool"],
        )
        mock_tool = ExternalTool(
            id = "test-tool",
            name = "Test Tool",
            provider = mock_provider,
            types = [ToolType.chat],
            cost_estimate = CostEstimate(
                input_1m_tokens = 100,
                output_1m_tokens = 500,
                search_1m_tokens = 300,
                output_image_1k = 10,
                api_call = 5,
                second_of_runtime = 0.01,
                web_search_query = 1.4,
            ),
        )

        cloned_di = MagicMock(spec = DI)
        cloned_access_token_resolver = MagicMock()
        cloned_di.access_token_resolver = cloned_access_token_resolver
        self.mock_di.clone.return_value = cloned_di
        cloned_access_token_resolver.get_access_token.return_value = None

        with patch("api.settings_controller.ALL_EXTERNAL_TOOLS", [mock_tool]):
            with patch("api.settings_controller.ALL_PROVIDERS", [mock_provider]):
                controller = SettingsController(self.mock_di)
                result = controller.fetch_external_tools(self.invoker_user.id.hex)

        # Verify cost_estimate is in response
        self.assertEqual(len(result.tools), 1)
        tool_response = result.tools[0]

        cost_est = tool_response.definition.cost_estimate
        self.assertIsNotNone(cost_est)
        self.assertEqual(cost_est.input_1m_tokens, 100)
        self.assertEqual(cost_est.output_1m_tokens, 500)
        self.assertEqual(cost_est.search_1m_tokens, 300)
        self.assertEqual(cost_est.output_image_1k, 10)
        self.assertIsNone(cost_est.output_image_2k)
        self.assertIsNone(cost_est.output_image_4k)
        self.assertEqual(cost_est.api_call, 5)
        self.assertEqual(cost_est.second_of_runtime, 0.01)
        self.assertEqual(cost_est.web_search_query, 1.4)

    @patch("api.auth.create_jwt_token")
    def test_create_help_link_success(self, mock_create_jwt_token):
        mock_create_jwt_token.return_value = "test_jwt_token"

        controller = SettingsController(self.mock_di)
        link = controller.create_help_link()

        self.assertIn("features", link)
        self.assertIn("token=", link)
        self.assertIn("en", link)  # Default language
        mock_create_jwt_token.assert_called_once()

    @patch("api.auth.create_jwt_token")
    def test_create_help_link_success_with_custom_language(self, mock_create_jwt_token):
        mock_create_jwt_token.return_value = "test_jwt_token"

        controller = SettingsController(self.mock_di)
        link = controller.create_help_link()

        self.assertIn("features", link)
        self.assertIn("token=", link)
        self.assertIn("es", link)  # Custom language
        mock_create_jwt_token.assert_called_once()

    def test_create_help_link_failure_no_telegram_chat_id(self):
        user_without_chat = User(
            id = self.invoker_user.id,
            full_name = self.invoker_user.full_name,
            telegram_username = self.invoker_user.telegram_username,
            telegram_chat_id = None,  # No chat ID
            telegram_user_id = None,  # No user ID
            open_ai_key = self.invoker_user.open_ai_key,
            anthropic_key = self.invoker_user.anthropic_key,
            perplexity_key = self.invoker_user.perplexity_key,
            replicate_key = self.invoker_user.replicate_key,
            rapid_api_key = self.invoker_user.rapid_api_key,
            coinmarketcap_key = self.invoker_user.coinmarketcap_key,
            tool_choice_chat = self.invoker_user.tool_choice_chat,
            tool_choice_reasoning = self.invoker_user.tool_choice_reasoning,
            tool_choice_vision = self.invoker_user.tool_choice_vision,
            tool_choice_images_gen = self.invoker_user.tool_choice_images_gen,
            tool_choice_search = self.invoker_user.tool_choice_search,
            group = self.invoker_user.group,
            created_at = self.invoker_user.created_at,
        )

        # noinspection PyPropertyAccess
        type(self.mock_di).invoker = PropertyMock(return_value = user_without_chat)
        controller = SettingsController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.create_help_link()

        self.assertIn("User never sent a private message, cannot create settings link", str(context.exception))

    def test_fetch_external_tools_sorts_by_provider_order_then_name(self):
        """Verify that tools are sorted by provider order first, then by tool name"""
        # Create providers in specific order
        provider_a = ExternalToolProvider(
            id = "provider-a",
            name = "Provider A",
            token_management_url = "https://example.com",
            token_format = "test-format",
            tools = ["tool-a1", "tool-a2"],
        )
        provider_b = ExternalToolProvider(
            id = "provider-b",
            name = "Provider B",
            token_management_url = "https://example.com",
            token_format = "test-format",
            tools = ["tool-b1", "tool-b2"],
        )

        # Create tools, intentionally out of order
        # Tools for Provider A: tool-a2, tool-a1 (wrong order)
        tool_a2 = ExternalTool(
            id = "tool-a2",
            name = "Tool A2",
            provider = provider_a,
            types = [ToolType.chat],
            cost_estimate = CostEstimate(),
        )
        tool_a1 = ExternalTool(
            id = "tool-a1",
            name = "Tool A1",
            provider = provider_a,
            types = [ToolType.chat],
            cost_estimate = CostEstimate(),
        )
        # Tools for Provider B: tool-b2, tool-b1 (wrong order)
        tool_b2 = ExternalTool(
            id = "tool-b2",
            name = "Tool B2",
            provider = provider_b,
            types = [ToolType.chat],
            cost_estimate = CostEstimate(),
        )
        tool_b1 = ExternalTool(
            id = "tool-b1",
            name = "Tool B1",
            provider = provider_b,
            types = [ToolType.chat],
            cost_estimate = CostEstimate(),
        )

        # Mock the clone method to return a new DI instance
        cloned_di = MagicMock(spec = DI)
        cloned_access_token_resolver = MagicMock()
        cloned_di.access_token_resolver = cloned_access_token_resolver
        self.mock_di.clone.return_value = cloned_di

        # All tools and providers are configured
        cloned_access_token_resolver.get_access_token.return_value = SecretStr("test-token")

        with patch("api.settings_controller.ALL_EXTERNAL_TOOLS", [tool_a2, tool_a1, tool_b2, tool_b1]):
            with patch("api.settings_controller.ALL_PROVIDERS", [provider_a, provider_b]):
                controller = SettingsController(self.mock_di)
                result = controller.fetch_external_tools(self.invoker_user.id.hex)

        # Verify result structure
        self.assertEqual(len(result.tools), 4)

        # Extract tool IDs and check sorting
        tool_ids = [tool.definition.id for tool in result.tools]

        # Expected order: Provider A tools first (sorted by name), then Provider B tools (sorted by name)
        expected_order = ["tool-a1", "tool-a2", "tool-b1", "tool-b2"]
        self.assertEqual(tool_ids, expected_order, f"Tools not sorted correctly. Got {tool_ids}, expected {expected_order}")

    def test_fetch_external_tools_uses_provider_configuration_cache(self):
        """Verify that tool configuration is determined from provider configuration (not checked per tool)"""
        provider = ExternalToolProvider(
            id = "test-provider",
            name = "Test Provider",
            token_management_url = "https://example.com",
            token_format = "test-format",
            tools = ["tool-1", "tool-2", "tool-3"],
        )

        # Create three tools under the same provider
        tools = [
            ExternalTool(
                id = f"tool-{i}",
                name = f"Tool {i}",
                provider = provider,
                types = [ToolType.chat],
                cost_estimate = CostEstimate(),
            )
            for i in range(1, 4)
        ]

        cloned_di = MagicMock(spec = DI)
        cloned_access_token_resolver = MagicMock()
        cloned_di.access_token_resolver = cloned_access_token_resolver
        self.mock_di.clone.return_value = cloned_di

        # Provider is configured
        cloned_access_token_resolver.get_access_token.return_value = SecretStr("test-token")

        with patch("api.settings_controller.ALL_EXTERNAL_TOOLS", tools):
            with patch("api.settings_controller.ALL_PROVIDERS", [provider]):
                controller = SettingsController(self.mock_di)
                result = controller.fetch_external_tools(self.invoker_user.id.hex)

        # Verify all tools have the same configuration status as the provider
        for tool in result.tools:
            self.assertTrue(tool.is_configured, "All tools should be configured since provider is configured")

        # Verify get_access_token was called only once for the provider
        # (not three times for each tool)
        call_count = sum(
            1 for call in cloned_access_token_resolver.get_access_token.call_args_list
            if call[0][0].id == provider.id
        )
        self.assertEqual(call_count, 1, "Provider configuration should be checked only once, not per tool")

    def test_fetch_products_success(self):
        mock_products = {
            "prod-1": ConfiguredProduct(id = "prod-1", credits = 100, name = "Starter Pack", url = "https://example.com/prod-1"),
            "prod-2": ConfiguredProduct(id = "prod-2", credits = 500, name = "Pro Pack", url = "https://example.com/prod-2"),
        }

        with patch("api.settings_controller.config") as mock_config:
            mock_config.products = mock_products
            controller = SettingsController(self.mock_di)
            result = controller.fetch_products(self.invoker_user.id.hex)

        self.mock_authorization_service.authorize_for_user.assert_called_once_with(
            self.invoker_user,
            self.invoker_user.id.hex,
        )
        self.assertEqual(len(result.products), 2)
        product_ids = {p.id for p in result.products}
        self.assertEqual(product_ids, {"prod-1", "prod-2"})
        starter = next(p for p in result.products if p.id == "prod-1")
        self.assertEqual(starter.credits, 100)
        self.assertEqual(starter.name, "Starter Pack")
        self.assertEqual(starter.url, f"https://example.com/prod-1?user_id={self.invoker_user.id.hex}")
