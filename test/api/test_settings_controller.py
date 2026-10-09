from dataclasses import replace
from datetime import date
from typing import cast
from unittest import TestCase
from uuid import uuid4

import stubs
from fakes.fake_chat_model import FakeChatModel
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_url_shortener import FakeUrlShortener
from util.di_utils import di_for_tests

from api.auth import verify_jwt_token
from api.settings_controller import SettingsController
from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import (
    ALL_EXTERNAL_TOOLS,
    CLAUDE_4_6_SONNET,
    GPT_5_5,
    IMAGE_GEN_EDIT_FLUX_2_PRO,
    SONAR,
    TWELVE_DATA_STOCK_QUOTE,
    VIDEO_GEN_P_VIDEO,
)
from features.external_tools.external_tool_provider_library import ALL_PROVIDERS, ANTHROPIC, OPEN_AI
from features.external_tools.intelligence_presets import default_tool_for
from features.integrations.integration_config import THE_AGENT
from features.users.user import User
from util.config import config
from util.error_codes import (
    EMPTY_CHAT_SETTINGS_PAYLOAD,
    INVALID_LANGUAGE_SETTINGS,
    INVALID_RELEASE_NOTIFICATIONS,
    INVALID_REPLY_CHANCE,
    INVALID_SETTINGS_TYPE,
    NO_PRIVATE_CHAT,
    NOT_CHAT_ADMIN,
    POLICY_ACCEPTANCE_REQUIRED,
    WAITLIST_ACCOUNT_NOT_ACTIVE,
)
from util.errors import AuthorizationError, ValidationError
from util.functions import mask_secret


