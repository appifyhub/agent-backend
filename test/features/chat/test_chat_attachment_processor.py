import unittest
from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import MagicMock
from uuid import UUID

import requests_mock
from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.chat_attachment_service import ChatAttachmentService
from features.chat.chat_attachment_processor import CACHE_PREFIX, CACHE_TTL, SEARCH_THRESHOLD_TOKENS, ChatAttachmentProcessor
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.documents.docx_loader import DocxLoader
from features.documents.plain_text_loader import PlainTextLoader
from features.integrations.platform_bot_sdk import PlatformBotSDK
from features.tools_cache.tools_cache import ToolsCache
from features.tools_cache.tools_cache_repo import ToolsCacheRepository
from features.users.user import User
from util.config import config
from util.errors import NotFoundError, ValidationError
from util.functions import digest_md5


def _make_attachment(
    id: str = "1",
    mime_type: str = "image/png",
    extension: str = "png",
    url: str = "http://test.com/file.png",
) -> ChatAttachment:
    return ChatAttachment(
        id = id,
        external_id = f"external_{id}",
        chat_id = UUID(int = 1),
        uploader_user_id = UUID(int = 9),
        message_id = id,
        mime_type = mime_type,
        extension = extension,
        last_url = url,
    )


class ChatAttachmentProcessorTest(unittest.TestCase):

    def setUp(self):
        config.web_retries = 1
        config.web_retry_delay_s = 0
        config.web_timeout_s = 1

        self.mock_di = MagicMock()
        self.mock_cache_repo = MagicMock(spec = ToolsCacheRepository)
        self.mock_chat_attachment_repo = MagicMock()
        self.mock_access_token_resolver = MagicMock()
        self.mock_di.tools_cache_repo = self.mock_cache_repo
        self.mock_di.chat_attachment_repo = self.mock_chat_attachment_repo
        self.mock_di.chat_attachment_service.save.side_effect = (
            lambda attachment, content = None: self.mock_chat_attachment_repo.save(attachment)
        )
        attachment_service = ChatAttachmentService(self.mock_di)
        self.mock_di.chat_attachment_service.resolve_attachments.side_effect = attachment_service.resolve_attachments
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
        self.attachment = _make_attachment()

        self.mock_chat_attachment_repo.get.return_value = self.attachment
        self.mock_chat_attachment_repo.save.return_value = self.attachment
        self.mock_di.require_invoker_chat_type = MagicMock(return_value = ChatConfigDB.ChatType.telegram)

        self.mock_di.telegram_bot_sdk = TelegramBotSDK(self.mock_di)
        self.mock_di.platform_bot_sdk = MagicMock(return_value = PlatformBotSDK(self.mock_di))
        self.mock_di.plain_text_loader.side_effect = lambda job_id, document_url: PlainTextLoader(job_id, document_url)
        self.mock_di.docx_loader.side_effect = lambda job_id, document_url: DocxLoader(job_id, document_url)

        # storage reads return attachment content directly
        self.mock_di.attachment_storage.open.side_effect = lambda att: BytesIO(b"image data")

        # public URL generation returns the original last_url (so requests_mock still intercepts)
        self.mock_di.chat_attachment_service.create_public_url.side_effect = (
            lambda att: MagicMock(url = att.last_url)
        )

    # ── Image cache tests (unchanged behavior) ────────────────────────────

    @requests_mock.Mocker()
    def test_execute_with_cache_hit(self, m: requests_mock.Mocker):
        m.get(str(self.attachment.last_url), content = b"image data", status_code = 200)
        self.mock_cache_repo.get.return_value = self.cache_entry

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
        self.mock_cache_repo.get.return_value = None

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
        self.mock_cache_repo.save.assert_called_once()

    @requests_mock.Mocker()
    def test_execute_with_expired_cache_entry_refreshes_content(self, m: requests_mock.Mocker):
        m.get(str(self.attachment.last_url), content = b"image data", status_code = 200)
        self.mock_cache_repo.get.return_value = ToolsCache(
            key = "expired_cache_key",
            value = "expired content",
            expires_at = datetime.now() - timedelta(seconds = 1),
        )

        mock_cv_instance = MagicMock()
        mock_cv_instance.execute.return_value = self.cached_content
        self.mock_di.computer_vision_analyzer.return_value = mock_cv_instance
        self.mock_di.tool_choice_resolver.require_tool.return_value = MagicMock()

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["1"],
            urls = None,
            di = self.mock_di,
        )
        result = resolver.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        self.assertEqual(resolver.result[0]["text_content"], self.cached_content)
        mock_cv_instance.execute.assert_called_once()
        self.mock_cache_repo.save.assert_called_once()

    # ── Validation / not-found tests (unchanged behavior) ─────────────────

    def test_empty_attachment_ids_list(self):
        with self.assertRaises(ValidationError) as context:
            ChatAttachmentProcessor(
                additional_context = "context",
                attachment_ids = [],
                urls = None,
                di = self.mock_di,
            )
        self.assertIn("No attachment IDs or URLs provided", str(context.exception))

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
        self.mock_chat_attachment_repo.get.return_value = None

        with self.assertRaises(NotFoundError) as context:
            ChatAttachmentProcessor(
                additional_context = "context",
                attachment_ids = ["nonexistent"],
                urls = None,
                di = self.mock_di,
            )
        self.assertIn("not found", str(context.exception))

    # ── Audio path ────────────────────────────────────────────

    def test_fetch_text_content_with_audio(self):
        audio_attachment = _make_attachment(id = "2", mime_type = "audio/mpeg", extension = "mp3", url = "http://test.com/audio.mp3")
        self.mock_di.attachment_storage.open.side_effect = lambda attachment: BytesIO(b"audio data")

        mock_audio_instance = MagicMock()
        mock_audio_instance.execute.return_value = "Audio transcription"
        self.mock_di.audio_transcriber.return_value = mock_audio_instance
        transcriber_tool = MagicMock()
        copywriter_tool = MagicMock()
        self.mock_di.tool_choice_resolver.require_tool.side_effect = [transcriber_tool, copywriter_tool]

        resolver = ChatAttachmentProcessor(
            additional_context = "context",
            attachment_ids = ["2"],
            urls = None,
            di = self.mock_di,
        )
        content = resolver.fetch_text_content(audio_attachment)

        self.assertEqual(content, "Audio transcription")
        self.mock_di.audio_transcriber.assert_called_once_with(
            job_id = "2",
            audio_content = b"audio data",
            extension = "mp3",
            transcriber_tool = transcriber_tool,
            copywriter_tool = copywriter_tool,
        )
        self.mock_di.chat_attachment_service.create_public_url.assert_not_called()
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
        self.mock_chat_attachment_repo.get.return_value = txt_attachment
        self.mock_chat_attachment_repo.save.return_value = txt_attachment
        self.mock_cache_repo.get.return_value = None
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
        self.mock_chat_attachment_repo.get.return_value = md_attachment
        self.mock_chat_attachment_repo.save.return_value = md_attachment
        self.mock_cache_repo.get.return_value = None
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
        self.mock_chat_attachment_repo.get.return_value = txt_attachment
        self.mock_chat_attachment_repo.save.return_value = txt_attachment
        self.mock_cache_repo.get.return_value = None
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
        self.mock_chat_attachment_repo.get.return_value = txt_attachment
        self.mock_chat_attachment_repo.save.return_value = txt_attachment
        self.mock_cache_repo.get.return_value = None
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
        self.mock_chat_attachment_repo.get.return_value = txt_attachment
        self.mock_chat_attachment_repo.save.return_value = txt_attachment
        self.mock_cache_repo.get.return_value = None
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
        self.mock_chat_attachment_repo.get.return_value = bad_attachment
        self.mock_chat_attachment_repo.save.return_value = bad_attachment
        self.mock_cache_repo.get.return_value = None
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
                return image_attachment
            if id == "11":
                return bad_attachment
            return None

        def save_by_model(model):
            if model.id == "1":
                return image_attachment
            if model.id == "11":
                return bad_attachment
            return model

        self.mock_chat_attachment_repo.get.side_effect = get_by_id
        self.mock_chat_attachment_repo.save.side_effect = save_by_model
        self.mock_cache_repo.get.return_value = None
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
        self.mock_chat_attachment_repo.get.return_value = txt_attachment
        self.mock_chat_attachment_repo.save.return_value = txt_attachment
        self.mock_cache_repo.get.return_value = None
        m.get(str(txt_attachment.last_url), content = b"Short content", status_code = 200)

        resolver = ChatAttachmentProcessor(
            additional_context = "ctx",
            attachment_ids = ["12"],
            urls = None,
            di = self.mock_di,
        )
        resolver.execute()

        context_hash = digest_md5("ctx")
        expected_key = ToolsCache.create_key(CACHE_PREFIX, f"12-raw-{context_hash}")
        saved_entry = self.mock_cache_repo.save.call_args.args[0]
        self.assertEqual(saved_entry.key, expected_key)

    @requests_mock.Mocker()
    def test_raw_and_search_cache_keys_do_not_collide(self, m: requests_mock.Mocker):
        txt_attachment = _make_attachment(id = "13", mime_type = "text/plain", extension = "txt", url = "http://test.com/small.txt")
        self.mock_chat_attachment_repo.get.return_value = txt_attachment
        self.mock_chat_attachment_repo.save.return_value = txt_attachment
        self.mock_cache_repo.get.return_value = None
        m.get(str(txt_attachment.last_url), content = b"Small text", status_code = 200)

        resolver = ChatAttachmentProcessor(
            additional_context = "ctx",
            attachment_ids = ["13"],
            urls = None,
            di = self.mock_di,
        )
        resolver.execute()

        context_hash = digest_md5("ctx")
        raw_key = ToolsCache.create_key(CACHE_PREFIX, f"13-raw-{context_hash}")
        search_key = ToolsCache.create_key(CACHE_PREFIX, f"13-search-{context_hash}")
        self.assertNotEqual(raw_key, search_key)
        self.mock_cache_repo.get.assert_any_call(raw_key)
        self.mock_cache_repo.get.assert_any_call(search_key)

    # ── Encoding fallback ─────────────────────────────────────────────────

    @requests_mock.Mocker()
    def test_execute_with_latin1_encoded_file(self, m: requests_mock.Mocker):
        txt_attachment = _make_attachment(id = "14", mime_type = "text/plain", extension = "txt", url = "http://test.com/latin1.txt")
        self.mock_chat_attachment_repo.get.return_value = txt_attachment
        self.mock_chat_attachment_repo.save.return_value = txt_attachment
        self.mock_cache_repo.get.return_value = None
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
        self.mock_cache_repo.get.return_value = self.cache_entry

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
        self.assertIsNotNone(resolver.result[0]["id"])

    @requests_mock.Mocker()
    def test_url_resolved_merged_with_db_attachments(self, m: requests_mock.Mocker):
        virtual_url = "https://example.com/image.png"
        m.head(virtual_url, exc = ConnectionError("timeout"))
        m.get(virtual_url, content = b"image data", status_code = 200)
        m.get(str(self.attachment.last_url), content = b"image data", status_code = 200)
        self.mock_cache_repo.get.return_value = self.cache_entry

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
        self.assertIn("1", result_ids)

    def test_empty_ids_and_no_urls_raises_error(self):
        with self.assertRaises(ValidationError) as context:
            ChatAttachmentProcessor(
                additional_context = "context",
                attachment_ids = [],
                urls = None,
                di = self.mock_di,
            )
        self.assertIn("No attachment IDs or URLs provided", str(context.exception))
