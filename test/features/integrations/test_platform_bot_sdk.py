import os
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.integrations.platform_bot_sdk import ChatAccess, PlatformBotSDK
from features.users.user import User


def _make_di() -> DI:
    di = Mock(spec = DI)
    di.require_invoker_chat_type.return_value = ChatConfigDB.ChatType.telegram
    di.require_invoker_chat.return_value = SimpleNamespace(media_mode = ChatConfigDB.MediaMode.photo)
    di.telegram_bot_sdk = Mock()
    di.telegram_bot_sdk.send_photo = Mock(return_value = "sent")
    di.whatsapp_bot_sdk = Mock()
    di.image_uploader = MagicMock()
    return di


def _mock_response(content_length: int | None = None, body: bytes = b"") -> Mock:
    resp = Mock()
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


class PlatformBotSDKTest(unittest.TestCase):

    def test_send_photo_resizes_and_uploads(self):
        """Test that send_photo resizes large images and uploads them"""
        di = _make_di()
        resized_path = _make_temp_file(b"resized")
        uploader = Mock()
        uploader.execute.return_value = "uploaded-url"
        di.image_uploader.return_value = uploader
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_head.return_value = _mock_response(content_length = 6 * 1024 * 1024)
            mock_get.return_value = _mock_response(body = b"x" * (6 * 1024 * 1024))
            mock_resize.return_value = resized_path
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")
        mock_resize.assert_called_once()
        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, "uploaded-url", None)
        self.assertEqual(result, "sent")

    def test_send_photo_head_failure_still_resizes_and_uploads(self):
        """Test that send_photo handles HEAD request failure gracefully"""
        di = _make_di()
        resized_path = _make_temp_file(b"resized")
        uploader = Mock()
        uploader.execute.return_value = "uploaded-url"
        di.image_uploader.return_value = uploader
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_head.side_effect = Exception("head failed")
            mock_get.return_value = _mock_response(body = b"x" * (6 * 1024 * 1024))
            mock_resize.return_value = resized_path
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")
        mock_resize.assert_called_once()
        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, "uploaded-url", None)
        self.assertEqual(result, "sent")

    def test_send_photo_resize_failure_falls_back_to_original(self):
        """Test that send_photo uses original URL if resizing fails"""
        di = _make_di()
        uploader = Mock()
        uploader.execute.return_value = "uploaded-url"
        di.image_uploader.return_value = uploader
        sdk = PlatformBotSDK(di = di)
        with patch("features.integrations.platform_bot_sdk.requests.head") as mock_head, \
                patch("features.integrations.platform_bot_sdk.requests.get") as mock_get, \
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_head.return_value = _mock_response(content_length = 6 * 1024 * 1024)
            mock_get.return_value = _mock_response(body = b"x" * (6 * 1024 * 1024))
            mock_resize.side_effect = Exception("resize failed")
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")
        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, "http://example.com/img.png", None)
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
                patch("features.integrations.platform_bot_sdk.resize_file") as mock_resize:
            mock_head.return_value = _mock_response(content_length = 6 * 1024 * 1024)
            mock_get.return_value = _mock_response(body = b"x" * (6 * 1024 * 1024))
            mock_resize.return_value = resized_path
            result = sdk.send_photo(chat_id = 1, photo_url = "http://example.com/img.png")
        di.telegram_bot_sdk.send_photo.assert_called_once_with(1, "http://example.com/img.png", None)
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
