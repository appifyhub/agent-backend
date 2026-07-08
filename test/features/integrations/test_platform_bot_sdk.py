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
from features.integrations.platform_bot_sdk import ChatAccess, PlatformBotSDK
from features.users.user import User
from util.config import config


def _make_di() -> DI:
    di = Mock(spec = DI)
    di.require_invoker_chat_type.return_value = ChatConfigDB.ChatType.telegram
    di.require_invoker_chat.return_value = SimpleNamespace(
        chat_id = UUID(int = 1),
        media_mode = ChatConfigDB.MediaMode.photo,
    )
    di.invoker = SimpleNamespace(id = UUID(int = 2))
    di.telegram_bot_sdk = Mock()
    di.telegram_bot_sdk.send_photo = Mock(return_value = "sent")
    di.telegram_bot_sdk.send_document = Mock(return_value = "document-sent")
    di.whatsapp_bot_sdk = Mock()
    di.whatsapp_bot_sdk.send_photo = Mock(return_value = "sent")
    di.whatsapp_bot_sdk.send_document = Mock(return_value = "document-sent")
    di.image_uploader = MagicMock()
    di.chat_message_attachment_service = Mock()
    di.chat_message_attachment_service.is_own_public_url.side_effect = lambda url: bool(
        url and url.startswith(f"{config.public_api_base_url}/attachments/public/"),
    )
    di.chat_message_attachment_service.save.return_value = SimpleNamespace(
        id = "stored-attachment",
        last_url = "s3://the-agent/chats/chat-id/attachments/stored-attachment",
    )
    di.chat_message_attachment_service.create_public_url.return_value = SimpleNamespace(
        url = _public_attachment_url("stored-attachment"),
        valid_until = 0,
    )
    return di


def _public_attachment_url(token: str) -> str:
    return f"{config.public_api_base_url}/attachments/public/{token}"


def _mock_response(content_length: int | None = None, body: bytes = b"") -> Mock:
    resp = Mock()
    resp.status_code = 200
    resp.content = body
    resp.headers = {}
    if content_length is not None:
        resp.headers["Content-Length"] = str(content_length)
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


def _transparent_png_bytes() -> bytes:
    image = Image.new("RGBA", (2, 1))
    image.putdata([(255, 0, 0, 0), (10, 20, 30, 255)])
    return _image_bytes(image)


def _noisy_transparent_png_bytes(width: int = 80, height: int = 80) -> bytes:
    image = Image.new("RGBA", (width, height))
    pixels = []
    for y in range(height):
        for x in range(width):
            pixels.append(((x * 17) % 256, (y * 19) % 256, ((x + y) * 23) % 256, 128))
    image.putdata(pixels)
    return _image_bytes(image)


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (10, 10), color = (100, 150, 200))
    return _image_bytes(image, "JPEG", quality = 90)


