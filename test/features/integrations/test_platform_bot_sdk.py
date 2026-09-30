from typing import cast
from unittest import TestCase
from uuid import UUID

from fakes.fake_http_client import FakeHTTPClient
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from PIL import Image
from stubs import domain, external
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.integrations.integration_config import TELEGRAM_MAX_PHOTO_SIZE_BYTES, WHATSAPP_MAX_VIDEO_SIZE_BYTES
from features.integrations.platform_bot_sdk import ChatAccess, PlatformBotSDK
from util.config import config
from util.error_codes import EXTERNAL_EMPTY_RESPONSE, FILE_UPLOAD_FAILED, MEDIA_DOWNLOAD_FAILED, UNSUPPORTED_CHAT_TYPE
from util.errors import ConfigurationError, ExternalServiceError


class PlatformBotSDKTest(TestCase):

    di: DI
    sdk: PlatformBotSDK
    chat: ChatConfig
    whatsapp_chat: ChatConfig
    telegram: FakeTelegramBotAPI
    whatsapp: FakeWhatsAppBotAPI
    http: FakeHTTPClient

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(domain.user()))
        self.chat = self.di.chat_config_repo.save(domain.chat_config(external_id = "123456789"))
        self.whatsapp_chat = self.di.chat_config_repo.save(domain.chat_config(
            chat_id = UUID("33333333-3333-4333-8333-c33333333333"),
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = "15551234567",
        ))
        self.di.inject_invoker_chat(self.chat)
        self.sdk = self.di.platform_bot_sdk()
        self.telegram = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.whatsapp = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)
        self.http = cast(FakeHTTPClient, self.di.http_client())

    def test_send_photo_resizes_and_uploads(self):
        body = external.image_bytes(size = (1500, 1500), compress_level = 0)
        self.assertGreater(len(body), TELEGRAM_MAX_PHOTO_SIZE_BYTES)
        self.http.responses["https://example.com/image.png"].append(external.http_response(
            content = body, headers = {"Content-Type": "image/png"},
        ))

        result = self.sdk.send_photo(self.chat.external_id, "https://example.com/image.png")

        attachment, = self.di.chat_attachment_repo.get_all_by_message(self.chat.chat_id, result.message_id)
        self.assertLessEqual(attachment.size, TELEGRAM_MAX_PHOTO_SIZE_BYTES)
        self.assertEqual(result.chat_id, self.chat.chat_id)
        self.assertIn("photo_url", self.telegram.get_sent_message(result.message_id))

    def test_whatsapp_send_photo_adds_background_to_transparent_png(self):
        self.di.inject_invoker_chat(self.whatsapp_chat)
        body = external.image_bytes(color = (100, 150, 200, 128))
        self.http.responses["https://example.com/image.png"].append(external.http_response(
            content = body, headers = {"Content-Type": "image/png"},
        ))

        result = self.sdk.send_photo(self.whatsapp_chat.external_id, "https://example.com/image.png")

        attachment, = self.di.chat_attachment_repo.get_all_by_message(self.whatsapp_chat.chat_id, result.message_id)
        with self.di.attachment_storage.open(attachment) as stream, Image.open(stream) as image:
            self.assertEqual(image.mode, "RGB")
        self.assertEqual(result.chat_id, self.whatsapp_chat.chat_id)
        self.assertIn("image_url", self.whatsapp.get_sent_message(result.message_id))
        self.assertEqual(self.telegram.get_sent_messages(self.chat.external_id), [])

    def test_send_photo_stores_original_when_no_resize_needed(self):
        body = external.image_bytes(image_format = "JPEG")
        self.http.responses["https://example.com/image.jpg"].append(external.http_response(
            content = body, headers = {"Content-Type": "image/jpeg"},
        ))

        result = self.sdk.send_photo(self.chat.external_id, "https://example.com/image.jpg")

        attachment, = self.di.chat_attachment_repo.get_all_by_message(self.chat.chat_id, result.message_id)
        with self.di.attachment_storage.open(attachment) as stream:
            self.assertEqual(stream.read(), body)
        self.assertIn("photo_url", self.telegram.get_sent_message(result.message_id))

    def test_send_photo_download_failure_raises(self):
        self.http.responses["https://example.com/image.png"].append(external.http_response(status_code = 503))

        with self.assertRaises(ExternalServiceError) as raised:
            self.sdk.send_photo(self.chat.external_id, "https://example.com/image.png")

        self.assertEqual(raised.exception.error_code, MEDIA_DOWNLOAD_FAILED)
        self.assertEqual(self.telegram.get_sent_messages(self.chat.external_id), [])
        self.assertEqual(self.di.chat_attachment_repo.get_all(), [])

    def test_send_photo_empty_download_raises(self):
        self.http.responses["https://example.com/image.png"].append(external.http_response(content = b""))

        with self.assertRaises(ExternalServiceError) as raised:
            self.sdk.send_photo(self.chat.external_id, "https://example.com/image.png")

        self.assertEqual(raised.exception.error_code, MEDIA_DOWNLOAD_FAILED)
        self.assertEqual(self.telegram.get_sent_messages(self.chat.external_id), [])
        self.assertEqual(self.di.chat_attachment_repo.get_all(), [])

    def test_send_document_preserves_original_content(self):
        body = external.image_bytes(color = (100, 150, 200, 128))
        self.http.responses["https://example.com/image.png"].append(external.http_response(
            content = body, headers = {"Content-Type": "image/png"},
        ))

        result = self.sdk.send_document(self.chat.external_id, "https://example.com/image.png")

        attachment, = self.di.chat_attachment_repo.get_all_by_message(self.chat.chat_id, result.message_id)
        with self.di.attachment_storage.open(attachment) as stream:
            self.assertEqual(stream.read(), body)
        self.assertEqual(attachment.mime_type, "image/png")
        self.assertIn("document_url", self.telegram.get_sent_message(result.message_id))

    def test_send_document_with_thumbnail_builds_public_url(self):
        self.http.responses["https://example.com/doc.pdf"].append(external.http_response(
            content = b"%PDF-1.7 document", headers = {"Content-Type": "application/pdf"},
        ))
        self.http.responses["https://example.com/thumb.png"].append(external.http_response(
            content = external.image_bytes(), headers = {"Content-Type": "image/png"},
        ))

        result = self.sdk.send_document(
            self.chat.external_id, "https://example.com/doc.pdf", caption = "caption",
            thumbnail = "https://example.com/thumb.png",
        )

        sent = self.telegram.get_sent_message(result.message_id)
        self.assertTrue(sent["thumbnail"].startswith(f"{config.public_api_base_url}/attachments/public/"))
        self.assertEqual(sent["caption"], "caption")
        attachment, = self.di.chat_attachment_repo.get_all_by_message(self.chat.chat_id, result.message_id)
        self.assertEqual(attachment.mime_type, "application/pdf")

    def test_smart_send_photo_file_mode_sends_document_only(self):
        self.http.responses["https://example.com/image.png"].append(external.http_response(
            content = external.image_bytes(), headers = {"Content-Type": "image/png"},
        ))

        result = self.sdk.smart_send_photo(ChatConfigDB.MediaMode.file, self.chat.external_id, "https://example.com/image.png")

        sent, = self.telegram.get_sent_messages(self.chat.external_id)
        self.assertIn("document_url", sent)
        self.assertEqual(self.telegram.get_sent_message(result.message_id), sent)

    def test_smart_send_photo_all_mode_sends_photo_and_document(self):
        body = external.image_bytes(color = (100, 150, 200, 128))
        self.http.responses["https://example.com/image.png"].extend([
            external.http_response(content = body, headers = {"Content-Type": "image/png"}) for _ in range(2)
        ])
        self.http.responses["https://example.com/thumb.png"].append(external.http_response(
            content = external.image_bytes(), headers = {"Content-Type": "image/png"},
        ))

        result = self.sdk.smart_send_photo(
            ChatConfigDB.MediaMode.all, self.chat.external_id, "https://example.com/image.png",
            caption = "caption", thumbnail = "https://example.com/thumb.png",
        )

        photo, document = self.telegram.get_sent_messages(self.chat.external_id)
        self.assertIn("photo_url", photo)
        self.assertIn("document_url", document)
        self.assertEqual(photo["caption"], "caption")
        self.assertEqual(document["caption"], "caption")
        self.assertTrue(document["thumbnail"].startswith(f"{config.public_api_base_url}/attachments/public/"))
        self.assertEqual(self.telegram.get_sent_message(result.message_id), document)
        attachment, = self.di.chat_attachment_repo.get_all_by_message(self.chat.chat_id, result.message_id)
        with self.di.attachment_storage.open(attachment) as stream:
            self.assertEqual(stream.read(), body)

    def test_smart_send_photo_all_mode_continues_after_photo_delivery_failure(self):
        self.telegram.photo_error = ExternalServiceError("Photo upload failed", FILE_UPLOAD_FAILED)
        self.http.responses["https://example.com/image.png"].extend([
            external.http_response(content = external.image_bytes(), headers = {"Content-Type": "image/png"}) for _ in range(2)
        ])

        result = self.sdk.smart_send_photo(ChatConfigDB.MediaMode.all, self.chat.external_id, "https://example.com/image.png")

        sent, = self.telegram.get_sent_messages(self.chat.external_id)
        self.assertIn("document_url", sent)
        self.assertEqual(self.telegram.get_sent_message(result.message_id), sent)

    def test_smart_send_photo_photo_mode_falls_back_to_document(self):
        self.telegram.photo_error = ExternalServiceError("Photo upload failed", FILE_UPLOAD_FAILED)
        self.http.responses["https://example.com/image.png"].extend([
            external.http_response(content = external.image_bytes(), headers = {"Content-Type": "image/png"}) for _ in range(2)
        ])

        result = self.sdk.smart_send_photo(ChatConfigDB.MediaMode.photo, self.chat.external_id, "https://example.com/image.png")

        sent, = self.telegram.get_sent_messages(self.chat.external_id)
        self.assertIn("document_url", sent)
        self.assertEqual(self.telegram.get_sent_message(result.message_id), sent)

    def test_prepare_outgoing_video_stores_prepared_media(self):
        original = external.video_bytes(fast_start = False)
        self.http.responses["https://example.com/video.mp4"].append(external.http_response(content = original))

        attachment = self.sdk.prepare_outgoing_video_attachment(self.chat, "https://example.com/video.mp4")

        self.assertEqual(attachment.extension, "mp4")
        self.assertGreater(attachment.size, 0)
        with self.di.attachment_storage.open(attachment) as stream:
            self.assertNotEqual(stream.read(), original)

    def test_prepare_outgoing_video_stores_compliant_media(self):
        body = external.video_bytes()
        self.http.responses["https://example.com/video.mp4"].append(external.http_response(content = body))

        attachment = self.sdk.prepare_outgoing_video_attachment(self.chat, "https://example.com/video.mp4")

        self.assertEqual(attachment.extension, "mp4")
        with self.di.attachment_storage.open(attachment) as stream:
            self.assertEqual(stream.read(), body)

    def test_prepare_outgoing_video_respects_whatsapp_limit(self):
        self.di.inject_invoker_chat(self.whatsapp_chat)
        body = external.video_bytes() + external.iso_media_box(b"free", bytes(WHATSAPP_MAX_VIDEO_SIZE_BYTES))
        self.http.responses["https://example.com/video.mp4"].append(external.http_response(content = body))

        attachment = self.sdk.prepare_outgoing_video_attachment(self.whatsapp_chat, "https://example.com/video.mp4")

        self.assertGreater(attachment.size, 0)
        self.assertLessEqual(attachment.size, WHATSAPP_MAX_VIDEO_SIZE_BYTES)
        with self.di.attachment_storage.open(attachment) as stream:
            self.assertNotEqual(stream.read(), body)

    def test_send_video_routes_telegram_native_attachment(self):
        body = external.video_bytes()
        self.http.responses["https://example.com/video.mp4"].append(external.http_response(content = body))

        result = self.sdk.send_video(self.chat.external_id, "https://example.com/video.mp4", caption = "caption")

        sent = self.telegram.get_sent_message(result.message_id)
        self.assertEqual(sent["content"], body)
        self.assertEqual(sent["caption"], "caption")
        self.assertEqual(result.chat_id, self.chat.chat_id)
        self.assertEqual(self.whatsapp.get_sent_messages(self.whatsapp_chat.external_id), [])

    def test_send_video_routes_whatsapp_native_attachment(self):
        self.di.inject_invoker_chat(self.whatsapp_chat)
        self.http.responses["https://example.com/video.mp4"].append(external.http_response(content = external.video_bytes()))

        result = self.sdk.send_video(self.whatsapp_chat.external_id, "https://example.com/video.mp4", caption = "caption")

        sent = self.whatsapp.get_sent_message(result.message_id)
        self.assertTrue(sent["video_url"].startswith(f"{config.public_api_base_url}/attachments/public/"))
        self.assertEqual(sent["caption"], "caption")
        self.assertEqual(result.chat_id, self.whatsapp_chat.chat_id)
        self.assertEqual(self.telegram.get_sent_messages(self.chat.external_id), [])

    def test_send_video_rejects_unsupported_chat_type(self):
        chat = self.di.chat_config_repo.save(domain.chat_config(chat_type = ChatConfigDB.ChatType.github))
        self.di.inject_invoker_chat(chat)

        with self.assertRaises(ConfigurationError) as raised:
            self.sdk.send_video(chat.external_id, "https://example.com/video.mp4")

        self.assertEqual(raised.exception.error_code, UNSUPPORTED_CHAT_TYPE)

    def test_smart_send_video_file_mode_sends_document_only(self):
        body = external.video_bytes()
        self.http.responses["https://example.com/video.mp4"].append(external.http_response(
            content = body, headers = {"Content-Type": "video/mp4"},
        ))

        result = self.sdk.smart_send_video(
            ChatConfigDB.MediaMode.file, self.chat.external_id, "https://example.com/video.mp4", caption = "caption",
        )

        sent, = self.telegram.get_sent_messages(self.chat.external_id)
        self.assertNotIn("metadata", sent)
        self.assertEqual(sent["content"], body)
        self.assertEqual(sent["caption"], "caption")
        self.assertEqual(self.telegram.get_sent_message(result.message_id), sent)

    def test_smart_send_video_all_mode_sends_video_and_document(self):
        body = external.video_bytes()
        self.http.responses["https://example.com/video.mp4"].extend([
            external.http_response(content = body, headers = {"Content-Type": "video/mp4"}) for _ in range(2)
        ])

        result = self.sdk.smart_send_video(
            ChatConfigDB.MediaMode.all, self.chat.external_id, "https://example.com/video.mp4", caption = "caption",
        )

        video, document = self.telegram.get_sent_messages(self.chat.external_id)
        self.assertIn("metadata", video)
        self.assertNotIn("metadata", document)
        self.assertEqual(video["content"], body)
        self.assertEqual(document["content"], body)
        self.assertEqual(video["caption"], "caption")
        self.assertEqual(document["caption"], "caption")
        self.assertEqual(self.telegram.get_sent_message(result.message_id), document)

    def test_smart_send_video_photo_mode_falls_back_to_document(self):
        self.telegram.video_error = ExternalServiceError("Video upload failed", FILE_UPLOAD_FAILED)
        body = external.video_bytes()
        self.http.responses["https://example.com/video.mp4"].extend([
            external.http_response(content = body, headers = {"Content-Type": "video/mp4"}) for _ in range(2)
        ])

        result = self.sdk.smart_send_video(ChatConfigDB.MediaMode.photo, self.chat.external_id, "https://example.com/video.mp4")

        sent, = self.telegram.get_sent_messages(self.chat.external_id)
        self.assertNotIn("metadata", sent)
        self.assertEqual(sent["content"], body)
        self.assertEqual(self.telegram.get_sent_message(result.message_id), sent)


