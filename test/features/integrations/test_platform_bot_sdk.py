import io
import os
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

from PIL import Image

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.integrations.integration_config import (
    TELEGRAM_MAX_PHOTO_SIZE_BYTES,
    TELEGRAM_MAX_VIDEO_SIZE_BYTES,
    WHATSAPP_MAX_VIDEO_SIZE_BYTES,
)
from features.integrations.platform_bot_sdk import ChatAccess, PlatformBotSDK
from features.users.user import User
from features.videos.video_file_utils import VideoMetadata
from util.config import config
from util.errors import ConfigurationError, ExternalServiceError


def _make_di() -> DI:
    di = Mock(spec = DI)
    di.require_invoker_chat_type.return_value = ChatConfigDB.ChatType.telegram
    di.chat_config_repo = Mock()
    di.chat_config_repo.get_by_external_identifiers.return_value = SimpleNamespace(
        chat_id = UUID(int = 1),
        external_id = "tg-chat-1",
        media_mode = ChatConfigDB.MediaMode.photo,
        chat_type = ChatConfigDB.ChatType.telegram,
    )
    di.invoker = SimpleNamespace(id = UUID(int = 2))
    di.telegram_bot_sdk = Mock()
    di.telegram_bot_sdk.send_photo = Mock(return_value = "sent")
    di.telegram_bot_sdk.send_document = Mock(return_value = "document-sent")
    di.telegram_bot_sdk.send_video = Mock(return_value = "video-sent")
    di.whatsapp_bot_sdk = Mock()
    di.whatsapp_bot_sdk.send_photo = Mock(return_value = "sent")
    di.whatsapp_bot_sdk.send_document = Mock(return_value = "document-sent")
    di.whatsapp_bot_sdk.send_video = Mock(return_value = "video-sent")
    di.chat_attachment_service = Mock()
    di.chat_attachment_service.save.return_value = SimpleNamespace(
        id = "stored-attachment",
        last_url = "s3://the-agent/chats/chat-id/attachments/stored-attachment",
        extension = "mp4",
        mime_type = "video/mp4",
    )
    di.chat_attachment_service.create_public_url.return_value = SimpleNamespace(
        url = _public_attachment_url("stored-attachment"),
        valid_until = 0,
    )
    return di


def _public_attachment_url(token: str) -> str:
    return f"{config.public_api_base_url}/attachments/public/{token}"


def _mock_response(body: bytes = b"data") -> Mock:
    resp = Mock()
    resp.status_code = 200
    resp.iter_content.return_value = [body]
    resp.raise_for_status = Mock()
    resp.__enter__ = Mock(return_value = resp)
    resp.__exit__ = Mock(return_value = False)
    return resp


def _make_temp_file(content: bytes = b"data") -> str:
    tmp = tempfile.NamedTemporaryFile(delete = False, suffix = ".png")
    tmp.write(content)
    tmp.flush()
    tmp.close()
    return tmp.name


def _image_bytes(image: Image.Image, image_format: str = "PNG", **kwargs) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format = image_format, **kwargs)
    return buffer.getvalue()


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (10, 10), color = (100, 150, 200))
    return _image_bytes(image, "JPEG", quality = 90)