class SettingsControllerTest(TestCase):

    di: DI
    controller: SettingsController
    user: User
    chat: ChatConfig
    agent: User
    model: FakeChatModel
    bot: FakeTelegramBotAPI
    shortener: FakeUrlShortener

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user(created_at = date.today()))
        self.chat = self.di.chat_config_repo.save(stubs.domain.chat_config(is_private = False))
        self.agent = self.di.user_repo.save(stubs.domain.user(
            id = THE_AGENT.id, telegram_user_id = None, whatsapp_user_id = None, connect_key = "AGENT-KEY",
        ))
        self.di.inject_invoker(self.user)
        self.di.inject_invoker_chat(self.chat)
        self.bot = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        tool = self.di.tool_choice_resolver.require_tool(ToolType.copywriting, default_tool_for(ToolType.copywriting))
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(tool))
        self.bot.members[(self.chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_administrator()
        self.shortener = cast(FakeUrlShortener, self.di.url_shortener("https://example.com/settings"))
        self.controller = self.di.settings_controller

    def __save_private_notification_chat(self, user: User) -> ChatConfig:
        assert user.telegram_chat_id is not None
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = None,
            external_id = user.telegram_chat_id,
            is_private = True,
        ))
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(
            chat_id = chat.chat_id,
            user_id = user.id,
        ))
        return chat

    def test_create_settings_link_default_is_intelligence(self):
        result = self.controller.create_settings_link()

        self.assertEqual(result.settings_link, self.shortener.short_url)
        url = self.shortener.requested_urls[-1]
        self.assertTrue(url.startswith(f"{config.backoffice_url_base}/en/user/{self.user.id.hex}/intelligence?token="))
        claims = verify_jwt_token(url.split("token=")[1])
        self.assertEqual(claims["sub"], self.user.id.hex)
        self.assertEqual(claims["platform"], "telegram")
        self.assertEqual(claims["platform_id"], str(self.user.telegram_user_id))
        self.assertEqual(claims["platform_handle"], self.user.telegram_username)

    def test_create_settings_link_success_user_settings(self):
        result = self.controller.create_settings_link("user")

        self.assertEqual(result.settings_link, self.shortener.short_url)
        self.assertTrue(self.shortener.requested_urls[-1].startswith(
            f"{config.backoffice_url_base}/en/user/{self.user.id.hex}/settings?token=",
        ))

    def test_create_settings_link_success_chat_settings(self):
        result = self.controller.create_settings_link("chat")

        self.assertEqual(result.settings_link, self.shortener.short_url)
        self.assertTrue(self.shortener.requested_urls[-1].startswith(
            f"{config.backoffice_url_base}/en/chat/{self.chat.chat_id.hex}/settings?token=",
        ))

    def test_create_settings_link_failure_invalid_settings_type(self):
        with self.assertRaises(ValidationError) as context:
            self.controller.create_settings_link("invalid_type")

        self.assertEqual(context.exception.error_code, INVALID_SETTINGS_TYPE)

    def test_create_settings_link_chat_type_no_chat_context_falls_back_to_user(self):
        self.di.inject_invoker_chat(None)

        result = self.controller.create_settings_link("chat", chat_type = ChatConfigDB.ChatType.telegram)

        self.assertEqual(result.settings_link, self.shortener.short_url)
        self.assertTrue(self.shortener.requested_urls[-1].startswith(
            f"{config.backoffice_url_base}/{config.main_language_iso_code}/user/{self.user.id.hex}/intelligence?token=",
        ))

    def test_fetch_user_settings_success(self):
        invoker_user = self.user

        controller = self.controller
        result = controller.fetch_user_settings(invoker_user.id.hex)

        self.assertEqual(result.id, invoker_user.id.hex)
        self.assertEqual(result.full_name, invoker_user.full_name)
        self.assertEqual(result.telegram_username, invoker_user.telegram_username)
        self.assertEqual(result.telegram_chat_id, invoker_user.telegram_chat_id)
        self.assertEqual(result.telegram_user_id, invoker_user.telegram_user_id)
        self.assertEqual(result.group, invoker_user.group.value)
        self.assertEqual(result.tool_choice_videos_gen, invoker_user.tool_choice_videos_gen)
        self.assertFalse(result.is_sponsored)

    def test_fetch_user_settings_masks_all_token_fields(self):
        invoker_user = self.user

        controller = self.controller
        result = controller.fetch_user_settings(invoker_user.id.hex)

        self.assertEqual(result.open_ai_key, mask_secret(invoker_user.open_ai_key))
        self.assertEqual(result.anthropic_key, mask_secret(invoker_user.anthropic_key))
        self.assertEqual(result.google_ai_key, mask_secret(invoker_user.google_ai_key))
        self.assertEqual(result.perplexity_key, mask_secret(invoker_user.perplexity_key))
        self.assertEqual(result.replicate_key, mask_secret(invoker_user.replicate_key))
        self.assertEqual(result.rapid_api_key, mask_secret(invoker_user.rapid_api_key))
        self.assertEqual(result.coinmarketcap_key, mask_secret(invoker_user.coinmarketcap_key))
        self.assertEqual(result.twelve_data_api_key, mask_secret(invoker_user.twelve_data_api_key))
        self.assertEqual(result.x_key, mask_secret(invoker_user.x_key))
        self.assertEqual(result.x_ai_key, mask_secret(invoker_user.x_ai_key))
        self.assertEqual(result.tool_choice_api_stock_quote, invoker_user.tool_choice_api_stock_quote)

    def test_save_user_settings_updates_all_tokens_and_selected_tool_choices(self):
        invoker_user = self.user

        controller = self.controller
        payload = stubs.api.user_settings_payload(
            full_name = None,
            about_me = None,
            custom_prompt = None,
            open_ai_key = "new_openai_key",
            anthropic_key = "new_anthropic_key",
            google_ai_key = "new_google_ai_key",
            perplexity_key = "new_perplexity_key",
            replicate_key = "new_replicate_key",
            rapid_api_key = "new_rapid_api_key",
            coinmarketcap_key = "new_coinmarketcap_key",
            twelve_data_api_key = "new_twelve_data_api_key",
            x_key = "new_x_key",
            x_ai_key = "new_x_ai_key",
            tool_choice_chat = CLAUDE_4_6_SONNET.id,
            tool_choice_reasoning = GPT_5_5.id,
            tool_choice_copywriting = None,
            tool_choice_vision = CLAUDE_4_6_SONNET.id,
            tool_choice_hearing = None,
            tool_choice_images_gen = IMAGE_GEN_EDIT_FLUX_2_PRO.id,
            tool_choice_videos_gen = VIDEO_GEN_P_VIDEO.id,
            tool_choice_search = SONAR.id,
            tool_choice_embedding = None,
            tool_choice_api_fiat_exchange = None,
            tool_choice_api_crypto_exchange = None,
            tool_choice_api_stock_quote = TWELVE_DATA_STOCK_QUOTE.id,
            tool_choice_api_twitter = None,
            are_policies_accepted = None,
        )

        controller.save_user_settings(invoker_user.id.hex, payload)

        saved_user = self.di.user_repo.get(self.user.id)
        self.assertEqual(saved_user.full_name, invoker_user.full_name)
        self.assertEqual(saved_user.about_me, invoker_user.about_me)
        self.assertEqual(saved_user.custom_prompt, invoker_user.custom_prompt)
        self.assertEqual(saved_user.open_ai_key.get_secret_value(), "new_openai_key")
        self.assertEqual(saved_user.anthropic_key.get_secret_value(), "new_anthropic_key")
        self.assertEqual(saved_user.google_ai_key.get_secret_value(), "new_google_ai_key")
        self.assertEqual(saved_user.perplexity_key.get_secret_value(), "new_perplexity_key")
        self.assertEqual(saved_user.replicate_key.get_secret_value(), "new_replicate_key")
        self.assertEqual(saved_user.rapid_api_key.get_secret_value(), "new_rapid_api_key")
        self.assertEqual(saved_user.coinmarketcap_key.get_secret_value(), "new_coinmarketcap_key")
        self.assertEqual(saved_user.twelve_data_api_key.get_secret_value(), "new_twelve_data_api_key")
        self.assertEqual(saved_user.x_key.get_secret_value(), "new_x_key")
        self.assertEqual(saved_user.x_ai_key.get_secret_value(), "new_x_ai_key")
        self.assertEqual(saved_user.tool_choice_chat, payload.tool_choice_chat)
        self.assertEqual(saved_user.tool_choice_reasoning, payload.tool_choice_reasoning)
        self.assertEqual(saved_user.tool_choice_copywriting, invoker_user.tool_choice_copywriting)
        self.assertEqual(saved_user.tool_choice_vision, payload.tool_choice_vision)
        self.assertEqual(saved_user.tool_choice_hearing, invoker_user.tool_choice_hearing)
        self.assertEqual(saved_user.tool_choice_images_gen, payload.tool_choice_images_gen)
        self.assertEqual(saved_user.tool_choice_videos_gen, payload.tool_choice_videos_gen)
        self.assertEqual(saved_user.tool_choice_search, payload.tool_choice_search)
        self.assertEqual(saved_user.tool_choice_embedding, invoker_user.tool_choice_embedding)
        self.assertEqual(saved_user.tool_choice_api_fiat_exchange, invoker_user.tool_choice_api_fiat_exchange)
        self.assertEqual(saved_user.tool_choice_api_crypto_exchange, invoker_user.tool_choice_api_crypto_exchange)
        self.assertEqual(saved_user.tool_choice_api_stock_quote, payload.tool_choice_api_stock_quote)
        self.assertEqual(saved_user.tool_choice_api_twitter, invoker_user.tool_choice_api_twitter)
        self.assertEqual(saved_user.are_policies_accepted, invoker_user.are_policies_accepted)

    def test_save_user_settings_failure_invalid_tool_choice(self):
        invoker_user = self.user

        controller = self.controller
        payload = stubs.api.user_settings_payload(
            tool_choice_chat = "unconfigured-tool",
        )

        with self.assertRaises(ValidationError) as context:
            controller.save_user_settings(invoker_user.id.hex, payload)

        self.assertIn("Invalid tool choice", str(context.exception))
        self.assertIn("not recognized", str(context.exception))

    def test_save_user_settings_reject_policy_false(self):
        invoker_user = self.user

        controller = self.controller
        payload = stubs.api.user_settings_payload(are_policies_accepted = False)

        with self.assertRaises(ValidationError) as context:
            controller.save_user_settings(invoker_user.id.hex, payload)

        self.assertEqual(context.exception.error_code, POLICY_ACCEPTANCE_REQUIRED)

    def test_fetch_user_settings_is_sponsored_true(self):
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(sponsor_id = self.agent.id, receiver_id = self.user.id))

        self.assertTrue(self.controller.fetch_user_settings(self.user.id.hex).is_sponsored)

    def test_save_user_settings_requires_policy_acceptance_before_other_changes(self):
        user = self.di.user_repo.save(replace(self.user, are_policies_accepted = False))
        payload = stubs.api.user_settings_payload(full_name = "New Name", are_policies_accepted = None)

        with self.assertRaises(ValidationError) as context:
            self.controller.save_user_settings(user.id.hex, payload)

        self.assertEqual(context.exception.error_code, POLICY_ACCEPTANCE_REQUIRED)
        self.assertEqual(self.di.user_repo.get(user.id), user)

    def test_save_user_settings_waitlisted_activation_when_capacity_available(self):
        user = self.di.user_repo.save(replace(
            self.user, is_on_waitlist = True, is_invited_to_start = False, are_policies_accepted = False,
        ))
        self.addCleanup(setattr, config, "max_users", config.max_users)
        config.max_users = 3

        self.controller.save_user_settings(user.id.hex, stubs.api.user_settings_payload())

        result = self.controller.fetch_user_settings(user.id.hex)
        self.assertFalse(result.is_on_waitlist)
        self.assertFalse(result.is_invited_to_start)
        self.assertTrue(result.are_policies_accepted)
        self.assertEqual(result.credit_balance, user.credit_balance)

    def test_save_user_settings_waitlisted_activation_denied_without_invite_or_capacity(self):
        user = self.di.user_repo.save(replace(
            self.user, is_on_waitlist = True, is_invited_to_start = False, are_policies_accepted = False,
        ))
        self.addCleanup(setattr, config, "max_users", config.max_users)
        config.max_users = 2

        with self.assertRaises(AuthorizationError) as context:
            self.controller.save_user_settings(user.id.hex, stubs.api.user_settings_payload())

        self.assertEqual(context.exception.error_code, WAITLIST_ACCOUNT_NOT_ACTIVE)
        self.assertEqual(self.di.user_repo.get(user.id), user)

    def test_save_user_settings_accepts_eula_without_granting_again_and_notifies_once(self):
        user = self.di.user_repo.save(replace(self.user, are_policies_accepted = False))
        private_chat = self.__save_private_notification_chat(user)
        self.model.responses.append(stubs.external.ai_message(content = "Welcome credits granted."))

        self.controller.save_user_settings(user.id.hex, stubs.api.user_settings_payload())
        self.controller.save_user_settings(user.id.hex, stubs.api.user_settings_payload())

        result = self.controller.fetch_user_settings(user.id.hex)
        self.assertTrue(result.are_policies_accepted)
        self.assertEqual(result.credit_balance, user.credit_balance)
        self.assertEqual(self.di.user_repo.get(self.agent.id).credit_balance, self.agent.credit_balance)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.agent.id, only_transfers = True), [])
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(
            self.model.prompts[0][-1].content,
            f"You have been granted {config.welcome_credit_grant_amount} credits for \"Welcome\". Enjoy!",
        )
        self.assertEqual(
            [message["text"] for message in self.bot.get_sent_messages(str(private_chat.external_id))],
            ["Welcome credits granted."],
        )

    def test_save_user_settings_acceptance_notifies_after_credits_were_spent(self):
        user = self.di.user_repo.save(replace(
            self.user,
            are_policies_accepted = False,
            credit_balance = 1.0,
        ))
        private_chat = self.__save_private_notification_chat(user)
        self.model.responses.append(stubs.external.ai_message(content = "Welcome credits granted."))

        self.controller.save_user_settings(user.id.hex, stubs.api.user_settings_payload())

        result = self.controller.fetch_user_settings(user.id.hex)
        self.assertTrue(result.are_policies_accepted)
        self.assertEqual(result.credit_balance, user.credit_balance)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.agent.id, only_transfers = True), [])
        self.assertEqual(len(self.model.prompts), 1)
        self.assertEqual(
            [message["text"] for message in self.bot.get_sent_messages(str(private_chat.external_id))],
            ["Welcome credits granted."],
        )

    def test_save_user_settings_repeated_acceptance_does_not_notify(self):
        private_chat = self.__save_private_notification_chat(self.user)
        self.model.responses.append(stubs.external.ai_message(content = "Unexpected notification"))

        self.controller.save_user_settings(self.user.id.hex, stubs.api.user_settings_payload())

        self.assertEqual(self.controller.fetch_user_settings(self.user.id.hex).credit_balance, self.user.credit_balance)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.agent.id, only_transfers = True), [])
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.bot.get_sent_messages(str(private_chat.external_id)), [])

    def test_save_user_settings_acceptance_with_zero_welcome_amount_does_not_notify(self):
        self.addCleanup(setattr, config, "welcome_credit_grant_amount", config.welcome_credit_grant_amount)
        config.welcome_credit_grant_amount = 0.0
        user = self.di.user_repo.save(replace(self.user, are_policies_accepted = False))
        private_chat = self.__save_private_notification_chat(user)
        self.model.responses.append(stubs.external.ai_message(content = "Unexpected notification"))

        self.controller.save_user_settings(user.id.hex, stubs.api.user_settings_payload())

        result = self.controller.fetch_user_settings(user.id.hex)
        self.assertTrue(result.are_policies_accepted)
        self.assertEqual(result.credit_balance, user.credit_balance)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.agent.id, only_transfers = True), [])
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.bot.get_sent_messages(str(private_chat.external_id)), [])

    def test_save_user_settings_without_eula_acceptance_does_not_grant_credits(self):
        payload = stubs.api.user_settings_payload(full_name = "New Name", are_policies_accepted = None)

        self.controller.save_user_settings(self.user.id.hex, payload)

        result = self.controller.fetch_user_settings(self.user.id.hex)
        self.assertEqual(result.full_name, "New Name")
        self.assertEqual(result.credit_balance, self.user.credit_balance)

    def test_save_chat_settings_failure_language_mismatch(self):
        payload = stubs.api.chat_settings_payload(
            chat_config = stubs.api.chat_config_payload(language_name = ""), user_chat_config = None,
        )

        with self.assertRaises(ValidationError) as context:
            self.controller.save_chat_settings(self.chat.chat_id.hex, payload)

        self.assertEqual(context.exception.error_code, INVALID_LANGUAGE_SETTINGS)

    def test_save_chat_settings_failure_reply_chance_private_chat(self):
        chat = self.di.chat_config_repo.save(replace(self.chat, is_private = True, external_id = self.user.telegram_chat_id))
        payload = stubs.api.chat_settings_payload(
            chat_config = stubs.api.chat_config_payload(reply_chance_percent = 50), user_chat_config = None,
        )

        with self.assertRaises(ValidationError) as context:
            self.controller.save_chat_settings(chat.chat_id.hex, payload)

        self.assertEqual(context.exception.error_code, INVALID_REPLY_CHANCE)

    def test_save_chat_settings_failure_invalid_release_notifications(self):
        payload = stubs.api.chat_settings_payload(
            chat_config = stubs.api.chat_config_payload(release_notifications = "invalid_value"), user_chat_config = None,
        )

        with self.assertRaises(ValidationError) as context:
            self.controller.save_chat_settings(self.chat.chat_id.hex, payload)

        self.assertEqual(context.exception.error_code, INVALID_RELEASE_NOTIFICATIONS)

    def test_save_chat_settings_success_chat_config(self):
        payload = stubs.api.chat_settings_payload(
            chat_config = stubs.api.chat_config_payload(
                language_name = "Spanish", language_iso_code = "es", reply_chance_percent = 75, media_mode = "file",
            ),
            user_chat_config = None,
        )

        self.controller.save_chat_settings(self.chat.chat_id.hex, payload)

        result = self.controller.fetch_chat_settings(self.chat.chat_id.hex).chat_config
        self.assertEqual(result.chat_id, self.chat.chat_id.hex)
        self.assertEqual(result.title, self.chat.title)
        self.assertEqual(result.platform, self.chat.chat_type.value)
        self.assertEqual(result.language_name, "Spanish")
        self.assertEqual(result.language_iso_code, "es")
        self.assertEqual(result.reply_chance_percent, 75)
        self.assertEqual(result.release_notifications, "major")
        self.assertEqual(result.media_mode, "file")
        self.assertFalse(result.is_private)

    def test_save_chat_settings_success_user_chat_config(self):
        payload = stubs.api.chat_settings_payload(
            chat_config = None,
            user_chat_config = stubs.api.user_chat_config_payload(
                use_about_me = False, max_output_tokens = 500, max_chat_history_depth = 5, max_iterations = 3,
            ),
        )

        self.controller.save_chat_settings(self.chat.chat_id.hex, payload)

        result = self.controller.fetch_chat_settings(self.chat.chat_id.hex).user_chat_config
        self.assertFalse(result.use_about_me)
        self.assertTrue(result.use_custom_prompt)
        self.assertEqual(result.max_output_tokens, 500)
        self.assertEqual(result.max_chat_history_depth, 5)
        self.assertEqual(result.max_iterations, 3)

    def test_save_chat_settings_failure_non_admin_chat_config_rejected(self):
        self.bot.members[(self.chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member()
        payload = stubs.api.chat_settings_payload(user_chat_config = None)

        with self.assertRaises(AuthorizationError) as context:
            self.controller.save_chat_settings(self.chat.chat_id.hex, payload)

        self.assertEqual(context.exception.error_code, NOT_CHAT_ADMIN)

    def test_save_chat_settings_rejects_empty_payload(self):
        payload = stubs.api.chat_settings_payload(chat_config = None, user_chat_config = None)

        with self.assertRaises(ValidationError) as context:
            self.controller.save_chat_settings(self.chat.chat_id.hex, payload)

        self.assertEqual(context.exception.error_code, EMPTY_CHAT_SETTINGS_PAYLOAD)

    def test_fetch_all_chat_settings_success(self):
        self.di.chat_config_repo.save(replace(self.chat, is_private = True, external_id = self.user.telegram_chat_id))

        result = self.controller.fetch_all_chat_settings()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].chat_config.chat_id, self.chat.chat_id.hex)
        self.assertEqual(result[0].chat_config.title, self.chat.title)
        self.assertTrue(result[0].chat_config.is_own)
        self.assertTrue(result[0].chat_config.is_admin)
        self.assertEqual(result[0].chat_config.platform, "telegram")
        self.assertTrue(result[0].user_chat_config.use_about_me)

    def test_fetch_all_chat_settings_sort_order(self):
        private_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = uuid4(), external_id = self.user.telegram_chat_id,
        ))
        member_chat = self.di.chat_config_repo.save(stubs.domain.chat_config(
            chat_id = uuid4(), external_id = "member-chat", title = "A Member Group", is_private = False,
        ))
        self.di.chat_membership_service.save(stubs.domain.chat_membership(chat_id = member_chat.chat_id))
        self.bot.members[(member_chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member()

        result = self.controller.fetch_all_chat_settings()

        self.assertEqual([entry.chat_config.chat_id for entry in result], [
            private_chat.chat_id.hex, self.chat.chat_id.hex, member_chat.chat_id.hex,
        ])
        self.assertEqual([entry.chat_config.is_admin for entry in result], [True, True, False])

    def test_fetch_all_chat_settings_empty_memberships(self):
        self.bot.members[(self.chat.external_id, str(self.user.telegram_user_id))] = stubs.external.telegram_chat_member_left()

        self.assertEqual(self.controller.fetch_all_chat_settings(), [])

    def test_fetch_chat_settings_success(self):
        self.di.chat_membership_service.save(stubs.domain.chat_membership())

        result = self.controller.fetch_chat_settings(self.chat.chat_id.hex)

        self.assertEqual(result.chat_config.chat_id, self.chat.chat_id.hex)
        self.assertTrue(result.chat_config.is_admin)
        self.assertEqual(result.user_chat_config.max_output_tokens, 3500)

    def test_create_settings_link_with_sponsorship(self):
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(sponsor_id = self.agent.id, receiver_id = self.user.id))

        result = self.controller.create_settings_link()

        self.assertEqual(result.settings_link, self.shortener.short_url)
        url = self.shortener.requested_urls[-1]
        self.assertTrue(url.startswith(f"{config.backoffice_url_base}/en/user/{self.user.id.hex}/sponsorships?token="))
        claims = verify_jwt_token(url.split("token=")[1])
        self.assertEqual(claims["sub"], self.user.id.hex)
        self.assertNotIn("sponsored_by", claims)

    def test_create_settings_link_no_telegram_chat_id(self):
        self.di.inject_invoker(replace(self.user, telegram_chat_id = None, telegram_user_id = None))

        with self.assertRaises(AuthorizationError) as context:
            self.controller.create_settings_link()

        self.assertEqual(context.exception.error_code, NO_PRIVATE_CHAT)

    def test_fetch_external_tools_success_mixed_configuration(self):
        self.di.user_repo.save(replace(self.user, anthropic_key = None, credit_balance = 0.0))

        result = self.controller.fetch_external_tools(self.user.id.hex)

        self.assertEqual(len(result.tools), len(ALL_EXTERNAL_TOOLS))
        self.assertEqual(len(result.providers), len(ALL_PROVIDERS))
        providers = {provider.definition.id: provider.is_configured for provider in result.providers}
        self.assertTrue(providers[OPEN_AI.id])
        self.assertFalse(providers[ANTHROPIC.id])
        for tool in result.tools:
            with self.subTest(tool = tool.definition.id):
                self.assertEqual(tool.is_configured, providers[tool.definition.provider.id])
        self.assertIn("lowest_price", result.presets)
        self.assertIn("highest_price", result.presets)
        self.assertIn("agent_choice", result.presets)
        for choices in result.presets.values():
            self.assertTrue(choices)
            self.assertTrue(all(isinstance(key, str) and isinstance(value, str) and value for key, value in choices.items()))

    def test_fetch_external_tools_includes_cost_estimate(self):
        result = self.controller.fetch_external_tools(self.user.id.hex)

        for tool in result.tools:
            with self.subTest(tool = tool.definition.id):
                expected = next(definition for definition in ALL_EXTERNAL_TOOLS if definition.id == tool.definition.id)
                self.assertEqual(tool.definition.cost_estimate, expected.cost_estimate)

    def test_create_help_link_success(self):
        result = self.controller.create_help_link()

        self.assertEqual(result, self.shortener.short_url)
        url = self.shortener.requested_urls[-1]
        self.assertTrue(url.startswith(f"{config.backoffice_url_base}/en/features?token="))
        self.assertEqual(verify_jwt_token(url.split("token=")[1])["sub"], self.user.id.hex)

    def test_create_help_link_success_with_custom_language(self):
        self.di.inject_invoker_chat(replace(self.chat, language_iso_code = "es"))

        result = self.controller.create_help_link()

        self.assertEqual(result, self.shortener.short_url)
        url = self.shortener.requested_urls[-1]
        self.assertTrue(url.startswith(f"{config.backoffice_url_base}/es/features?token="))
        self.assertEqual(verify_jwt_token(url.split("token=")[1])["sub"], self.user.id.hex)

    def test_create_help_link_failure_no_telegram_chat_id(self):
        self.di.inject_invoker(replace(self.user, telegram_chat_id = None, telegram_user_id = None))

        with self.assertRaises(AuthorizationError) as context:
            self.controller.create_help_link()

        self.assertEqual(context.exception.error_code, NO_PRIVATE_CHAT)

    def test_fetch_external_tools_sorts_by_provider_order_then_name(self):
        result = self.controller.fetch_external_tools(self.user.id.hex)

        self.assertEqual([provider.definition.id for provider in result.providers], [provider.id for provider in ALL_PROVIDERS])
        for provider in ALL_PROVIDERS:
            names = [tool.definition.name for tool in result.tools if tool.definition.provider.id == provider.id]
            self.assertEqual(names, sorted(names))
        provider_positions = {provider.id: index for index, provider in enumerate(ALL_PROVIDERS)}
        positions = [provider_positions[tool.definition.provider.id] for tool in result.tools]
        self.assertEqual(positions, sorted(positions))

    def test_fetch_external_tools_matches_provider_configuration(self):
        result = self.controller.fetch_external_tools(self.user.id.hex)

        providers = {provider.definition.id: provider.is_configured for provider in result.providers}
        self.assertTrue(providers[OPEN_AI.id])
        for tool in result.tools:
            self.assertEqual(tool.is_configured, providers[tool.definition.provider.id])

    def test_fetch_products_success(self):
        starter_product = stubs.domain.configured_product()
        pro_product = stubs.domain.configured_product(id = "prod-2", credits = 500, name = "Pro Pack")
        self.addCleanup(setattr, config, "products", config.products)
        config.products = {product.id: product for product in (starter_product, pro_product)}

        result = self.controller.fetch_products(self.user.id.hex)

        self.assertEqual(result.products, [
            replace(product, url = f"{product.url}?user_id={self.user.id.hex}")
            for product in (starter_product, pro_product)
        ])
