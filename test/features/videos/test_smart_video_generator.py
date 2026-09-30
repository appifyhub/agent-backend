import json
from dataclasses import replace
from threading import Thread
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_chat_model import FakeChatModel
from fakes.fake_http_client import FakeHTTPClient
from fakes.fake_replicate_client import FakeReplicateClient
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from util.di_utils import di_for_tests
from util.thread_utils import BackgroundThreads

from di.di import DI
from features.chat.llm_tools.llm_tool_library import ALL_LLM_TOOLS, generate_video
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import GPT_5_NANO, VIDEO_GEN_P_VIDEO
from features.videos import smart_video_generator
from features.videos.smart_video_generator import SmartVideoGenerator
from util.error_codes import INSUFFICIENT_CREDITS, MISSING_CONTENT, VIDEO_GENERATION_FAILED
from util.errors import ExternalServiceError, ValidationError


class SmartVideoGeneratorTest(TestCase):

    di: DI
    copywriter: FakeChatModel
    provider: FakeReplicateClient
    bot: FakeTelegramBotAPI
    http: FakeHTTPClient
    workers: BackgroundThreads
    copywriter_tool: ConfiguredTool
    video_tool: ConfiguredTool
    generator: SmartVideoGenerator

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user(
            tool_choice_videos_gen = VIDEO_GEN_P_VIDEO.id,
        )))
        self.di.inject_invoker_chat(self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = "12345")))
        self.copywriter_tool = stubs.domain.configured_tool(definition = GPT_5_NANO, purpose = ToolType.copywriting)
        self.video_tool = stubs.domain.configured_tool(
            definition = VIDEO_GEN_P_VIDEO,
            purpose = ToolType.videos_gen,
        )
        self.copywriter = cast(FakeChatModel, self.di.base_chat_langchain_model(self.copywriter_tool))
        self.provider = cast(FakeReplicateClient, self.di.base_replicate_client(self.video_tool.token.get_secret_value()))
        self.bot = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.copywriter.responses.append(stubs.external.ai_message(content = "Enhanced video prompt"))
        self.provider.predictions.responses.append(stubs.external.replicate_prediction(output = "https://example.com/video.mp4"))
        self.http.responses["https://example.com/video.mp4"].append(
            stubs.external.http_response(content = stubs.external.video_bytes()),
        )
        self.workers = BackgroundThreads()
        # plain threads need the test context; their real worker bodies still execute
        self.enterContext(patch.object(smart_video_generator, "Thread", new = self.workers.create))
        self.addCleanup(self.workers.finish)
        self.generator = self.di.smart_video_generator(
            raw_prompt = "Make them shake hands",
            attachment_ids = [],
            urls = [],
            configured_copywriter_tool = self.copywriter_tool,
            configured_video_gen_tool = self.video_tool,
        )

    def test_constructor_rejects_empty_prompt_before_resolving_attachments(self):
        with self.assertRaises(ValidationError) as context:
            self.di.smart_video_generator(
                raw_prompt = " ",
                attachment_ids = ["missing-attachment"],
                urls = [],
                configured_copywriter_tool = self.copywriter_tool,
                configured_video_gen_tool = self.video_tool,
            )

        self.assertEqual(context.exception.error_code, MISSING_CONTENT)
        self.assertEqual(self.http.requests, [])

    def test_execute_screenwrites_synchronously_before_starting_worker(self):
        result = self.generator.execute()

        self.assertEqual(result["status"], "started")
        self.assertEqual(result["used_reference_images"], 0)
        self.assertEqual(result["ignored_reference_images"], 0)
        self.assertEqual(len(self.copywriter.prompts), 1)
        self.assertEqual(self.copywriter.prompts[0][-1].content, "Make them shake hands")
        self.assertEqual(self.provider.predictions.requests, [])
        self.assertEqual(self.bot.get_sent_messages("12345"), [])
        self.workers.finish()
        self.assertEqual(self.provider.predictions.requests[0][1]["input"]["prompt"], "Enhanced video prompt")

    def test_llm_tool_parses_references_and_returns_immediate_acknowledgement(self):
        for attachment_id in ("first", "second"):
            self.di.chat_attachment_service.save(
                stubs.domain.chat_attachment(id = attachment_id, external_id = None),
                content = stubs.external.image_bytes(),
            )
        for url in ("https://example.com/first.png", "https://example.com/second.png"):
            self.http.responses[url].append(stubs.external.http_response(content = stubs.external.image_bytes()))
        result = json.loads(generate_video(
            di = self.di,
            prompt = "Make them shake hands",
            attachment_ids = "first, second",
            urls = "https://example.com/first.png, https://example.com/second.png",
            aspect_ratio = "16:9",
            size = "2K",
        ))

        self.assertIs(ALL_LLM_TOOLS["generate_video"], generate_video)
        self.assertEqual(result["result"], "Success")
        self.assertEqual(result["status"], "started")
        self.assertEqual(result["used_reference_images"], 1)
        self.assertEqual(result["ignored_reference_images"], 3)
        self.assertEqual(self.provider.predictions.requests, [])
        self.workers.finish()
        self.assertEqual(self.provider.predictions.requests[0][1]["input"]["resolution"], "1080p")

    def test_execute_retains_first_supported_reference(self):
        for attachment_id in ("first", "ignored"):
            self.di.chat_attachment_service.save(
                stubs.domain.chat_attachment(id = attachment_id, external_id = None),
                content = stubs.external.image_bytes(),
            )
        generator = self.di.smart_video_generator(
            raw_prompt = "Make them shake hands",
            attachment_ids = ["first", "ignored"],
            urls = [],
            configured_copywriter_tool = self.copywriter_tool,
            configured_video_gen_tool = self.video_tool,
        )

        result = generator.execute()
        self.workers.finish()

        self.assertEqual(result["used_reference_images"], 1)
        self.assertEqual(result["ignored_reference_images"], 1)
        references = self.di.chat_attachment_service.resolve_image_attachments(
            [], [self.provider.predictions.requests[0][1]["input"]["image"]],
        )
        self.assertEqual([attachment.id for attachment in references], ["first"])

    def test_execute_stops_before_screenwriting_when_preflight_fails(self):
        self.di.user_repo.save(replace(self.di.invoker, credit_balance = -1))
        generator = self.di.smart_video_generator(
            raw_prompt = "Make them shake hands",
            attachment_ids = [],
            urls = [],
            configured_copywriter_tool = self.copywriter_tool,
            configured_video_gen_tool = replace(self.video_tool, uses_credits = True, payer_id = self.di.invoker.id),
        )

        with self.assertRaises(ValidationError) as context:
            generator.execute()

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.copywriter.prompts, [])
        self.assertEqual(self.workers.threads, [])

    def test_execute_rejects_busy_service_after_screenwriting(self):
        while smart_video_generator.VIDEO_GENERATION_SLOTS.acquire(blocking = False):
            self.addCleanup(smart_video_generator.VIDEO_GENERATION_SLOTS.release)

        with self.assertRaises(ExternalServiceError) as context:
            self.generator.execute()

        self.assertEqual(context.exception.error_code, VIDEO_GENERATION_FAILED)
        self.assertEqual(len(self.copywriter.prompts), 1)
        self.assertEqual(self.workers.threads, [])

    def test_execute_does_not_acquire_slot_when_screenwriting_fails(self):
        self.copywriter.responses.clear()
        self.copywriter.responses.append(ExternalServiceError("Copywriter unavailable", VIDEO_GENERATION_FAILED))
        with self.assertRaises(ExternalServiceError):
            self.generator.execute()

        self.assertEqual(self.workers.threads, [])
        self.assertEqual(self.provider.predictions.requests, [])
        acquired = 0
        try:
            while smart_video_generator.VIDEO_GENERATION_SLOTS.acquire(blocking = False):
                acquired += 1
            self.assertEqual(acquired, 16)
        finally:
            for _ in range(acquired):
                smart_video_generator.VIDEO_GENERATION_SLOTS.release()

    def test_execute_releases_slot_when_thread_start_fails(self):
        # OS thread startup failure cannot be reproduced reliably with normal threads
        with patch.object(Thread, "start", side_effect = RuntimeError("Thread unavailable")):
            with self.assertRaises(ExternalServiceError) as context:
                self.generator.execute()

        self.assertEqual(context.exception.error_code, VIDEO_GENERATION_FAILED)
        acquired = 0
        try:
            while smart_video_generator.VIDEO_GENERATION_SLOTS.acquire(blocking = False):
                acquired += 1
            self.assertEqual(acquired, 16)
        finally:
            for _ in range(acquired):
                smart_video_generator.VIDEO_GENERATION_SLOTS.release()

    def test_background_worker_sets_upload_action_delivers_and_releases_slot(self):
        self.generator.execute()
        self.workers.finish()

        self.assertEqual(self.bot.statuses["12345"], "upload_video")
        messages = self.bot.get_sent_messages("12345")
        self.assertEqual(len(messages), 1)
        self.assertGreater(len(messages[0]["content"]), 0)
        self.assertEqual(messages[0]["metadata"].video_codecs, ("h264",))
        acquired = 0
        try:
            while smart_video_generator.VIDEO_GENERATION_SLOTS.acquire(blocking = False):
                acquired += 1
            self.assertEqual(acquired, 16)
        finally:
            for _ in range(acquired):
                smart_video_generator.VIDEO_GENERATION_SLOTS.release()

    def test_background_worker_notifies_chat_with_formatted_failure(self):
        cases = [
            (ExternalServiceError("Provider unavailable", VIDEO_GENERATION_FAILED), "Provider unavailable"),
            (RuntimeError("Unexpected provider failure"), "Could not create Replicate video prediction"),
        ]
        self.provider.predictions.responses.clear()
        self.copywriter.responses.clear()
        for index, (response, expected_detail) in enumerate(cases):
            with self.subTest(failure = expected_detail):
                self.provider.predictions.responses.append(response)
                self.copywriter.responses.extend([
                    stubs.external.ai_message(content = "Enhanced video prompt"),
                    stubs.external.ai_message(content = "Localized video failure notification"),
                ])

                self.generator.execute()
                self.workers.finish()

                messages = self.bot.get_sent_messages("12345")
                self.assertEqual(len(messages), index + 1)
                self.assertEqual(messages[-1]["text"], "Localized video failure notification")
                self.assertIn(expected_detail, str(self.copywriter.prompts[-1]))
