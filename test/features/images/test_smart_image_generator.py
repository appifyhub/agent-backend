import json
from dataclasses import replace
from re import compile, escape
from threading import Thread
from typing import cast
from unittest import TestCase
from unittest.mock import patch

import stubs
from fakes.fake_chat_model import FakeChatModel
from fakes.fake_http_client import FakeHTTPClient
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from fakes.fake_x_ai_client import FakeXAIClient
from util.di_utils import di_for_tests
from util.thread_utils import BackgroundThreads

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.llm_tools.llm_tool_library import ALL_LLM_TOOLS, generate_image
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import GPT_5_NANO, IMAGE_GEN_GROK_IMAGINE_QUALITY
from features.images import smart_image_generator
from features.images.smart_image_generator import SmartImageGenerator
from util.config import config
from util.error_codes import IMAGE_GENERATION_FAILED, INSUFFICIENT_CREDITS, MISSING_CONTENT
from util.errors import ExternalServiceError, ValidationError


class SmartImageGeneratorTest(TestCase):

    di: DI
    copywriter: FakeChatModel
    provider: FakeXAIClient
    bot: FakeTelegramBotAPI
    http: FakeHTTPClient
    workers: BackgroundThreads
    copywriter_tool: ConfiguredTool
    image_tool: ConfiguredTool
    generator: SmartImageGenerator

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user(
            tool_choice_images_gen = IMAGE_GEN_GROK_IMAGINE_QUALITY.id,
        )))
        self.di.inject_invoker_chat(self.di.chat_config_repo.save(stubs.domain.chat_config(external_id = "12345")))
        self.copywriter_tool = stubs.domain.configured_tool(definition = GPT_5_NANO, purpose = ToolType.copywriting)
        self.image_tool = stubs.domain.configured_tool(
            definition = IMAGE_GEN_GROK_IMAGINE_QUALITY,
            purpose = ToolType.images_gen,
        )
        self.copywriter = cast(FakeChatModel, self.di.base_chat_langchain_model(self.copywriter_tool))
        self.provider = cast(FakeXAIClient, self.di.base_x_ai_client(self.image_tool))
        self.bot = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.copywriter.responses.append(stubs.external.ai_message(content = "Enhanced image prompt"))
        self.provider.image.responses.append(stubs.external.x_ai_image_response(content = stubs.external.image_bytes()))
        self.http.responses[compile(escape(config.public_api_base_url) + r"/attachments/public/[^/]+")].append(
            stubs.external.http_response(content = stubs.external.image_bytes()),
        )
        self.workers = BackgroundThreads()
        # plain threads need the test context; their real worker bodies still execute
        self.enterContext(patch.object(smart_image_generator, "Thread", new = self.workers.create))
        self.addCleanup(self.workers.finish)
        self.generator = self.di.smart_image_generator(
            raw_prompt = "Make them shake hands",
            attachment_ids = [],
            urls = [],
            configured_copywriter_tool = self.copywriter_tool,
            configured_image_gen_tool = self.image_tool,
        )

    def test_constructor_rejects_empty_prompt_before_resolving_attachments(self):
        with self.assertRaises(ValidationError) as context:
            self.di.smart_image_generator(
                raw_prompt = " ",
                attachment_ids = ["missing-attachment"],
                urls = [],
                configured_copywriter_tool = self.copywriter_tool,
                configured_image_gen_tool = self.image_tool,
            )

        self.assertEqual(context.exception.error_code, MISSING_CONTENT)
        self.assertEqual(self.http.requests, [])

    def test_execute_upscales_synchronously_before_starting_worker(self):
        result = self.generator.execute()

        self.assertEqual(result["status"], "started")
        self.assertEqual(result["used_reference_images"], 0)
        self.assertEqual(result["ignored_reference_images"], 0)
        self.assertEqual(len(self.copywriter.prompts), 1)
        self.assertEqual(self.copywriter.prompts[0][-1].content, "Make them shake hands")
        self.assertEqual(self.provider.image.requests, [])
        self.assertEqual(self.bot.get_sent_messages("12345"), [])
        self.workers.finish()
        self.assertEqual(self.provider.image.requests[0]["prompt"], "Enhanced image prompt")

    def test_llm_tool_parses_references_and_returns_immediate_acknowledgement(self):
        for attachment_id in ("first", "second"):
            self.di.chat_attachment_service.save(
                stubs.domain.chat_attachment(id = attachment_id, external_id = None),
                content = stubs.external.image_bytes(),
            )
        for url in ("https://example.com/first.png", "https://example.com/second.png"):
            self.http.responses[url].append(stubs.external.http_response(content = stubs.external.image_bytes()))
        result = json.loads(generate_image(
            di = self.di,
            prompt = "Make them shake hands",
            attachment_ids = "first, second",
            urls = "https://example.com/first.png, https://example.com/second.png",
            aspect_ratio = "16:9",
            size = "2K",
        ))

        self.assertIs(ALL_LLM_TOOLS["generate_image"], generate_image)
        self.assertEqual(result["result"], "Success")
        self.assertEqual(result["status"], "started")
        self.assertEqual(result["used_reference_images"], 1)
        self.assertEqual(result["ignored_reference_images"], 3)
        self.assertEqual(self.provider.image.requests, [])
        self.workers.finish()
        self.assertEqual(self.provider.image.requests[0]["resolution"], "2k")

    def test_execute_retains_first_supported_reference(self):
        for attachment_id in ("first", "ignored"):
            self.di.chat_attachment_service.save(
                stubs.domain.chat_attachment(id = attachment_id, external_id = None),
                content = stubs.external.image_bytes(),
            )
        generator = self.di.smart_image_generator(
            raw_prompt = "Make them shake hands",
            attachment_ids = ["first", "ignored"],
            urls = [],
            configured_copywriter_tool = self.copywriter_tool,
            configured_image_gen_tool = self.image_tool,
        )

        result = generator.execute()
        self.workers.finish()

        self.assertEqual(result["used_reference_images"], 1)
        self.assertEqual(result["ignored_reference_images"], 1)
        references = self.di.chat_attachment_service.resolve_image_attachments(
            [], [self.provider.image.requests[0]["image_url"]],
        )
        self.assertEqual([attachment.id for attachment in references], ["first"])

    def test_execute_stops_before_upscaling_when_preflight_fails(self):
        self.di.user_repo.save(replace(self.di.invoker, credit_balance = -1))
        generator = self.di.smart_image_generator(
            raw_prompt = "Make them shake hands",
            attachment_ids = [],
            urls = [],
            configured_copywriter_tool = self.copywriter_tool,
            configured_image_gen_tool = replace(self.image_tool, uses_credits = True, payer_id = self.di.invoker.id),
        )

        with self.assertRaises(ValidationError) as context:
            generator.execute()

        self.assertEqual(context.exception.error_code, INSUFFICIENT_CREDITS)
        self.assertEqual(self.copywriter.prompts, [])
        self.assertEqual(self.workers.threads, [])

    def test_execute_rejects_busy_service_after_upscaling(self):
        while smart_image_generator.IMAGE_GENERATION_SLOTS.acquire(blocking = False):
            self.addCleanup(smart_image_generator.IMAGE_GENERATION_SLOTS.release)

        with self.assertRaises(ExternalServiceError) as context:
            self.generator.execute()

        self.assertEqual(context.exception.error_code, IMAGE_GENERATION_FAILED)
        self.assertEqual(len(self.copywriter.prompts), 1)
        self.assertEqual(self.workers.threads, [])

    def test_execute_does_not_acquire_slot_when_upscaling_fails(self):
        self.copywriter.responses.clear()
        self.copywriter.responses.append(ExternalServiceError("Copywriter unavailable", IMAGE_GENERATION_FAILED))
        with self.assertRaises(ExternalServiceError):
            self.generator.execute()

        self.assertEqual(self.workers.threads, [])
        self.assertEqual(self.provider.image.requests, [])
        acquired = 0
        try:
            while smart_image_generator.IMAGE_GENERATION_SLOTS.acquire(blocking = False):
                acquired += 1
            self.assertEqual(acquired, 16)
        finally:
            for _ in range(acquired):
                smart_image_generator.IMAGE_GENERATION_SLOTS.release()

    def test_execute_releases_slot_when_thread_start_fails(self):
        # OS thread startup failure cannot be reproduced reliably with normal threads
        with patch.object(Thread, "start", side_effect = RuntimeError("Thread unavailable")):
            with self.assertRaises(ExternalServiceError) as context:
                self.generator.execute()

        self.assertEqual(context.exception.error_code, IMAGE_GENERATION_FAILED)
        acquired = 0
        try:
            while smart_image_generator.IMAGE_GENERATION_SLOTS.acquire(blocking = False):
                acquired += 1
            self.assertEqual(acquired, 16)
        finally:
            for _ in range(acquired):
                smart_image_generator.IMAGE_GENERATION_SLOTS.release()

    def test_background_worker_sets_upload_action_delivers_and_releases_slot(self):
        self.generator.execute()
        self.workers.finish()

        self.assertEqual(self.bot.statuses["12345"], "upload_photo")
        messages = self.bot.get_sent_messages("12345")
        self.assertEqual(len(messages), 1)
        self.assertIn("photo_url", messages[0])
        attachments = self.di.chat_attachment_service.resolve_image_attachments([], [messages[0]["photo_url"]])
        self.assertEqual(len(attachments), 1)
        acquired = 0
        try:
            while smart_image_generator.IMAGE_GENERATION_SLOTS.acquire(blocking = False):
                acquired += 1
            self.assertEqual(acquired, 16)
        finally:
            for _ in range(acquired):
                smart_image_generator.IMAGE_GENERATION_SLOTS.release()

    def test_background_worker_notifies_chat_with_formatted_failure(self):
        cases = [
            (ExternalServiceError("Provider unavailable", IMAGE_GENERATION_FAILED), "Provider unavailable"),
            (RuntimeError("Unexpected provider failure"), "Unexpected provider failure"),
            (stubs.external.x_ai_image_response(), "filtered by moderation"),
        ]
        self.provider.image.responses.clear()
        self.copywriter.responses.clear()
        for index, (response, expected_detail) in enumerate(cases):
            with self.subTest(failure = expected_detail):
                self.provider.image.responses.append(response)
                self.copywriter.responses.extend([
                    stubs.external.ai_message(content = "Enhanced image prompt"),
                    stubs.external.ai_message(content = "Localized image failure notification"),
                ])

                self.generator.execute()
                self.workers.finish()

                messages = self.bot.get_sent_messages("12345")
                self.assertEqual(len(messages), index + 1)
                self.assertEqual(messages[-1]["text"], "Localized image failure notification")
                self.assertIn(expected_detail, str(self.copywriter.prompts[-1]))

    def test_background_worker_logs_error_and_skips_unfunded_failure_notification(self):
        user = self.di.user_repo.save(replace(
            self.di.invoker,
            whatsapp_user_id = "15551234567",
        ))
        chat = self.di.chat_config_repo.save(replace(
            self.di.require_invoker_chat(),
            chat_type = ChatConfigDB.ChatType.whatsapp,
            external_id = user.whatsapp_user_id,
        ))
        self.di.inject_invoker(user)
        self.di.inject_invoker_chat(chat)
        self.di.chat_membership_repo.save(stubs.domain.chat_membership(user_id = user.id, chat_id = chat.chat_id))
        self.provider.image.responses.clear()
        self.provider.image.responses.append(ExternalServiceError("Provider unavailable", IMAGE_GENERATION_FAILED))
        bot = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)

        self.generator.execute()
        self.di.user_repo.save(replace(user, credit_balance = 0.0))
        with patch.object(smart_image_generator.log, "e") as error_log:
            self.workers.finish()

        self.assertEqual(len(self.copywriter.prompts), 1)
        self.assertEqual(bot.get_sent_messages(str(chat.external_id)), [])
        error_messages = [call.args[0] for call in error_log.call_args_list]
        self.assertIn(f"Background image generation failed for chat '{chat.chat_id.hex}'", error_messages)
        self.assertIn(f"Could not notify chat '{chat.chat_id.hex}' of image generation failure", error_messages)
