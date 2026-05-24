import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID

import requests_mock
from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from db.schema.chat_config import ChatConfig
from db.schema.chat_message_attachment import ChatMessageAttachment
from db.schema.tools_cache import ToolsCache
from db.schema.user import User
from features.chat.chat_attachment_processor import CACHE_TTL, SEARCH_THRESHOLD_TOKENS, ChatAttachmentProcessor
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.chat.url_attachment_resolver import UrlAttachmentResolver
from features.documents.docx_loader import DocxLoader
from features.documents.plain_text_loader import PlainTextLoader
from features.integrations.platform_bot_sdk import PlatformBotSDK
from util.config import config
from util.errors import NotFoundError, ValidationError


def _make_attachment(
    id: str = "1",
    mime_type: str = "image/png",
    extension: str = "png",
    url: str = "http://test.com/file.png",
) -> ChatMessageAttachment:
    return ChatMessageAttachment(
        id = id,
        external_id = f"external_{id}",
        chat_id = UUID(int = 1),
        message_id = id,
        mime_type = mime_type,
        extension = extension,
        last_url = url,
        last_url_until = int((datetime.now() + timedelta(days = 1)).timestamp()),
    )


class ChatAttachmentProcessorTest(unittest.TestCase):

    def setUp(self):
        config.web_retries = 1
        config.web_retry_delay_s = 0
        config.web_timeout_s = 1

        self.mock_di = MagicMock()
        self.mock_cache_crud = MagicMock()
        self.mock_user_crud = MagicMock()
        self.mock_chat_config_crud = MagicMock()
        self.mock_chat_message_attachment_crud = MagicMock()
        self.mock_access_token_resolver = MagicMock()
        self.mock_di.tools_cache_crud = self.mock_cache_crud
        self.mock_di.user_crud = self.mock_user_crud
        self.mock_di.chat_config_crud = self.mock_chat_config_crud
        self.mock_di.chat_message_attachment_crud = self.mock_chat_message_attachment_crud
        self.mock_di.access_token_resolver = self.mock_access_token_resolver
        self.mock_di.invoker_chat_id = UUID(int = 1).hex
        mock_chat = MagicMock()
        mock_chat.language_name = "Spanish"
        mock_chat.language_iso_code = "es"
        self.mock_di.require_invoker_chat = MagicMock(return_value = mock_chat)
        self.mock_di.telegram_bot_api = MagicMock()
        self.mock_di.tool_choice_resolver = MagicMock()
        self.mock_di.computer_vision_analyzer = MagicMock()

        self.cached_content = "resolved content"
        self.cache_entry = ToolsCache(
            key = "test_cache_key",
            value = self.cached_content,
            expires_at = datetime.now() + CACHE_TTL,
        )

        self.invoker_user = User(
            id = UUID(int = 1),
            full_name = "Test User",
            telegram_username = "test_user",
            telegram_chat_id = "test_chat_id",
            telegram_user_id = 1,
            open_ai_key = SecretStr("test_openai_key"),
            anthropic_key = SecretStr("test_anthropic_key"),
            perplexity_key = SecretStr("test_perplexity_key"),
            replicate_key = SecretStr("test_replicate_key"),
            rapid_api_key = SecretStr("test_rapid_api_key"),
            coinmarketcap_key = SecretStr("test_coinmarketcap_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.chat_config = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = "1",
            language_name = "Spanish",
            language_iso_code = "es",
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.attachment = _make_attachment()

        self.mock_user_crud.get.return_value = self.invoker_user.model_dump()
        self.mock_chat_config_crud.get.return_value = self.chat_config.model_dump()
        self.mock_chat_message_attachment_crud.get.return_value = self.attachment.model_dump()
        self.mock_chat_message_attachment_crud.save.return_value = self.attachment.model_dump()
        self.mock_cache_crud.create_key.return_value = "test_cache_key"
        self.mock_di.require_invoker_chat_type = MagicMock(return_value = ChatConfigDB.ChatType.telegram)

        self.mock_di.telegram_bot_sdk = TelegramBotSDK(self.mock_di)
        self.mock_di.platform_bot_sdk = MagicMock(return_value = PlatformBotSDK(self.mock_di))
        self.mock_di.url_attachment_resolver.side_effect = lambda url: UrlAttachmentResolver(url, self.mock_di)
        self.mock_di.plain_text_loader.side_effect = lambda job_id, document_url: PlainTextLoader(job_id, document_url)
        self.mock_di.docx_loader.side_effect = lambda job_id, document_url: DocxLoader(job_id, document_url)

    # ── Image cache tests (unchanged behavior) ────────────────────────────

    @requests_mock.Mocker()
    def test_execute_with_cache_hit(self, m: requests_mock.Mocker):
        m.get(str(self.attachment.last_url), content = b"image data", status_code = 200)
        self.mock_cache_crud.get.return_value = self.cache_entry.model_dump()

        mock_cv_instance = MagicMock()
        mock_cv_instance.execute.return_value = self.cached_content
        self.mock_di.computer_vision_analyzer.return_value = mock_cv_instance

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["1"],
            urls = None,
            di = self.mock_di,
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        self.assertEqual(len(resolver.result), 1)
        self.assertEqual(resolver.result[0]["text_content"], self.cached_content)
        self.mock_di.computer_vision_analyzer.assert_not_called()
        mock_cv_instance.execute.assert_not_called()

    @requests_mock.Mocker()
    def test_execute_with_cache_miss(self, m: requests_mock.Mocker):
        m.get(str(self.attachment.last_url), content = b"image data", status_code = 200)
        self.mock_cache_crud.get.return_value = None

        mock_cv_instance = MagicMock()
        mock_cv_instance.execute.return_value = self.cached_content
        self.mock_di.computer_vision_analyzer.return_value = mock_cv_instance
        self.mock_di.tool_choice_resolver.require_tool.return_value = MagicMock()
        self.mock_access_token_resolver.require_access_token_for_tool.return_value = "**********"

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["1"],
            urls = None,
            di = self.mock_di,
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        self.assertEqual(len(resolver.result), 1)
        self.assertEqual(resolver.result[0]["text_content"], self.cached_content)
        mock_cv_instance.execute.assert_called_once()
        self.mock_cache_crud.save.assert_called_once()

    # ── Validation / not-found tests (unchanged behavior) ─────────────────

    def test_empty_attachment_ids_list(self):
        with self.assertRaises(ValidationError) as context:
            ChatAttachmentProcessor(
                additional_context = "context",
                attachment_ids = [],
                urls = None,
                di = self.mock_di,
            )
        self.assertIn("No attachment IDs provided", str(context.exception))

    def test_empty_attachment_id_string(self):
        with self.assertRaises(ValidationError) as context:
            ChatAttachmentProcessor(
                additional_context = "context",
                attachment_ids = [""],
                urls = None,
                di = self.mock_di,
            )
        self.assertIn("Attachment ID cannot be empty", str(context.exception))

    def test_attachment_not_found_in_db(self):
        self.mock_chat_message_attachment_crud.get.return_value = None

        with self.assertRaises(NotFoundError) as context:
            ChatAttachmentProcessor(
                additional_context = "context",
                attachment_ids = ["nonexistent"],
                urls = None,
                di = self.mock_di,
            )
        self.assertIn("not found in DB", str(context.exception))

    # ── Audio path (unchanged behavior) ──────────────────────────────────

    @requests_mock.Mocker()
    def test_fetch_text_content_with_audio(self, m: requests_mock.Mocker):
        audio_attachment = _make_attachment(id = "2", mime_type = "audio/mpeg", extension = "mp3", url = "http://test.com/audio.mp3")
        m.get(str(audio_attachment.last_url), content = b"audio data", status_code = 200)

        mock_audio_instance = MagicMock()
        mock_audio_instance.execute.return_value = "Audio transcription"
        self.mock_di.audio_transcriber.return_value = mock_audio_instance

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["2"],
            urls = None,
            di = self.mock_di,
        )
        content = resolver.fetch_text_content(audio_attachment)

        self.assertEqual(content, "Audio transcription")
        mock_audio_instance.execute.assert_called_once()

    @requests_mock.Mocker()
    def test_fetch_text_content_with_unsupported_type(self, m: requests_mock.Mocker):
        unsupported_attachment = _make_attachment(
            id = "3", mime_type = "application/xxx", extension = "xxx", url = "http://test.com/file.xxx",
        )
        m.get(str(unsupported_attachment.last_url), content = b"data", status_code = 200)

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["3"],
            urls = None,
            di = self.mock_di,
        )
        content = resolver.fetch_text_content(unsupported_attachment)
        self.assertIsNone(content)

    # ── Document path: raw strategy ───────────────────────────────────────

    @requests_mock.Mocker()
    def test_execute_with_plain_text_raw_strategy(self, m: requests_mock.Mocker):
        txt_attachment = _make_attachment(id = "5", mime_type = "text/plain", extension = "txt", url = "http://test.com/notes.txt")
        self.mock_chat_message_attachment_crud.get.return_value = txt_attachment.model_dump()
        self.mock_chat_message_attachment_crud.save.return_value = txt_attachment.model_dump()
        self.mock_cache_crud.get.return_value = None
        small_text = "Hello world"
        m.get(str(txt_attachment.last_url), content = small_text.encode("utf-8"), status_code = 200)

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["5"],
            urls = None,
            di = self.mock_di,
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        content = resolver.result[0]["text_content"]
        self.assertIn(small_text, content)
        self.mock_di.document_search.assert_not_called()

    @requests_mock.Mocker()
    def test_execute_with_markdown_raw_strategy(self, m: requests_mock.Mocker):
        md_attachment = _make_attachment(id = "6", mime_type = "text/markdown", extension = "md", url = "http://test.com/readme.md")
        self.mock_chat_message_attachment_crud.get.return_value = md_attachment.model_dump()
        self.mock_chat_message_attachment_crud.save.return_value = md_attachment.model_dump()
        self.mock_cache_crud.get.return_value = None
        m.get(str(md_attachment.last_url), content = b"# Title\n\nSome content.", status_code = 200)

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["6"],
            urls = None,
            di = self.mock_di,
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        self.assertIn("# Title", resolver.result[0]["text_content"])
        self.mock_di.document_search.assert_not_called()

    # ── Document path: search strategy ───────────────────────────────────

    @requests_mock.Mocker()
    def test_execute_with_plain_text_search_strategy(self, m: requests_mock.Mocker):
        txt_attachment = _make_attachment(id = "7", mime_type = "text/plain", extension = "txt", url = "http://test.com/large.txt")
        self.mock_chat_message_attachment_crud.get.return_value = txt_attachment.model_dump()
        self.mock_chat_message_attachment_crud.save.return_value = txt_attachment.model_dump()
        self.mock_cache_crud.get.return_value = None
        large_text = "x" * (SEARCH_THRESHOLD_TOKENS * 3 + 3)
        m.get(str(txt_attachment.last_url), content = large_text.encode("utf-8"), status_code = 200)

        mock_search_instance = MagicMock()
        mock_search_instance.execute.return_value = "Search result summary"
        self.mock_di.document_search.return_value = mock_search_instance

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["7"],
            urls = None,
            di = self.mock_di,
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        self.assertEqual(resolver.result[0]["text_content"], "Search result summary")
        mock_search_instance.execute.assert_called_once()

    @requests_mock.Mocker()
    def test_execute_document_uses_search_strategy_at_threshold_boundary(self, m: requests_mock.Mocker):
        txt_attachment = _make_attachment(id = "8", mime_type = "text/plain", extension = "txt", url = "http://test.com/border.txt")
        self.mock_chat_message_attachment_crud.get.return_value = txt_attachment.model_dump()
        self.mock_chat_message_attachment_crud.save.return_value = txt_attachment.model_dump()
        self.mock_cache_crud.get.return_value = None
        # exactly at threshold (tokens = threshold, so raw applies)
        at_threshold_text = "x" * (SEARCH_THRESHOLD_TOKENS * 3)
        m.get(str(txt_attachment.last_url), content = at_threshold_text.encode("utf-8"), status_code = 200)

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["8"],
            urls = None,
            di = self.mock_di,
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        # at exactly threshold, raw strategy applies - document_search not called
        self.mock_di.document_search.assert_not_called()

    # ── Document path: empty extraction ──────────────────────────────────

    @requests_mock.Mocker()
    def test_execute_with_empty_document_returns_no_text_message(self, m: requests_mock.Mocker):
        txt_attachment = _make_attachment(id = "9", mime_type = "text/plain", extension = "txt", url = "http://test.com/empty.txt")
        self.mock_chat_message_attachment_crud.get.return_value = txt_attachment.model_dump()
        self.mock_chat_message_attachment_crud.save.return_value = txt_attachment.model_dump()
        self.mock_cache_crud.get.return_value = None
        m.get(str(txt_attachment.last_url), content = b"   \n\n  ", status_code = 200)

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["9"],
            urls = None,
            di = self.mock_di,
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        self.assertIn("no extractable text", resolver.result[0]["text_content"])
        self.mock_di.document_search.assert_not_called()

    # ── Document path: error handling ─────────────────────────────────────

    @requests_mock.Mocker()
    def test_execute_with_corrupt_document_stores_error_per_attachment(self, m: requests_mock.Mocker):
        bad_attachment = _make_attachment(
            id = "10",
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            extension = "docx",
            url = "http://test.com/corrupt.docx",
        )
        self.mock_chat_message_attachment_crud.get.return_value = bad_attachment.model_dump()
        self.mock_chat_message_attachment_crud.save.return_value = bad_attachment.model_dump()
        self.mock_cache_crud.get.return_value = None
        m.get(str(bad_attachment.last_url), content = b"not a zip", status_code = 200)

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["10"],
            urls = None,
            di = self.mock_di,
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.failed)
        self.assertIsNotNone(resolver.result[0]["error"])
        self.assertNotEqual(resolver.result[0]["error"], "<none>")

    @requests_mock.Mocker()
    def test_execute_one_bad_one_good_attachment_returns_partial(self, m: requests_mock.Mocker):
        image_attachment = _make_attachment(id = "1", mime_type = "image/png", extension = "png", url = "http://test.com/img.png")
        bad_attachment = _make_attachment(
            id = "11",
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            extension = "docx",
            url = "http://test.com/bad.docx",
        )

        def get_by_id(id):
            if id == "1":
                return image_attachment.model_dump()
            if id == "11":
                return bad_attachment.model_dump()
            return None

        def save_by_model(model):
            if model.id == "1":
                return image_attachment.model_dump()
            if model.id == "11":
                return bad_attachment.model_dump()
            return model.model_dump()

        self.mock_chat_message_attachment_crud.get.side_effect = get_by_id
        self.mock_chat_message_attachment_crud.save.side_effect = save_by_model
        self.mock_cache_crud.get.return_value = None
        m.get(str(image_attachment.last_url), content = b"img data", status_code = 200)
        m.get(str(bad_attachment.last_url), content = b"not a zip", status_code = 200)

        mock_cv_instance = MagicMock()
        mock_cv_instance.execute.return_value = "Image description"
        self.mock_di.computer_vision_analyzer.return_value = mock_cv_instance

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["1", "11"],
            urls = None,
            di = self.mock_di,
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.partial)
        results_by_id = {r["id"]: r for r in resolver.result}
        self.assertEqual(results_by_id["1"]["text_content"], "Image description")
        self.assertNotEqual(results_by_id["11"]["error"], "<none>")

    # ── Cache key includes strategy ───────────────────────────────────────

    @requests_mock.Mocker()
    def test_cache_key_includes_strategy_on_save(self, m: requests_mock.Mocker):
        txt_attachment = _make_attachment(id = "12", mime_type = "text/plain", extension = "txt", url = "http://test.com/doc.txt")
        self.mock_chat_message_attachment_crud.get.return_value = txt_attachment.model_dump()
        self.mock_chat_message_attachment_crud.save.return_value = txt_attachment.model_dump()
        self.mock_cache_crud.get.return_value = None
        m.get(str(txt_attachment.last_url), content = b"Short content", status_code = 200)

        resolver = ChatAttachmentProcessor(
            additional_context = "ctx",
            attachment_ids = ["12"],
            urls = None,
            di = self.mock_di,
        )
        resolver.execute()

        create_key_calls = [str(call) for call in self.mock_cache_crud.create_key.call_args_list]
        self.assertTrue(
            any("raw" in call for call in create_key_calls),
            f"Expected '{'raw'}' in cache key call args: {create_key_calls}",
        )

    @requests_mock.Mocker()
    def test_raw_and_search_cache_keys_do_not_collide(self, m: requests_mock.Mocker):
        txt_attachment = _make_attachment(id = "13", mime_type = "text/plain", extension = "txt", url = "http://test.com/small.txt")
        self.mock_chat_message_attachment_crud.get.return_value = txt_attachment.model_dump()
        self.mock_chat_message_attachment_crud.save.return_value = txt_attachment.model_dump()
        self.mock_cache_crud.get.return_value = None
        m.get(str(txt_attachment.last_url), content = b"Small text", status_code = 200)

        captured_keys: list[str] = []

        def capture_key(prefix, identifier):
            captured_keys.append(identifier)
            return f"{prefix}-{identifier}"

        self.mock_cache_crud.create_key.side_effect = capture_key

        resolver = ChatAttachmentProcessor(
            additional_context = "ctx",
            attachment_ids = ["13"],
            urls = None,
            di = self.mock_di,
        )
        resolver.execute()

        raw_keys = [k for k in captured_keys if "raw" in k]
        search_keys = [k for k in captured_keys if "search" in k]
        # save uses raw; lookup probes both - no raw key should equal a search key
        self.assertTrue(len(raw_keys) > 0)
        for rk in raw_keys:
            for sk in search_keys:
                self.assertNotEqual(rk, sk)

    # ── Encoding fallback ─────────────────────────────────────────────────

    @requests_mock.Mocker()
    def test_execute_with_latin1_encoded_file(self, m: requests_mock.Mocker):
        txt_attachment = _make_attachment(id = "14", mime_type = "text/plain", extension = "txt", url = "http://test.com/latin1.txt")
        self.mock_chat_message_attachment_crud.get.return_value = txt_attachment.model_dump()
        self.mock_chat_message_attachment_crud.save.return_value = txt_attachment.model_dump()
        self.mock_cache_crud.get.return_value = None
        latin1_bytes = "Héllo Wörld".encode("latin-1")
        m.get(str(txt_attachment.last_url), content = latin1_bytes, status_code = 200)

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["14"],
            urls = None,
            di = self.mock_di,
        )
        result = resolver.execute()

        # should succeed with replacement chars, not raise
        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        content = resolver.result[0]["text_content"]
        self.assertIsNotNone(content)

    # ── URL-resolved attachment tests (unchanged behavior) ─────────────────

    @requests_mock.Mocker()
    def test_url_resolved_attachment_skips_db_lookup(self, m: requests_mock.Mocker):
        virtual_url = "https://example.com/image.png"
        m.head(virtual_url, exc = ConnectionError("timeout"))
        m.get(virtual_url, content = b"image data", status_code = 200)
        self.mock_cache_crud.get.return_value = self.cache_entry.model_dump()

        mock_cv_instance = MagicMock()
        mock_cv_instance.execute.return_value = self.cached_content
        self.mock_di.computer_vision_analyzer.return_value = mock_cv_instance

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = [],
            di = self.mock_di,
            urls = [virtual_url],
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        self.assertEqual(len(resolver.result), 1)
        self.assertTrue(resolver.result[0]["id"].startswith("url-"))
        self.mock_chat_message_attachment_crud.get.assert_not_called()

    @requests_mock.Mocker()
    def test_url_resolved_merged_with_db_attachments(self, m: requests_mock.Mocker):
        virtual_url = "https://example.com/image.png"
        m.head(virtual_url, exc = ConnectionError("timeout"))
        m.get(virtual_url, content = b"image data", status_code = 200)
        m.get(str(self.attachment.last_url), content = b"image data", status_code = 200)
        self.mock_cache_crud.get.return_value = self.cache_entry.model_dump()

        mock_cv_instance = MagicMock()
        mock_cv_instance.execute.return_value = self.cached_content
        self.mock_di.computer_vision_analyzer.return_value = mock_cv_instance

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["1"],
            di = self.mock_di,
            urls = [virtual_url],
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        self.assertEqual(len(resolver.result), 2)
        result_ids = {r["id"] for r in resolver.result}
        self.assertTrue(any(rid.startswith("url-") for rid in result_ids))
        self.assertIn("1", result_ids)

    def test_empty_ids_and_no_urls_raises_error(self):
        with self.assertRaises(ValidationError) as context:
            ChatAttachmentProcessor(
                additional_context = "context",
                attachment_ids = [],
                urls = None,
                di = self.mock_di,
            )
        self.assertIn("No attachment IDs provided", str(context.exception))