class PlatformBotSDKTest(unittest.TestCase):

    def __video_context(
        self,
        original: bytes = b"original",
        prepared: bytes | None = None,
        container: str = "mp4",
    ):
        original_path = _make_temp_file(original)
        self.addCleanup(os.unlink, original_path)
        prepared_path = original_path
        if prepared is not None:
            prepared_path = _make_temp_file(prepared)
            self.addCleanup(os.unlink, prepared_path)
        context = MagicMock()
        context.__enter__.return_value = (
            original_path,
            prepared_path,
            VideoMetadata(
                container = container,
                video_codecs = ("h264",),
                audio_codecs = ("aac",),
                pixel_formats = ("yuv420p",),
                video_stream_count = 1,
                audio_stream_count = 1,
                width = 1280,
                height = 720,
                duration_seconds = 10,
                size_bytes = len(prepared or original),
                has_fast_start = True,
            ),
        )
        return context, original_path, prepared_path, context.__enter__.return_value[2]

    def test_send_photo_resizes_and_uploads(self):
        di = _make_di()
        prepared_path = _make_temp_file(b"prepared")
        resized_path = _make_temp_file(b"resized")
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.add_outgoing_png_background") as mock_prepare, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_get.return_value = _mock_response(body = b"x" * (6 * 1024 * 1024))
            mock_prepare.return_value = prepared_path
            mock_resize.return_value = resized_path
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")
        mock_prepare.assert_called_once()
        mock_resize.assert_called_once()
        self.assertEqual(mock_resize.call_args.args[0], prepared_path)
        self.assertEqual(mock_resize.call_args.args[1], TELEGRAM_MAX_PHOTO_SIZE_BYTES)
        stored_bytes = di.chat_attachment_service.save.call_args.kwargs["content"]
        self.assertEqual(stored_bytes, b"resized")
        di.telegram_bot_sdk.send_photo.assert_called_once_with(
            di.chat_config_repo.get_by_external_identifiers.return_value,
            di.chat_attachment_service.save.return_value,
            None,
        )
        self.assertEqual(result, "sent")

    def test_whatsapp_send_photo_prepares_before_resize(self):
        di = _make_di()
        di.require_invoker_chat_type.return_value = ChatConfigDB.ChatType.whatsapp
        prepared_path = _make_temp_file(b"prepared")
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.add_outgoing_png_background") as mock_prepare, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_get.return_value = _mock_response(body = b"source")
            mock_prepare.return_value = prepared_path
            mock_resize.return_value = prepared_path
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")

        mock_prepare.assert_called_once()
        self.assertEqual(mock_resize.call_args.args[0], prepared_path)
        di.whatsapp_bot_sdk.send_photo.assert_called_once_with(
            di.chat_config_repo.get_by_external_identifiers.return_value,
            di.chat_attachment_service.save.return_value,
            None,
        )
        self.assertEqual(result, "sent")

    def test_send_photo_stores_original_when_no_resize_needed(self):
        di = _make_di()
        body = _jpeg_bytes()
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_get.return_value = _mock_response(body = body)
            mock_resize.side_effect = lambda path, max_size_bytes: path
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.jpg")
        stored_bytes = di.chat_attachment_service.save.call_args.kwargs["content"]
        self.assertEqual(stored_bytes, body)
        self.assertEqual(
            di.chat_attachment_service.save.call_args.kwargs["remote_url"],
            "http://example.com/img.jpg",
        )
        di.telegram_bot_sdk.send_photo.assert_called_once_with(
            di.chat_config_repo.get_by_external_identifiers.return_value,
            di.chat_attachment_service.save.return_value,
            None,
        )
        self.assertEqual(result, "sent")

    def test_send_photo_download_failure_raises(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.get") as mock_get:
            response = _mock_response()
            response.raise_for_status.side_effect = Exception("boom")
            mock_get.return_value = response
            with self.assertRaises(ExternalServiceError):
                sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")
        di.chat_attachment_service.save.assert_not_called()
        di.telegram_bot_sdk.send_photo.assert_not_called()

    def test_send_photo_empty_download_raises(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.get") as mock_get:
            mock_get.return_value = _mock_response(body = b"")
            with self.assertRaises(ExternalServiceError):
                sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")
        di.chat_attachment_service.save.assert_not_called()
        di.telegram_bot_sdk.send_photo.assert_not_called()

    def test_send_document_does_not_resize(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.add_outgoing_png_background") as mock_prepare, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            response = _mock_response(body = b"document")
            response.headers = {"Content-Type": "application/pdf"}
            mock_get.return_value = response
            mock_resize.side_effect = lambda path, max_size_bytes: path
            result = sdk.send_document(chat_id = 1, document_url = "http://example.com/doc.pdf")
        self.assertIsNone(mock_resize.call_args.args[1])
        mock_prepare.assert_not_called()
        stored_bytes = di.chat_attachment_service.save.call_args.kwargs["content"]
        self.assertEqual(stored_bytes, b"document")
        stored_attachment = di.chat_attachment_service.save.call_args.kwargs["attachment"]
        self.assertIsNone(stored_attachment.last_url)
        self.assertEqual(stored_attachment.mime_type, "application/pdf")
        self.assertEqual(
            di.chat_attachment_service.save.call_args.kwargs["remote_url"],
            "http://example.com/doc.pdf",
        )
        di.telegram_bot_sdk.send_document.assert_called_once_with(
            chat_config = di.chat_config_repo.get_by_external_identifiers.return_value,
            attachment = di.chat_attachment_service.save.return_value,
            thumbnail = None,
            caption = None,
        )
        self.assertEqual(result, "document-sent")

    def test_send_document_with_thumbnail_builds_public_url(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.add_outgoing_png_background") as mock_prepare, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_get.return_value = _mock_response(body = b"document")
            mock_resize.side_effect = lambda path, max_size_bytes: path
            result = sdk.send_document(
                chat_id = 1,
                document_url = "http://example.com/doc.pdf",
                caption = "caption",
                thumbnail = "http://example.com/thumb.png",
            )
        self.assertEqual(mock_resize.call_count, 2)
        mock_prepare.assert_not_called()
        di.chat_attachment_service.create_public_url.assert_called_once()
        di.telegram_bot_sdk.send_document.assert_called_once_with(
            chat_config = di.chat_config_repo.get_by_external_identifiers.return_value,
            attachment = di.chat_attachment_service.save.return_value,
            thumbnail = _public_attachment_url("stored-attachment"),
            caption = "caption",
        )
        self.assertEqual(result, "document-sent")

    def test_smart_send_photo_file_mode_sends_document_only(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.add_outgoing_png_background") as mock_prepare, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_get.return_value = _mock_response(body = b"document")
            mock_resize.side_effect = lambda path, max_size_bytes: path
            result = sdk.smart_send_photo(
                media_mode = ChatConfigDB.MediaMode.file,
                chat_id = 1,
                photo_url = "http://example.com/img.png",
            )
        di.telegram_bot_sdk.send_photo.assert_not_called()
        di.telegram_bot_sdk.send_document.assert_called_once()
        mock_prepare.assert_not_called()
        self.assertEqual(result, "document-sent")

    def test_smart_send_photo_all_mode_sends_photo_and_document(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.add_outgoing_png_background") as mock_prepare, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_get.return_value = _mock_response(body = b"data")
            mock_prepare.side_effect = lambda path: path
            mock_resize.side_effect = lambda path, max_size_bytes: path
            result = sdk.smart_send_photo(
                media_mode = ChatConfigDB.MediaMode.all,
                chat_id = 1,
                photo_url = "http://example.com/img.png",
                caption = "caption",
                thumbnail = "http://example.com/thumb.png",
        )
        di.telegram_bot_sdk.send_photo.assert_called_once_with(
            di.chat_config_repo.get_by_external_identifiers.return_value,
            di.chat_attachment_service.save.return_value,
            "caption",
        )
        di.telegram_bot_sdk.send_document.assert_called_once_with(
            chat_config = di.chat_config_repo.get_by_external_identifiers.return_value,
            attachment = di.chat_attachment_service.save.return_value,
            thumbnail = _public_attachment_url("stored-attachment"),
            caption = "caption",
        )
        mock_prepare.assert_called_once()
        self.assertEqual(result, "document-sent")

    def test_smart_send_photo_photo_mode_falls_back_to_document(self):
        di = _make_di()
        di.telegram_bot_sdk.send_photo.side_effect = Exception("send failed")
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_get.return_value = _mock_response(body = b"data")
            mock_resize.side_effect = lambda path, max_size_bytes: path
            result = sdk.smart_send_photo(
                media_mode = ChatConfigDB.MediaMode.photo,
                chat_id = 1,
                photo_url = "http://example.com/img.png",
            )
        di.telegram_bot_sdk.send_photo.assert_called_once()
        di.telegram_bot_sdk.send_document.assert_called_once()
        self.assertEqual(result, "document-sent")

    def test_prepare_outgoing_video_stores_prepared_media(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        video_context, _, _, _ = self.__video_context(prepared = b"prepared")

        with patch(
            "features.integrations.platform_bot_sdk.prepare_remote_video_files",
            return_value = video_context,
        ) as mock_video_files:
            result = sdk.prepare_outgoing_video_attachment(
                chat_config = di.chat_config_repo.get_by_external_identifiers.return_value,
                public_url = "https://example.com/video.mp4",
            )

        mock_video_files.assert_called_once_with(
            "https://example.com/video.mp4",
            max_size_bytes = TELEGRAM_MAX_VIDEO_SIZE_BYTES,
        )
        di.chat_attachment_service.save.assert_called_once()
        self.assertEqual(di.chat_attachment_service.save.call_args.kwargs["content"], b"prepared")
        attachment = di.chat_attachment_service.save.call_args.kwargs["attachment"]
        self.assertIsNone(attachment.last_url)
        self.assertEqual(attachment.extension, "mp4")
        self.assertIsNone(attachment.mime_type)
        self.assertEqual(
            di.chat_attachment_service.save.call_args.kwargs["remote_url"],
            "https://example.com/video.mp4",
        )
        self.assertIs(result, di.chat_attachment_service.save.return_value)

    def test_prepare_outgoing_video_uses_url_when_container_is_unknown(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        video_context, _, _, _ = self.__video_context(prepared = b"prepared", container = "unknown")

        with patch(
            "features.integrations.platform_bot_sdk.prepare_remote_video_files",
            return_value = video_context,
        ):
            sdk.prepare_outgoing_video_attachment(
                chat_config = di.chat_config_repo.get_by_external_identifiers.return_value,
                public_url = "https://example.com/video.webm",
            )

        attachment = di.chat_attachment_service.save.call_args.kwargs["attachment"]
        self.assertIsNone(attachment.extension)
        self.assertEqual(
            di.chat_attachment_service.save.call_args.kwargs["remote_url"],
            "https://example.com/video.webm",
        )

    def test_prepare_outgoing_video_stores_compliant_media(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        video_context, _, _, _ = self.__video_context()

        with patch(
            "features.integrations.platform_bot_sdk.prepare_remote_video_files",
            return_value = video_context,
        ):
            sdk.prepare_outgoing_video_attachment(
                chat_config = di.chat_config_repo.get_by_external_identifiers.return_value,
                public_url = "https://example.com/video.mp4",
            )

        di.chat_attachment_service.save.assert_called_once()
        self.assertEqual(
            di.chat_attachment_service.save.call_args.kwargs["content"],
            b"original",
        )

    def test_prepare_outgoing_video_uses_whatsapp_limit(self):
        di = _make_di()
        di.require_invoker_chat_type.return_value = ChatConfigDB.ChatType.whatsapp
        sdk = PlatformBotSDK(di = di)
        video_context, _, _, _ = self.__video_context(prepared = b"prepared")

        with patch(
            "features.integrations.platform_bot_sdk.prepare_remote_video_files",
            return_value = video_context,
        ) as mock_video_files:
            sdk.prepare_outgoing_video_attachment(
                chat_config = di.chat_config_repo.get_by_external_identifiers.return_value,
                public_url = "https://example.com/video.mp4",
            )

        mock_video_files.assert_called_once_with(
            "https://example.com/video.mp4",
            max_size_bytes = WHATSAPP_MAX_VIDEO_SIZE_BYTES,
        )

    def test_send_video_prepares_for_telegram_and_routes_native_attachment(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        prepared_attachment = SimpleNamespace(id = "prepared")

        with patch.object(sdk, "prepare_outgoing_video_attachment", return_value = prepared_attachment) as mock_prepare:
            result = sdk.send_video(
                chat_id = 1,
                video_url = "https://example.com/video.mp4",
                caption = "caption",
            )

        mock_prepare.assert_called_once_with(
            di.chat_config_repo.get_by_external_identifiers.return_value,
            "https://example.com/video.mp4",
        )
        di.telegram_bot_sdk.send_video.assert_called_once_with(
            di.chat_config_repo.get_by_external_identifiers.return_value,
            prepared_attachment,
            "caption",
        )
        self.assertEqual(result, "video-sent")

    def test_send_video_prepares_for_whatsapp_and_routes_native_attachment(self):
        di = _make_di()
        di.require_invoker_chat_type.return_value = ChatConfigDB.ChatType.whatsapp
        sdk = PlatformBotSDK(di = di)
        prepared_attachment = SimpleNamespace(id = "prepared")

        with patch.object(
            sdk,
            "prepare_outgoing_video_attachment",
            return_value = prepared_attachment,
        ):
            result = sdk.send_video(
                chat_id = 1,
                video_url = "https://example.com/video.mp4",
                caption = "caption",
            )

        di.whatsapp_bot_sdk.send_video.assert_called_once_with(
            di.chat_config_repo.get_by_external_identifiers.return_value,
            prepared_attachment,
            "caption",
        )
        self.assertEqual(result, "video-sent")

    def test_send_video_rejects_unsupported_chat_type(self):
        di = _make_di()
        di.require_invoker_chat_type.return_value = "unsupported"
        sdk = PlatformBotSDK(di = di)

        with patch.object(sdk, "prepare_outgoing_video_attachment", return_value = Mock()), \
                self.assertRaises(ConfigurationError):
            sdk.send_video(
                chat_id = 1,
                video_url = "https://example.com/video.mp4",
            )

    def test_smart_send_video_file_mode_sends_document_only(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)

        with patch.object(sdk, "send_video", return_value = "video-sent") as mock_send_video, \
                patch.object(sdk, "send_document", return_value = "document-sent") as mock_send_document:
            result = sdk.smart_send_video(
                media_mode = ChatConfigDB.MediaMode.file,
                chat_id = 1,
                video_url = "https://example.com/video.mp4",
                caption = "caption",
            )

        mock_send_video.assert_not_called()
        mock_send_document.assert_called_once_with(
            1,
            "https://example.com/video.mp4",
            "caption",
        )
        self.assertEqual(result, "document-sent")

    def test_smart_send_video_all_mode_sends_video_and_document(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)

        with patch.object(sdk, "send_video", return_value = "video-sent") as mock_send_video, \
                patch.object(sdk, "send_document", return_value = "document-sent") as mock_send_document:
            result = sdk.smart_send_video(
                media_mode = ChatConfigDB.MediaMode.all,
                chat_id = 1,
                video_url = "https://example.com/video.mp4",
                caption = "caption",
            )

        mock_send_video.assert_called_once_with(
            1,
            "https://example.com/video.mp4",
            "caption",
        )
        mock_send_document.assert_called_once_with(
            1,
            "https://example.com/video.mp4",
            "caption",
        )
        self.assertEqual(result, "document-sent")

    def test_smart_send_video_photo_mode_falls_back_to_document(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)

        with patch.object(sdk, "send_video", side_effect = RuntimeError("send failed")) as mock_send_video, \
                patch.object(sdk, "send_document", return_value = "document-sent") as mock_send_document:
            result = sdk.smart_send_video(
                media_mode = ChatConfigDB.MediaMode.photo,
                chat_id = 1,
                video_url = "https://example.com/video.mp4",
            )

        mock_send_video.assert_called_once_with(
            1,
            "https://example.com/video.mp4",
            None,
        )
        mock_send_document.assert_called_once_with(
            1,
            "https://example.com/video.mp4",
            None,
        )
        self.assertEqual(result, "document-sent")


class ResolveChatAccessTest(unittest.TestCase):

    def _make_chat(self, chat_type: ChatConfigDB.ChatType, is_private: bool, external_id: str = "chat1") -> ChatConfig:
        return ChatConfig(
            chat_id = UUID(int = 1),
            external_id = external_id,
            is_private = is_private,
            chat_type = chat_type,
        )

    def _make_user(self, telegram_user_id: int | None = 1, telegram_chat_id: str | None = None) -> User:
        return User(
            id = UUID(int = 2),
            telegram_user_id = telegram_user_id,
            telegram_chat_id = telegram_chat_id,
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

    def _make_member(self, status: str) -> SimpleNamespace:
        return SimpleNamespace(status = status)

    def test_own_private_chat_returns_owner(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        chat = self._make_chat(ChatConfigDB.ChatType.telegram, is_private = True, external_id = "chat1")
        user = self._make_user(telegram_chat_id = "chat1")

        self.assertEqual(sdk.resolve_chat_access(chat, user), ChatAccess.owner)
        di.telegram_bot_sdk.get_chat_member.assert_not_called()

    def test_private_chat_not_owned_returns_none(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        chat = self._make_chat(ChatConfigDB.ChatType.telegram, is_private = True, external_id = "other_chat")
        user = self._make_user(telegram_chat_id = "chat1")

        self.assertIsNone(sdk.resolve_chat_access(chat, user))
        di.telegram_bot_sdk.get_chat_member.assert_not_called()

    def test_telegram_group_creator_returns_admin(self):
        di = _make_di()
        di.telegram_bot_sdk.get_chat_member.return_value = self._make_member("creator")
        sdk = PlatformBotSDK(di = di)
        chat = self._make_chat(ChatConfigDB.ChatType.telegram, is_private = False)
        user = self._make_user(telegram_user_id = 42)

        self.assertEqual(sdk.resolve_chat_access(chat, user), ChatAccess.admin)

    def test_telegram_group_administrator_returns_admin(self):
        di = _make_di()
        di.telegram_bot_sdk.get_chat_member.return_value = self._make_member("administrator")
        sdk = PlatformBotSDK(di = di)
        chat = self._make_chat(ChatConfigDB.ChatType.telegram, is_private = False)
        user = self._make_user(telegram_user_id = 42)

        self.assertEqual(sdk.resolve_chat_access(chat, user), ChatAccess.admin)

    def test_telegram_group_member_returns_member(self):
        di = _make_di()
        di.telegram_bot_sdk.get_chat_member.return_value = self._make_member("member")
        sdk = PlatformBotSDK(di = di)
        chat = self._make_chat(ChatConfigDB.ChatType.telegram, is_private = False)
        user = self._make_user(telegram_user_id = 42)

        self.assertEqual(sdk.resolve_chat_access(chat, user), ChatAccess.member)

    def test_telegram_group_restricted_returns_member(self):
        di = _make_di()
        di.telegram_bot_sdk.get_chat_member.return_value = self._make_member("restricted")
        sdk = PlatformBotSDK(di = di)
        chat = self._make_chat(ChatConfigDB.ChatType.telegram, is_private = False)
        user = self._make_user(telegram_user_id = 42)

        self.assertEqual(sdk.resolve_chat_access(chat, user), ChatAccess.member)

    def test_telegram_group_left_returns_none(self):
        di = _make_di()
        di.telegram_bot_sdk.get_chat_member.return_value = self._make_member("left")
        sdk = PlatformBotSDK(di = di)
        chat = self._make_chat(ChatConfigDB.ChatType.telegram, is_private = False)
        user = self._make_user(telegram_user_id = 42)

        self.assertIsNone(sdk.resolve_chat_access(chat, user))

    def test_telegram_group_kicked_returns_none(self):
        di = _make_di()
        di.telegram_bot_sdk.get_chat_member.return_value = self._make_member("kicked")
        sdk = PlatformBotSDK(di = di)
        chat = self._make_chat(ChatConfigDB.ChatType.telegram, is_private = False)
        user = self._make_user(telegram_user_id = 42)

        self.assertIsNone(sdk.resolve_chat_access(chat, user))

    def test_telegram_group_api_returns_none_returns_none(self):
        di = _make_di()
        di.telegram_bot_sdk.get_chat_member.return_value = None
        sdk = PlatformBotSDK(di = di)
        chat = self._make_chat(ChatConfigDB.ChatType.telegram, is_private = False)
        user = self._make_user(telegram_user_id = 42)

        self.assertIsNone(sdk.resolve_chat_access(chat, user))

    def test_telegram_group_no_telegram_user_id_returns_none(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        chat = self._make_chat(ChatConfigDB.ChatType.telegram, is_private = False)
        user = self._make_user(telegram_user_id = None)

        self.assertIsNone(sdk.resolve_chat_access(chat, user))
        di.telegram_bot_sdk.get_chat_member.assert_not_called()

    def test_whatsapp_group_returns_none(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)
        chat = self._make_chat(ChatConfigDB.ChatType.whatsapp, is_private = False)
        user = self._make_user()

        self.assertIsNone(sdk.resolve_chat_access(chat, user))


class TempFileBehaviorTest(unittest.TestCase):

    def test_named_temporary_file_deleted_manually(self):
        with tempfile.NamedTemporaryFile(delete = False) as tmp:
            path = tmp.name
            tmp.write(b"data")
        self.assertTrue(os.path.exists(path))
        os.unlink(path)
        self.assertFalse(os.path.exists(path))
