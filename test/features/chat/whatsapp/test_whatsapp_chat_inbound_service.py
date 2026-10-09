import unittest
from datetime import datetime, timedelta
from typing import cast

import stubs
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from pydantic import SecretStr
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.chat.attachment.chat_attachment_repo import ChatAttachmentRepository
from features.chat.attachment.chat_attachment_service import ChatAttachmentService
from features.chat.config.chat_config_repo import ChatConfigRepository
from features.chat.membership.chat_membership_service import ChatMembershipService
from features.chat.message.chat_message_repo import ChatMessageRepository
from features.chat.whatsapp.whatsapp_chat_inbound_service import WhatsAppChatInboundService
from features.integrations.integration_config import THE_AGENT
from features.integrations.integrations import resolve_agent_user
from features.users.user_repo import UserRepository
from util.config import config
from util.errors import InternalError
from util.functions import generate_deterministic_short_uuid


class WhatsAppChatInboundServiceTest(unittest.TestCase):

    di: DI
    resolver: WhatsAppChatInboundService
    chats: ChatConfigRepository
    users: UserRepository
    messages: ChatMessageRepository
    attachment_repo: ChatAttachmentRepository
    attachments: ChatAttachmentService
    memberships: ChatMembershipService
    api: FakeWhatsAppBotAPI

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.api = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)
        self.attachments = self.di.chat_attachment_service
        self.memberships = self.di.chat_membership_service
        self.attachment_repo = self.di.chat_attachment_repo
        self.chats = self.di.chat_config_repo
        self.messages = self.di.chat_message_repo
        self.users = self.di.user_repo
        self.users.save(THE_AGENT)
        self.resolver = self.di.whatsapp_chat_inbound_service

    def test_ingest_update_empty(self):
        result = self.resolver.ingest_update(stubs.external.whatsapp_update(entry = []))

        self.assertEqual(result, [])

    def test_ingest_update_orders_raw_messages_oldest_first(self):
        now = int(datetime.now().timestamp())
        latest = stubs.external.whatsapp_message(
            id = "latest",
            timestamp = str(now),
            text = stubs.external.whatsapp_text(body = "Latest"),
            **{"from": "1"},
        )
        oldest = stubs.external.whatsapp_message(
            id = "oldest",
            timestamp = str(now - 10),
            text = stubs.external.whatsapp_text(body = "Oldest"),
            **{"from": "1"},
        )
        value = stubs.external.whatsapp_value(messages = [latest, oldest])
        update = stubs.external.whatsapp_update(
            entry = [
                stubs.external.whatsapp_entry(
                    id = "entry",
                    changes = [stubs.external.whatsapp_change(value = value)],
                ),
            ],
        )

        results = self.resolver.ingest_update(update)

        self.assertEqual([result.message.message_id for result in results], ["oldest", "latest"])

    def test_ingest_message_no_author(self):
        message = stubs.external.whatsapp_message(
            id = "m1",
            timestamp = str(int(datetime.now().timestamp())),
            text = stubs.external.whatsapp_text(body = "This is a message"),
            **{"from": ""},
        )

        result = self.resolver.ingest_message(message, stubs.external.whatsapp_value(messages = [message], contacts = []))

        self.assertIsNone(result.author)
        self.assertEqual(result.message.message_id, "m1")
        self.assertIsNone(result.message.author_id)
        self.assertEqual(result.attachments, [])
        self.assertEqual(result.raw_message_text, "This is a message")

    def test_ingest_message_no_author_with_attachment_raises(self):
        message = stubs.external.whatsapp_message(
            id = "m1",
            timestamp = str(int(datetime.now().timestamp())),
            type = "image",
            text = None,
            image = stubs.external.whatsapp_media_attachment(id = "e1"),
            **{"from": ""},
        )

        with self.assertRaises(InternalError):
            self.resolver.ingest_message(message, stubs.external.whatsapp_value(messages = [message], contacts = []))

    def test_ingest_message_from_agent_skips_remote_attachments(self):
        agent_user = resolve_agent_user(ChatConfigDB.ChatType.whatsapp)
        agent_id = agent_user.whatsapp_user_id
        assert agent_id is not None
        message = stubs.external.whatsapp_message(
            id = "m1",
            timestamp = str(int(datetime.now().timestamp())),
            type = "image",
            text = None,
            image = stubs.external.whatsapp_media_attachment(
                id = "e1",
                caption = "This is a message",
            ),
            **{"from": agent_id},
        )

        result = self.resolver.ingest_message(
            message,
            stubs.external.whatsapp_value(
                messages = [message],
                contacts = [
                    stubs.external.whatsapp_contact(
                        profile = stubs.external.whatsapp_profile(
                            name = agent_user.full_name,
                        ),
                        wa_id = agent_id,
                    ),
                ],
            ),
        )

        assert result.author is not None
        self.assertEqual(result.author.whatsapp_user_id, agent_id)
        self.assertEqual(result.attachments, [])
        self.assertEqual(self.memberships.get_all_for_user(result.author.id), [])
        self.assertEqual(self.messages.get(result.chat.chat_id, result.message.message_id), result.message)

    def test_ingest_message_with_attachment_uses_local_attachment_id(self):
        self.api.downloads["e1"] = b"image content"
        message = stubs.external.whatsapp_message(
            id = "m1",
            timestamp = str(int(datetime.now().timestamp())),
            type = "image",
            text = None,
            image = stubs.external.whatsapp_media_attachment(
                id = "e1",
                caption = "This is a message",
            ),
            **{"from": "1"},
        )

        result = self.resolver.ingest_message(message, stubs.external.whatsapp_value(messages = [message]))

        assert result.author is not None
        attachment_id = generate_deterministic_short_uuid("e1")
        self.assertEqual(result.attachments[0].id, attachment_id)
        self.assertEqual(result.attachments[0].message_id, "m1")
        self.assertEqual(result.attachments[0].chat_id, result.chat.chat_id)
        self.assertEqual(result.attachments[0].uploader_user_id, result.author.id)
        self.assertIn(f"📎 [ {attachment_id} (image/jpeg) ]", result.message.text)
        self.assertEqual(result.raw_message_text, "This is a message")
        self.assertNotIn(attachment_id, result.raw_message_text)
        self.assertEqual(self.messages.get(result.chat.chat_id, result.message.message_id), result.message)
        self.assertIsNotNone(self.memberships.get(result.author.id, result.chat.chat_id))

    def test_ingest_message_with_video_uses_authenticated_download_path(self):
        self.api.downloads["video1"] = b"video content"
        message = stubs.external.whatsapp_message(
            id = "video-message",
            timestamp = str(int(datetime.now().timestamp())),
            type = "video",
            text = None,
            video = stubs.external.whatsapp_media_attachment(
                id = "video1",
                mime_type = "video/mp4",
                caption = "Video caption",
            ),
            **{"from": "1"},
        )

        result = self.resolver.ingest_message(message, stubs.external.whatsapp_value(messages = [message]))

        self.assertEqual(result.raw_message_text, "Video caption")
        self.assertEqual(len(result.attachments), 1)
        self.assertEqual(result.attachments[0].external_id, "video1")
        self.assertEqual(result.attachments[0].mime_type, "video/mp4")
        self.assertEqual(self.attachments.get(result.attachments[0].id), result.attachments[0])

    def test_ingest_message_with_reply_uses_local_attachment_id(self):
        chat = self.chats.save(
            stubs.domain.chat_config(external_id = "c1", chat_type = ChatConfigDB.ChatType.whatsapp),
        )
        uploader = self.users.save(stubs.domain.user(full_name = "Agent", whatsapp_user_id = "123"))
        self.messages.save(
            stubs.domain.chat_message(
                chat_id = chat.chat_id,
                message_id = "old-message",
                author_id = None,
                text = "Original caption\n\n📎 [ remote123 ]",
            ),
        )
        self.attachment_repo.save(
            stubs.domain.chat_attachment(
                id = "local123",
                chat_id = chat.chat_id,
                uploader_user_id = uploader.id,
                message_id = "old-message",
                mime_type = "image/png",
            ),
        )
        message = stubs.external.whatsapp_message(
            id = "new-message",
            timestamp = str(int(datetime.now().timestamp())),
            text = stubs.external.whatsapp_text(body = "Please use this"),
            context = stubs.external.whatsapp_context(id = "old-message"),
            **{"from": "c1"},
        )

        result = self.resolver.ingest_message(
            message,
            stubs.external.whatsapp_value(messages = [message], contacts = [stubs.external.whatsapp_contact(wa_id = "c1")]),
        )

        self.assertIn(">>>> Original caption", result.message.text)
        self.assertIn(">>>> 📎 [ local123 (image/png) ]", result.message.text)
        self.assertIn("Please use this", result.message.text)
        self.assertNotIn("remote123", result.message.text)

    def test_store_author_none(self):
        result = self.resolver.store_author(None)
        self.assertIsNone(result)

    def test_store_author_new(self):
        self.chats.save(stubs.domain.chat_config(
            external_id = "1",
            chat_type = ChatConfigDB.ChatType.whatsapp,
        ))
        mapped_data = stubs.domain.user_remote_data(
            whatsapp_user_id = "1",
            full_name = "New User",
        )

        result = self.resolver.store_author(mapped_data)
        saved_user = self.users.get(result.id)

        assert result is not None
        self.assertEqual(result, saved_user)
        self.assertIsNotNone(result.id)
        self.assertEqual(result.full_name, mapped_data.full_name)
        self.assertEqual(result.whatsapp_user_id, mapped_data.whatsapp_user_id)
        self.assertEqual(result.credit_balance, config.welcome_credit_grant_amount)
        self.assertIsNone(result.open_ai_key)
        self.assertEqual(result.group, UserDB.Group.standard)
        records = self.di.usage_record_repo.get_by_user(THE_AGENT.id, only_transfers = True)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].counterpart_id, result.id)
        self.assertEqual(records[0].total_cost_credits, config.welcome_credit_grant_amount)
        self.assertEqual(records[0].note, "Welcome")
        self.assertEqual(self.api.get_sent_messages("1"), [])

    def test_store_author_rolls_back_new_user_when_welcome_grant_fails(self):
        self.addCleanup(setattr, config, "welcome_credit_grant_amount", config.welcome_credit_grant_amount)
        config.welcome_credit_grant_amount = float("nan")
        mapped_data = stubs.domain.user_remote_data(whatsapp_user_id = "1")

        with self.assertRaises(InternalError):
            self.resolver.store_author(mapped_data)

        self.assertIsNone(self.users.get_by_remote_data(mapped_data))
        self.assertEqual(self.di.usage_record_repo.get_by_user(THE_AGENT.id, only_transfers = True), [])

    def test_store_author_by_whatsapp_user_id(self):
        existing_user_data = stubs.domain.user(
            whatsapp_user_id = "1234567890",
            full_name = "Existing User",
        )
        existing_user = self.users.save(existing_user_data)

        mapped_data = stubs.domain.user_remote_data(
            whatsapp_user_id = "1234567890",
            full_name = "Updated User",
        )

        result = self.resolver.store_author(mapped_data)
        assert result is not None
        saved_user = self.users.get(result.id)

        assert result is not None
        self.assertEqual(result, saved_user)
        self.assertEqual(result.id, existing_user.id)
        # Should preserve existing name when DB has a value, even if platform sends a new one
        self.assertEqual(result.full_name, existing_user.full_name)
        self.assertEqual(result.whatsapp_user_id, mapped_data.whatsapp_user_id)
        self.assertEqual(result.whatsapp_user_id, existing_user.whatsapp_user_id)
        self.assertEqual(result.open_ai_key, existing_user.open_ai_key)
        self.assertEqual(result.group, existing_user.group)
        self.assertEqual(result.created_at, existing_user.created_at)

    def test_store_author_user_limit_reached_creates_waitlisted_user(self):
        self.addCleanup(setattr, config, "max_users", config.max_users)
        config.max_users = 0
        mapped_data = stubs.domain.user_remote_data(
            whatsapp_user_id = "1",
            full_name = "New User",
        )

        result = self.resolver.store_author(mapped_data)
        assert result is not None
        self.assertTrue(result.is_on_waitlist)
        self.assertFalse(result.is_invited_to_start)
        self.assertFalse(result.are_policies_accepted)

    def test_store_author_existing(self):
        existing_user_data = stubs.domain.user(
            whatsapp_user_id = "1",
            full_name = "Existing User",
            open_ai_key = SecretStr("sk-key"),
            anthropic_key = SecretStr("sk-key"),
            perplexity_key = SecretStr("sk-key"),
            replicate_key = SecretStr("sk-key"),
            rapid_api_key = SecretStr("sk-key"),
            coinmarketcap_key = SecretStr("sk-key"),
            twelve_data_api_key = SecretStr("sk-key"),
            x_key = SecretStr("sk-key"),
            x_ai_key = SecretStr("sk-key"),
            about_me = SecretStr("Personal info about me"),
            custom_prompt = SecretStr("Custom instructions to preserve"),
            credit_balance = 123.45,
            group = UserDB.Group.developer,
            tool_choice_chat = "openai",
            tool_choice_reasoning = "anthropic",
            tool_choice_copywriting = "perplexity",
            tool_choice_vision = "openai",
            tool_choice_hearing = "openai",
            tool_choice_images_gen = "replicate",
            tool_choice_search = "perplexity",
            tool_choice_embedding = "openai",
            tool_choice_api_fiat_exchange = "rapidapi",
            tool_choice_api_crypto_exchange = "coinmarketcap",
            tool_choice_api_stock_quote = "twelve-data",
            tool_choice_api_twitter = "rapidapi",
        )
        existing_user = self.users.save(existing_user_data)

        mapped_data = stubs.domain.user_remote_data(
            whatsapp_user_id = "1",
            full_name = "Updated User",
        )

        result = self.resolver.store_author(mapped_data)
        assert result is not None

        saved_user = self.users.get(result.id)

        self.assertEqual(result, saved_user)
        self.assertEqual(result.id, existing_user.id)
        # Should preserve existing name when DB has a value, even if platform sends a new one
        self.assertEqual(result.full_name, existing_user.full_name)
        self.assertEqual(result.whatsapp_user_id, mapped_data.whatsapp_user_id)
        self.assertEqual(result.whatsapp_user_id, mapped_data.whatsapp_user_id)
        self.assertEqual(result.open_ai_key, existing_user.open_ai_key)
        self.assertEqual(result.anthropic_key, existing_user.anthropic_key)
        self.assertEqual(result.perplexity_key, existing_user.perplexity_key)
        self.assertEqual(result.replicate_key, existing_user.replicate_key)
        self.assertEqual(result.rapid_api_key, existing_user.rapid_api_key)
        self.assertEqual(result.coinmarketcap_key, existing_user.coinmarketcap_key)
        self.assertEqual(result.twelve_data_api_key, existing_user.twelve_data_api_key)
        self.assertEqual(result.x_key, existing_user.x_key)
        self.assertEqual(result.x_ai_key, existing_user.x_ai_key)
        self.assertEqual(result.about_me, existing_user.about_me)
        self.assertEqual(result.custom_prompt, existing_user.custom_prompt)
        self.assertEqual(result.credit_balance, existing_user.credit_balance)
        self.assertEqual(result.group, existing_user.group)
        self.assertEqual(result.created_at, existing_user.created_at)
        self.assertEqual(self.di.usage_record_repo.get_by_user(THE_AGENT.id, only_transfers = True), [])

        # Verify all tool choice fields are preserved from existing user
        self.assertEqual(result.tool_choice_chat, existing_user.tool_choice_chat)
        self.assertEqual(result.tool_choice_reasoning, existing_user.tool_choice_reasoning)
        self.assertEqual(result.tool_choice_copywriting, existing_user.tool_choice_copywriting)
        self.assertEqual(result.tool_choice_vision, existing_user.tool_choice_vision)
        self.assertEqual(result.tool_choice_hearing, existing_user.tool_choice_hearing)
        self.assertEqual(result.tool_choice_images_gen, existing_user.tool_choice_images_gen)
        self.assertEqual(result.tool_choice_videos_gen, existing_user.tool_choice_videos_gen)
        self.assertEqual(result.tool_choice_search, existing_user.tool_choice_search)
        self.assertEqual(result.tool_choice_embedding, existing_user.tool_choice_embedding)
        self.assertEqual(result.tool_choice_api_fiat_exchange, existing_user.tool_choice_api_fiat_exchange)
        self.assertEqual(result.tool_choice_api_crypto_exchange, existing_user.tool_choice_api_crypto_exchange)
        self.assertEqual(result.tool_choice_api_stock_quote, existing_user.tool_choice_api_stock_quote)
        self.assertEqual(result.tool_choice_api_twitter, existing_user.tool_choice_api_twitter)

    def test_store_author_preserves_name_when_empty(self):
        existing_user_data = stubs.domain.user(
            whatsapp_user_id = "1",
            full_name = "Existing User",
        )
        existing_user = self.users.save(existing_user_data)

        # Test with None full_name
        mapped_data_none = stubs.domain.user_remote_data(
            whatsapp_user_id = "1",
            full_name = None,
        )

        result = self.resolver.store_author(mapped_data_none)
        assert result is not None
        self.assertEqual(result.id, existing_user.id)
        self.assertEqual(result.full_name, existing_user.full_name)  # Should preserve existing name

        # Test with empty string full_name
        mapped_data_empty = stubs.domain.user_remote_data(
            whatsapp_user_id = "1",
            full_name = "",
        )

        result = self.resolver.store_author(mapped_data_empty)
        assert result is not None
        self.assertEqual(result.id, existing_user.id)
        self.assertEqual(result.full_name, existing_user.full_name)  # Should preserve existing name

    def test_store_message_new(self):
        chat = self.chats.save(
            stubs.domain.chat_config(external_id = "c1", chat_type = ChatConfigDB.ChatType.whatsapp),
        )
        mapped_data = stubs.domain.chat_message_remote_data(
            message_id = "m1",
            sent_at = datetime.now(),
            text = "Raw message",
        )
        formatted_text = "Formatted message"

        result = self.resolver.store_message(mapped_data, formatted_text, chat.chat_id, None)
        saved_message = self.messages.get(chat.chat_id, mapped_data.message_id)

        assert result is not None
        self.assertEqual(result, saved_message)
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertIsNone(result.author_id)
        self.assertEqual(result.sent_at, mapped_data.sent_at)
        self.assertEqual(result.text, formatted_text)
        self.assertEqual(mapped_data.text, "Raw message")

    def test_store_message_with_existing(self):
        chat = self.chats.save(
            stubs.domain.chat_config(external_id = "c1", chat_type = ChatConfigDB.ChatType.whatsapp),
        )
        old_message = stubs.domain.chat_message(
            chat_id = chat.chat_id,
            message_id = "m1",
            author_id = None,
            sent_at = datetime.now() - timedelta(days = 1),
            text = "Old message",
        )
        self.messages.save(old_message)

        new_author = self.users.save(stubs.domain.user(full_name = "First Last", whatsapp_user_id = "c1"))
        mapped_data = stubs.domain.chat_message_remote_data(
            message_id = "m1",
            sent_at = datetime.now(),
            text = "Raw updated message",
        )
        formatted_text = "Formatted updated message"

        result = self.resolver.store_message(mapped_data, formatted_text, chat.chat_id, new_author.id)
        saved_message = self.messages.get(chat.chat_id, mapped_data.message_id)

        self.assertEqual(result, saved_message)
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertEqual(result.author_id, new_author.id)
        self.assertEqual(result.sent_at, mapped_data.sent_at)
        self.assertEqual(result.text, formatted_text)
        self.assertEqual(mapped_data.text, "Raw updated message")

    def test_store_attachment_new(self):
        self.api.downloads["e1"] = b"image content"
        chat = self.chats.save(
            stubs.domain.chat_config(external_id = "c1", chat_type = ChatConfigDB.ChatType.whatsapp),
        )
        uploader = self.users.save(stubs.domain.user(full_name = "Uploader", whatsapp_user_id = "123"))
        self.messages.save(
            stubs.domain.chat_message(chat_id = chat.chat_id, message_id = "m1", author_id = None, text = "x"),
        )
        mapped_data = stubs.domain.chat_attachment_remote_data(
            external_id = "e1",
            message_id = "m1",
            last_url = "path/to/file.jpg",
        )

        result = self.resolver.store_attachment(mapped_data, chat.chat_id, uploader.id)
        saved_attachment = self.attachments.get(result.id)

        self.assertEqual(result, saved_attachment)
        self.assertEqual(result.id, generate_deterministic_short_uuid(mapped_data.external_id))
        self.assertEqual(result.external_id, mapped_data.external_id)
        self.assertEqual(result.uploader_user_id, uploader.id)
        self.assertEqual(result.chat_id, chat.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertEqual(result.extension, "jpg")
        self.assertEqual(result.mime_type, "image/jpeg")

    def test_store_attachment_existing(self):
        self.api.downloads["e1"] = b"image content"
        chat = self.chats.save(
            stubs.domain.chat_config(external_id = "c1", chat_type = ChatConfigDB.ChatType.whatsapp),
        )
        self.messages.save(
            stubs.domain.chat_message(chat_id = chat.chat_id, message_id = "m1", author_id = None, text = "x"),
        )
        uploader = self.users.save(stubs.domain.user(full_name = "Uploader", whatsapp_user_id = "123"))
        old_attachment_data = stubs.domain.chat_attachment(
            id = "i1",
            external_id = "e1",
            chat_id = chat.chat_id,
            uploader_user_id = uploader.id,
            message_id = "m1",
        )
        old_attachment_data = self.attachments.save(old_attachment_data, content = b"existing image")

        mapped_data = stubs.domain.chat_attachment_remote_data(external_id = "e1", message_id = "m1")
        result = self.resolver.store_attachment(mapped_data, chat.chat_id, uploader.id)
        saved_attachment = self.attachments.get("i1")

        self.assertEqual(result, saved_attachment)
        self.assertEqual(result.id, old_attachment_data.id)
        self.assertEqual(result.uploader_user_id, old_attachment_data.uploader_user_id)
        self.assertEqual(result.chat_id, old_attachment_data.chat_id)
        self.assertEqual(result.message_id, mapped_data.message_id)
        self.assertEqual(result.size, old_attachment_data.size)
        self.assertEqual(result.last_url, old_attachment_data.last_url)
        self.assertEqual(result.extension, old_attachment_data.extension)
        self.assertEqual(result.mime_type, old_attachment_data.mime_type)