class PlatformBotSDKTest(unittest.TestCase):

    def test_send_photo_resizes_and_uploads(self):
        """Test that send_photo resizes large images and uploads them"""
        di = _make_di()
        resized_path = _make_temp_file(b"resized")
        uploader = Mock()
        uploaded_url = _public_attachment_url("uploaded")
        uploader.execute.return_value = uploaded_url
        di.image_uploader.return_value = uploader
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.flatten_transparency_over_black") as mock_flatten, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_head.return_value = _mock_response(content_length = 6 * 1024 * 1024)
            mock_get.return_value = _mock_response(body = b"x" * (6 * 1024 * 1024))
            mock_flatten.side_effect = lambda path: path
            mock_resize.return_value = resized_path
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")
        mock_resize.assert_called_once()
        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, uploaded_url, None)
        self.assertEqual(result, "sent")

    def test_send_photo_head_failure_still_resizes_and_uploads(self):
        """Test that send_photo handles HEAD request failure gracefully"""
        di = _make_di()
        resized_path = _make_temp_file(b"resized")
        uploader = Mock()
        uploaded_url = _public_attachment_url("uploaded")
        uploader.execute.return_value = uploaded_url
        di.image_uploader.return_value = uploader
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.flatten_transparency_over_black") as mock_flatten, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_head.side_effect = Exception("head failed")
            mock_get.return_value = _mock_response(body = b"x" * (6 * 1024 * 1024))
            mock_flatten.side_effect = lambda path: path
            mock_resize.return_value = resized_path
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")
        mock_resize.assert_called_once()
        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, uploaded_url, None)
        self.assertEqual(result, "sent")

    def test_send_photo_resize_failure_falls_back_to_original(self):
        """Test that send_photo uses original URL if resizing fails"""
        di = _make_di()
        uploader = Mock()
        uploader.execute.return_value = _public_attachment_url("uploaded")
        di.image_uploader.return_value = uploader
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.flatten_transparency_over_black") as mock_flatten, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_head.return_value = _mock_response(content_length = 6 * 1024 * 1024)
            mock_get.return_value = _mock_response(body = b"x" * (6 * 1024 * 1024))
            mock_flatten.side_effect = lambda path: path
            mock_resize.side_effect = Exception("resize failed")
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")
        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, _public_attachment_url("stored-attachment"), None)
        self.assertEqual(result, "sent")

    def test_send_photo_uploader_failure_falls_back_to_original(self):
        """Test that send_photo uses original URL if upload fails"""
        di = _make_di()
        resized_path = _make_temp_file(b"resized")
        uploader = Mock()
        uploader.execute.side_effect = Exception("upload failed")
        di.image_uploader.return_value = uploader
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.flatten_transparency_over_black") as mock_flatten, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_head.return_value = _mock_response(content_length = 6 * 1024 * 1024)
            mock_get.return_value = _mock_response(body = b"x" * (6 * 1024 * 1024))
            mock_flatten.side_effect = lambda path: path
            mock_resize.return_value = resized_path
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")
        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, _public_attachment_url("stored-attachment"), None)
        self.assertEqual(result, "sent")

    def test_send_photo_flattens_transparent_png_and_uploads(self):
        di = _make_di()
        uploader = Mock()
        uploaded_url = _public_attachment_url("uploaded")
        uploader.execute.return_value = uploaded_url
        di.image_uploader.return_value = uploader
        body = _transparent_png_bytes()
        sdk = PlatformBotSDK(di = di)

        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get:
            mock_head.return_value = _mock_response(content_length = len(body))
            mock_get.return_value = _mock_response(body = body)
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")

        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, uploaded_url, None)
        di.image_uploader.assert_called_once()
        uploaded_bytes = di.image_uploader.call_args.kwargs["binary_image"]
        with Image.open(io.BytesIO(uploaded_bytes)) as uploaded_image:
            self.assertEqual(uploaded_image.mode, "RGB")
            self.assertEqual(uploaded_image.getpixel((0, 0)), (0, 0, 0))
        self.assertEqual(result, "sent")

    def test_send_photo_under_limit_jpeg_copies_original_url_to_storage(self):
        di = _make_di()
        body = _jpeg_bytes()
        sdk = PlatformBotSDK(di = di)

        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get:
            mock_head.return_value = _mock_response(content_length = len(body))
            mock_get.return_value = _mock_response(body = body)
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.jpg")

        mock_get.assert_called_once()
        di.image_uploader.assert_not_called()
        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, _public_attachment_url("stored-attachment"), None)
        self.assertEqual(result, "sent")

    def test_send_photo_resizes_flattened_image_before_upload(self):
        di = _make_di()
        resized_path = _make_temp_file(b"resized")
        uploader = Mock()
        uploaded_url = _public_attachment_url("uploaded")
        uploader.execute.return_value = uploaded_url
        di.image_uploader.return_value = uploader
        body = _noisy_transparent_png_bytes()
        sdk = PlatformBotSDK(di = di)

        with patch("features.integrations.platform_bot_sdk.TELEGRAM_MAX_PHOTO_SIZE_BYTES", 100), \
                patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_head.return_value = _mock_response(content_length = len(body))
            mock_get.return_value = _mock_response(body = body)
            mock_resize.return_value = resized_path
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")

        mock_resize.assert_called_once()
        di.image_uploader.assert_called_once_with(binary_image = b"resized", message_text = None)
        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, uploaded_url, None)
        self.assertEqual(result, "sent")

    def test_smart_send_photo_file_mode_uses_original_document_url(self):
        di = _make_di()
        sdk = PlatformBotSDK(di = di)

        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get:
            mock_get.return_value = _mock_response(body = b"document")
            result = sdk.smart_send_photo(
                media_mode = ChatConfigDB.MediaMode.file,
                chat_id = 1,
                photo_url = "http://example.com/img.png",
            )

        mock_head.assert_not_called()
        di.image_uploader.assert_not_called()
        di.telegram_bot_sdk.send_photo.assert_not_called()
        di.telegram_bot_sdk.send_document.assert_called_once_with(
            chat_id = 1,
            document_url = _public_attachment_url("stored-attachment"),
            thumbnail = None,
            caption = None,
        )
        self.assertEqual(result, "document-sent")

    def test_smart_send_photo_all_mode_sends_prepared_photo_and_original_document(self):
        di = _make_di()
        uploader = Mock()
        uploaded_url = _public_attachment_url("uploaded")
        uploader.execute.return_value = uploaded_url
        di.image_uploader.return_value = uploader
        body = _transparent_png_bytes()
        sdk = PlatformBotSDK(di = di)

        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get:
            mock_head.return_value = _mock_response(content_length = len(body))
            mock_get.return_value = _mock_response(body = body)
            result = sdk.smart_send_photo(
                media_mode = ChatConfigDB.MediaMode.all,
                chat_id = 1,
                photo_url = "http://example.com/img.png",
                caption = "caption",
                thumbnail = "thumb",
            )

        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, uploaded_url, "caption")
        di.telegram_bot_sdk.send_document.assert_called_once_with(
            chat_id = 1,
            document_url = _public_attachment_url("stored-attachment"),
            thumbnail = _public_attachment_url("stored-attachment"),
            caption = "caption",
        )
        self.assertEqual(result, "document-sent")

    def test_send_photo_preparation_failure_uses_original_url(self):
        di = _make_di()
        body = _transparent_png_bytes()
        sdk = PlatformBotSDK(di = di)

        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.flatten_transparency_over_black") as mock_flatten:
            mock_head.return_value = _mock_response(content_length = len(body))
            mock_get.return_value = _mock_response(body = body)
            mock_flatten.side_effect = Exception("flatten failed")
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")

        di.image_uploader.assert_not_called()
        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, _public_attachment_url("stored-attachment"), None)
        self.assertEqual(result, "sent")


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