class ResolveChatAccessTest(TestCase):

    di: DI
    sdk: PlatformBotSDK
    api: FakeTelegramBotAPI

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.sdk = self.di.platform_bot_sdk()
        self.api = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)

    def test_own_private_chat_returns_owner(self):
        chat = domain.chat_config(external_id = "chat1")
        user = domain.user(telegram_chat_id = "chat1")

        self.assertEqual(self.sdk.resolve_chat_access(chat, user), ChatAccess.owner)

    def test_private_chat_not_owned_returns_none(self):
        chat = domain.chat_config(external_id = "other_chat")
        user = domain.user(telegram_chat_id = "chat1")

        self.assertIsNone(self.sdk.resolve_chat_access(chat, user))

    def test_telegram_group_creator_returns_admin(self):
        chat = domain.chat_config(is_private = False)
        user = domain.user()
        self.api.members[(chat.external_id, str(user.telegram_user_id))] = external.telegram_chat_owner()

        self.assertEqual(self.sdk.resolve_chat_access(chat, user), ChatAccess.admin)

    def test_telegram_group_administrator_returns_admin(self):
        chat = domain.chat_config(is_private = False)
        user = domain.user()
        self.api.members[(chat.external_id, str(user.telegram_user_id))] = external.telegram_chat_administrator()

        self.assertEqual(self.sdk.resolve_chat_access(chat, user), ChatAccess.admin)

    def test_telegram_group_member_returns_member(self):
        chat = domain.chat_config(is_private = False)
        user = domain.user()
        self.api.members[(chat.external_id, str(user.telegram_user_id))] = external.telegram_chat_member()

        self.assertEqual(self.sdk.resolve_chat_access(chat, user), ChatAccess.member)

    def test_telegram_group_restricted_returns_member(self):
        chat = domain.chat_config(is_private = False)
        user = domain.user()
        self.api.members[(chat.external_id, str(user.telegram_user_id))] = external.telegram_chat_member_restricted()

        self.assertEqual(self.sdk.resolve_chat_access(chat, user), ChatAccess.member)

    def test_telegram_group_left_returns_none(self):
        chat = domain.chat_config(is_private = False)
        user = domain.user()
        self.api.members[(chat.external_id, str(user.telegram_user_id))] = external.telegram_chat_member_left()

        self.assertIsNone(self.sdk.resolve_chat_access(chat, user))

    def test_telegram_group_kicked_returns_none(self):
        chat = domain.chat_config(is_private = False)
        user = domain.user()
        self.api.members[(chat.external_id, str(user.telegram_user_id))] = external.telegram_chat_member_banned()

        self.assertIsNone(self.sdk.resolve_chat_access(chat, user))

    def test_telegram_group_api_failure_returns_none(self):
        chat = domain.chat_config(is_private = False)
        user = domain.user()
        self.api.members[(chat.external_id, str(user.telegram_user_id))] = ExternalServiceError("API failed", EXTERNAL_EMPTY_RESPONSE)  # ruff: ignore[line-too-long]

        self.assertIsNone(self.sdk.resolve_chat_access(chat, user))

    def test_telegram_group_no_telegram_user_id_returns_none(self):
        chat = domain.chat_config(is_private = False)
        user = domain.user(telegram_user_id = None)

        self.assertIsNone(self.sdk.resolve_chat_access(chat, user))

    def test_whatsapp_group_returns_none(self):
        chat = domain.chat_config(is_private = False, chat_type = ChatConfigDB.ChatType.whatsapp)

        self.assertIsNone(self.sdk.resolve_chat_access(chat, domain.user()))
