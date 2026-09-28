from datetime import datetime, timedelta
from re import Pattern, compile, escape
from typing import cast
from unittest import TestCase

from fakes.fake_chat_model import FakeChatModel
from fakes.fake_http_client import FakeHTTPClient
from fakes.fake_openai_client import FakeOpenAIClient
from requests_mock import Mocker
from stubs import domain, external
from util.di_utils import di_for_tests

from di.di import DI
from features.chat.attachment.chat_attachment_service import ChatAttachmentService
from features.chat.chat_attachment_processor import CACHE_PREFIX, CACHE_TTL, SEARCH_THRESHOLD_TOKENS, ChatAttachmentProcessor
from features.tools_cache.tools_cache import ToolsCache
from features.tools_cache.tools_cache_repo import ToolsCacheRepository
from util.config import config
from util.errors import NotFoundError, ValidationError
from util.functions import digest_md5


class ChatAttachmentProcessorTest(TestCase):

    di: DI
    attachments: ChatAttachmentService
    cache: ToolsCacheRepository
    model: FakeChatModel
    http: FakeHTTPClient
    openai: FakeOpenAIClient
    document_url_pattern: Pattern[str]

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(domain.user()))
        self.di.inject_invoker_chat(self.di.chat_config_repo.save(domain.chat_config()))
        self.attachments = self.di.chat_attachment_service
        self.cache = self.di.tools_cache_repo
        tool = domain.configured_tool()
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(tool, max_tokens = 500))
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.openai = cast(FakeOpenAIClient, self.di.base_open_ai_client(tool))
        # signed links vary with their issuance time; match the public download endpoint
        self.document_url_pattern = compile(escape(f"{config.public_api_base_url}/attachments/public/") + r"[^/]+")

    def __cache_key(self, id: str, context: str = "context", strategy: str | None = None) -> str:
        suffix = f"{id}-{strategy}" if strategy else id
        return ToolsCache.create_key(CACHE_PREFIX, f"{suffix}-{digest_md5(context)}")

    def test_execute_with_cache_hit(self):
        attachment = self.attachments.save(domain.chat_attachment(), content = b"image data")
        self.cache.save(domain.tools_cache(
            key = self.__cache_key(attachment.id), value = "cached description", expires_at = datetime.now() + CACHE_TTL,
        ))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(processor.execute(), ChatAttachmentProcessor.Result.success)
        self.assertEqual(processor.result[0]["text_content"], "cached description")
        self.assertEqual(self.model.prompts, [])

    def test_execute_with_cache_miss(self):
        attachment = self.attachments.save(domain.chat_attachment(), content = b"image data")
        self.model.responses.append(external.ai_message(content = "Image description"))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )
        started = datetime.now()

        self.assertEqual(processor.execute(), ChatAttachmentProcessor.Result.success)
        self.assertEqual(processor.result[0]["text_content"], "Image description")
        saved = self.cache.get(self.__cache_key(attachment.id))
        self.assertEqual(saved.value, "Image description")
        self.assertGreaterEqual(saved.expires_at, started + CACHE_TTL)
        self.assertLessEqual(saved.expires_at, datetime.now() + CACHE_TTL)

    def test_execute_with_expired_cache(self):
        attachment = self.attachments.save(domain.chat_attachment(), content = b"image data")
        self.cache.save(domain.tools_cache(
            key = self.__cache_key(attachment.id), value = "old", expires_at = datetime.now() - timedelta(seconds = 1),
        ))
        self.model.responses.append(external.ai_message(content = "Fresh description"))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(processor.execute(), ChatAttachmentProcessor.Result.success)
        self.assertEqual(processor.result[0]["text_content"], "Fresh description")
        self.assertEqual(self.cache.get(self.__cache_key(attachment.id)).value, "Fresh description")

    def test_empty_attachment_ids_list(self):
        with self.assertRaisesRegex(ValidationError, "No attachment IDs or URLs provided"):
            self.di.chat_attachment_processor(
                additional_context = "context",
                attachment_ids = [],
                urls = None,
            )

    def test_empty_attachment_id_string(self):
        with self.assertRaisesRegex(ValidationError, "Attachment ID cannot be empty"):
            self.di.chat_attachment_processor(
                additional_context = "context",
                attachment_ids = [""],
                urls = None,
            )

    def test_attachment_not_found(self):
        with self.assertRaises(NotFoundError):
            self.di.chat_attachment_processor(
                additional_context = "context",
                attachment_ids = ["nonexistent"],
                urls = None,
            )

    def test_fetch_text_content_with_audio(self):
        attachment = self.attachments.save(
            domain.chat_attachment(id = "audio", mime_type = "audio/mpeg", extension = "mp3"),
            content = b"audio data",
        )
        self.openai.audio.transcriptions.responses.append(external.openai_transcription())
        self.model.responses.append(external.ai_message(content = "Audio transcription"))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(processor.fetch_text_content(attachment), "Audio transcription")
        self.assertEqual(self.http.requests, [])

    def test_fetch_text_content_with_video_returns_unsupported_without_reading(self):
        attachment = domain.chat_attachment(id = "video", mime_type = "video/mp4", extension = "mp4")
        self.di.chat_attachment_repo.save(attachment)
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(processor.fetch_text_content(attachment), "Video attachment 'video' is unsupported for analysis")
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.openai.audio.transcriptions.recordings, [])

    def test_fetch_text_content_with_unsupported_type(self):
        attachment = self.attachments.save(
            domain.chat_attachment(id = "unknown", mime_type = "application/xxx", extension = "xxx"),
            content = b"data",
        )
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertIsNone(processor.fetch_text_content(attachment))

    def test_execute_with_plain_text_raw_strategy(self):
        content = b"Hello world"
        attachment = self.attachments.save(
            domain.chat_attachment(
                id = "document", external_id = None,
                mime_type = "text/plain", extension = "txt",
            ),
            content = content,
        )
        self.http.responses[self.document_url_pattern].append(external.http_response(content = content))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(processor.execute(), ChatAttachmentProcessor.Result.success)
        self.assertIn("Hello world", processor.result[0]["text_content"])
        self.assertEqual(self.model.prompts, [])
        self.assertEqual(self.openai.embeddings.inputs, [])

    def test_execute_with_markdown_raw_strategy(self):
        content = b"# Title\n\nSome content."
        attachment = self.attachments.save(
            domain.chat_attachment(
                id = "document", external_id = None,
                mime_type = "text/markdown", extension = "md",
            ),
            content = content,
        )
        self.http.responses[self.document_url_pattern].append(external.http_response(content = content))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(processor.execute(), ChatAttachmentProcessor.Result.success)
        self.assertIn("# Title", processor.result[0]["text_content"])
        self.assertEqual(self.model.prompts, [])

    def test_execute_with_plain_text_search_strategy(self):
        content = b"x" * (SEARCH_THRESHOLD_TOKENS * 3 + 3)
        attachment = self.attachments.save(
            domain.chat_attachment(
                id = "document", external_id = None,
                mime_type = "text/plain", extension = "txt",
            ),
            content = content,
        )
        self.http.responses[self.document_url_pattern].append(external.http_response(content = content))
        self.openai.embeddings.vector = [1.0, 0.0]
        self.model.responses.append(external.ai_message(content = "Search result summary"))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(processor.execute(), ChatAttachmentProcessor.Result.success)
        self.assertIn("Search result summary", processor.result[0]["text_content"])
        saved = self.cache.get(self.__cache_key(attachment.id, strategy = "search"))
        self.assertEqual(saved.value, processor.result[0]["text_content"])
        self.assertIsNone(self.cache.get(self.__cache_key(attachment.id, strategy = "raw")))

    def test_execute_document_uses_raw_strategy_at_threshold_boundary(self):
        text = "x" * (SEARCH_THRESHOLD_TOKENS * 3)
        content = text.encode()
        attachment = self.attachments.save(
            domain.chat_attachment(
                id = "document", external_id = None,
                mime_type = "text/plain", extension = "txt",
            ),
            content = content,
        )
        self.http.responses[self.document_url_pattern].append(external.http_response(content = content))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(processor.execute(), ChatAttachmentProcessor.Result.success)
        self.assertIn(text, processor.result[0]["text_content"])
        self.assertEqual(self.openai.embeddings.inputs, [])
        self.assertEqual(self.model.prompts, [])

    def test_execute_with_empty_document_returns_no_text_message(self):
        content = b"   \n\n  "
        attachment = self.attachments.save(
            domain.chat_attachment(
                id = "document", external_id = None,
                mime_type = "text/plain", extension = "txt",
            ),
            content = content,
        )
        self.http.responses[self.document_url_pattern].append(external.http_response(content = content))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(processor.execute(), ChatAttachmentProcessor.Result.success)
        self.assertIn("no extractable text", processor.result[0]["text_content"])
        self.assertEqual(self.model.prompts, [])

    def test_execute_with_corrupt_document_stores_error_per_attachment(self):
        content = b"not a zip"
        attachment = self.attachments.save(
            domain.chat_attachment(
                id = "document", external_id = None,
                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document", extension = "docx",
            ),
            content = content,
        )
        self.http.responses[self.document_url_pattern].append(external.http_response(content = content))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(processor.execute(), ChatAttachmentProcessor.Result.failed)
        self.assertEqual(processor.result[0]["text_content"], "<unresolved>")
        self.assertNotEqual(processor.result[0]["error"], "<none>")

    def test_execute_one_bad_one_good_attachment_returns_partial(self):
        image = self.attachments.save(domain.chat_attachment(), content = b"image data")
        content = b"not a zip"
        bad = self.attachments.save(
            domain.chat_attachment(
                id = "document", external_id = None,
                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document", extension = "docx",
            ),
            content = content,
        )
        self.http.responses[self.document_url_pattern].append(external.http_response(content = content))
        self.model.responses.append(external.ai_message(content = "Image description"))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [image.id, bad.id],
            urls = None,
        )

        self.assertEqual(processor.execute(), ChatAttachmentProcessor.Result.partial)
        results = {result["id"]: result for result in processor.result}
        self.assertEqual(results[image.id]["text_content"], "Image description")
        self.assertNotEqual(results[bad.id]["error"], "<none>")

    def test_cache_key_includes_strategy_on_save(self):
        content = b"Short content"
        attachment = self.attachments.save(
            domain.chat_attachment(
                id = "document", external_id = None,
                mime_type = "text/plain", extension = "txt",
            ),
            content = content,
        )
        self.http.responses[self.document_url_pattern].append(external.http_response(content = content))
        processor = self.di.chat_attachment_processor(
            additional_context = "ctx",
            attachment_ids = [attachment.id],
            urls = None,
        )

        processor.execute()

        self.assertEqual(
            self.cache.get(self.__cache_key(attachment.id, context = "ctx", strategy = "raw")).value,
            processor.result[0]["text_content"],
        )
        self.assertIsNone(self.cache.get(self.__cache_key(attachment.id, context = "ctx", strategy = "search")))

    def test_raw_and_search_cache_keys_do_not_collide(self):
        content = b"Small text"
        attachment = self.attachments.save(
            domain.chat_attachment(
                id = "document", external_id = None,
                mime_type = "text/plain", extension = "txt",
            ),
            content = content,
        )
        self.http.responses[self.document_url_pattern].append(external.http_response(content = content))
        search_key = self.__cache_key(attachment.id, strategy = "search")
        self.cache.save(domain.tools_cache(key = search_key, value = "Search cache", expires_at = datetime.now() + CACHE_TTL))
        cached = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )
        self.assertEqual(cached.execute(), ChatAttachmentProcessor.Result.success)
        self.assertEqual(cached.result[0]["text_content"], "Search cache")
        self.assertEqual(self.http.requests, [])
        self.cache.save(domain.tools_cache(key = search_key, value = "Search cache", expires_at = datetime.now() - CACHE_TTL))
        fresh = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(fresh.execute(), ChatAttachmentProcessor.Result.success)
        self.assertIn("Small text", fresh.result[0]["text_content"])
        self.assertEqual(self.cache.get(search_key).value, "Search cache")
        self.assertEqual(self.cache.get(self.__cache_key(attachment.id, strategy = "raw")).value, fresh.result[0]["text_content"])

    def test_execute_with_latin1_encoded_file(self):
        content = "Héllo Wörld".encode("latin-1")
        attachment = self.attachments.save(
            domain.chat_attachment(
                id = "document", external_id = None,
                mime_type = "text/plain", extension = "txt",
            ),
            content = content,
        )
        self.http.responses[self.document_url_pattern].append(external.http_response(content = content))
        processor = self.di.chat_attachment_processor(
            additional_context = "context",
            attachment_ids = [attachment.id],
            urls = None,
        )

        self.assertEqual(processor.execute(), ChatAttachmentProcessor.Result.success)
        self.assertIn("H�llo W�rld", processor.result[0]["text_content"])

    def test_url_resolved_attachment_is_processed(self):
        self.model.responses.append(external.ai_message(content = "Image description"))
        # URL ingestion uses requests directly; only its external transport is substituted
        with Mocker() as transport:
            transport.get("https://example.com/image.png", content = b"image data", headers = {"Content-Type": "image/png"})
            processor = self.di.chat_attachment_processor(
                additional_context = "context",
                attachment_ids = [],
                urls = ["https://example.com/image.png"],
            )
            result = processor.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        self.assertEqual(len(processor.result), 1)
        self.assertEqual(processor.result[0]["text_content"], "Image description")

    def test_url_resolved_merged_with_stored_attachments(self):
        attachment = self.attachments.save(domain.chat_attachment(), content = b"image data")
        self.model.responses.append(external.ai_message(content = "Combined image description"))
        # URL ingestion uses requests directly; only its external transport is substituted
        with Mocker() as transport:
            transport.get("https://example.com/image.png", content = b"image data", headers = {"Content-Type": "image/png"})
            processor = self.di.chat_attachment_processor(
                additional_context = "context",
                attachment_ids = [attachment.id],
                urls = ["https://example.com/image.png"],
            )
            result = processor.execute()

        self.assertEqual(result, ChatAttachmentProcessor.Result.success)
        self.assertEqual(len(processor.result), 2)
        self.assertIn(attachment.id, {item["id"] for item in processor.result})
        self.assertEqual([item["text_content"] for item in processor.result], ["Combined image description"] * 2)
