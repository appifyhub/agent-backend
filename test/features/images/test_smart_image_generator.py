import json
import unittest
from unittest.mock import MagicMock, Mock, call, patch
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.announcements.sys_announcements_service import SysAnnouncementsService
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.attachment.storage.attachment_storage import PublicAttachment
from features.chat.config.chat_config import ChatConfig
from features.chat.llm_tools.llm_tool_library import ALL_LLM_TOOLS, generate_image
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import GPT_5_NANO, IMAGE_GEN_GROK_IMAGINE_QUALITY
from features.external_tools.intelligence_presets import default_tool_for
from features.images import smart_image_generator
from features.images.image_api_utils import map_to_model_parameters
from features.images.smart_image_generator import SmartImageGenerator
from features.users.user import User
from util.error_codes import IMAGE_GENERATION_FAILED, MISSING_CONTENT
from util.errors import ExternalServiceError, ValidationError


class SmartImageGeneratorTest(unittest.TestCase):

    def setUp(self):
        self.invoker_id = UUID(int = 1)
        self.chat_id = UUID(int = 2)
        self.copywriter_tool = ConfiguredTool(
            definition = GPT_5_NANO,
            token = SecretStr("copywriter-token"),
            purpose = ToolType.copywriting,
            payer_id = self.invoker_id,
            uses_credits = True,
        )
        self.image_tool = ConfiguredTool(
            definition = IMAGE_GEN_GROK_IMAGINE_QUALITY,
            token = SecretStr("xai-token"),
            purpose = ToolType.images_gen,
            payer_id = self.invoker_id,
            uses_credits = True,
        )
        self.chat = ChatConfig(
            chat_id = self.chat_id,
            external_id = "12345",
            chat_type = ChatConfigDB.ChatType.telegram,
            media_mode = ChatConfigDB.MediaMode.photo,
        )
        self.copywriter = Mock()
        self.copywriter.invoke.return_value = AIMessage(content = "Enhanced image prompt")
        self.di = Mock(spec = DI)
        self.di.chat_langchain_model.return_value = self.copywriter
        self.di.require_invoker_chat.return_value = self.chat
        self.di.require_invoker_chat_type.return_value = self.chat.chat_type
        self.di.invoker = User(id = self.invoker_id)

    def _generator(
        self,
        attachment_ids: list[str] | None = None,
        urls: list[str] | None = None,
    ) -> SmartImageGenerator:
        return SmartImageGenerator(
            raw_prompt = "Make them shake hands",
            attachment_ids = attachment_ids or [],
            urls = urls or [],
            configured_copywriter_tool = self.copywriter_tool,
            configured_image_gen_tool = self.image_tool,
            di = self.di,
        )

    def _attachment(self, attachment_id: str, last_url: str = "s3://bucket/image.png") -> ChatAttachment:
        return ChatAttachment(
            id = attachment_id,
            chat_id = self.chat_id,
            uploader_user_id = self.invoker_id,
            last_url = last_url,
            mime_type = "image/png",
            extension = "png",
        )

    def test_constructor_rejects_empty_prompt_before_resolving_attachments(self):
        with self.assertRaises(ValidationError) as context:
            SmartImageGenerator(
                raw_prompt = " ",
                attachment_ids = ["attachment"],
                urls = [],
                configured_copywriter_tool = self.copywriter_tool,
                configured_image_gen_tool = self.image_tool,
                di = self.di,
            )

        self.assertEqual(context.exception.error_code, MISSING_CONTENT)
        self.di.chat_attachment_service.resolve_image_attachments.assert_not_called()

    def test_execute_upscales_synchronously_before_starting_worker(self):
        events = []
        worker = Mock()
        worker.start.side_effect = lambda: events.append("worker")
        self.di.spending_service.validate_pre_flight.side_effect = lambda *_, **__: events.append("preflight")
        self.copywriter.invoke.side_effect = lambda messages: (
            events.append("copywriter"),
            AIMessage(content = "Enhanced image prompt"),
        )[1]

        with patch.object(
            smart_image_generator,
            "IMAGE_GENERATION_SLOTS",
        ) as slots, patch.object(
            smart_image_generator,
            "Thread",
            return_value = worker,
        ) as thread, patch.object(
            smart_image_generator.prompt_resolvers,
            "copywriting_image_prompt_upscaler",
            return_value = "Copywriter system prompt",
        ) as prompt_upscaler:
            slots.acquire.return_value = True

            result = self._generator().execute()

        self.assertEqual(events, ["preflight", "copywriter", "worker"])
        self.assertEqual(result, {
            "status": "started",
            "description": "Image generation has started. You will receive a notification when the image is ready.",
            "used_reference_images": 0,
            "ignored_reference_images": 0,
        })
        prompt_upscaler.assert_called_once_with(self.chat.chat_type, 0)
        self.assertEqual(self.copywriter.invoke.call_args.args[0], [
            SystemMessage("Copywriter system prompt"),
            HumanMessage("Make them shake hands"),
        ])
        worker_kwargs = thread.call_args.kwargs["kwargs"]
        self.assertEqual(worker_kwargs["parameters"].prompt, "Enhanced image prompt")
        self.assertEqual(worker_kwargs["input_image_urls"], [])
        self.assertNotIn("di", worker_kwargs)
        self.assertIs(thread.call_args.kwargs["target"], smart_image_generator._run_image_worker)
        self.assertTrue(thread.call_args.kwargs["daemon"])
        slots.acquire.assert_called_once_with(blocking = False)
        slots.release.assert_not_called()
        self.di.spending_service.validate_pre_flight.assert_called_once_with(
            self.image_tool,
            input_image_sizes = None,
            output_image_sizes = ["2K"],
        )

    def test_llm_tool_parses_references_and_returns_immediate_acknowledgement(self):
        generator = Mock()
        generator.execute.return_value = {
            "status": "started",
            "description": "Image generation has started.",
            "used_reference_images": 2,
            "ignored_reference_images": 1,
        }
        self.di.tool_choice_resolver.require_tool.side_effect = [self.copywriter_tool, self.image_tool]
        self.di.smart_image_generator.return_value = generator

        result = json.loads(generate_image(
            di = self.di,
            prompt = "Make them shake hands",
            attachment_ids = "first, second",
            urls = "https://example.com/first.png, https://example.com/second.png",
            aspect_ratio = "16:9",
            size = "2K",
        ))

        self.assertIs(ALL_LLM_TOOLS["generate_image"], generate_image)
        self.di.tool_choice_resolver.require_tool.assert_has_calls([
            call(
                SmartImageGenerator.COPYWRITER_TOOL_TYPE,
                default_tool_for(SmartImageGenerator.COPYWRITER_TOOL_TYPE),
            ),
            call(
                SmartImageGenerator.IMAGE_GEN_TOOL_TYPE,
                default_tool_for(SmartImageGenerator.IMAGE_GEN_TOOL_TYPE),
            ),
        ])
        self.di.smart_image_generator.assert_called_once_with(
            raw_prompt = "Make them shake hands",
            attachment_ids = ["first", "second"],
            urls = ["https://example.com/first.png", "https://example.com/second.png"],
            configured_copywriter_tool = self.copywriter_tool,
            configured_image_gen_tool = self.image_tool,
            aspect_ratio = "16:9",
            output_size = "2K",
        )
        generator.execute.assert_called_once_with()
        self.assertEqual(result, {
            "result": "Success",
            "status": "started",
            "description": "Image generation has started.",
            "used_reference_images": 2,
            "ignored_reference_images": 1,
            "next_step": "Tell the partner that image generation started and it will be sent once ready",
        })

    def test_execute_retains_first_supported_reference_before_upscaling_and_worker_handoff(self):
        first = self._attachment("first")
        ignored = self._attachment("ignored")
        self.di.chat_attachment_service.resolve_image_attachments.return_value = [first, ignored]
        self.di.chat_attachment_service.create_public_url.return_value = PublicAttachment(
            id = "first",
            url = "https://example.com/first.png",
            valid_until = 1,
        )
        self.di.attachment_storage.open.return_value = MagicMock()
        worker = Mock()

        with patch.object(
            smart_image_generator,
            "IMAGE_GENERATION_SLOTS",
        ) as slots, patch.object(
            smart_image_generator,
            "Thread",
            return_value = worker,
        ) as thread, patch.object(
            smart_image_generator.prompt_resolvers,
            "copywriting_image_prompt_upscaler",
            return_value = "Copywriter system prompt",
        ) as prompt_upscaler, patch.object(
            smart_image_generator,
            "calculate_image_size_category",
            return_value = "4k",
        ):
            slots.acquire.return_value = True

            result = self._generator(
                attachment_ids = ["first", "ignored"],
                urls = ["https://example.com/reference.png"],
            ).execute()

        self.assertEqual(result, {
            "status": "started",
            "description": "Image generation has started. You will receive a notification when the image is ready.",
            "used_reference_images": 1,
            "ignored_reference_images": 1,
        })
        self.di.chat_attachment_service.resolve_image_attachments.assert_called_once_with(
            ["first", "ignored"],
            ["https://example.com/reference.png"],
        )
        self.di.chat_attachment_service.create_public_url.assert_called_once_with(first)
        self.di.attachment_storage.open.assert_called_once_with(first)
        self.di.spending_service.validate_pre_flight.assert_called_once_with(
            self.image_tool,
            input_image_sizes = ["4k"],
            output_image_sizes = ["2K"],
        )
        prompt_upscaler.assert_called_once_with(self.chat.chat_type, 1)
        worker_kwargs = thread.call_args.kwargs["kwargs"]
        self.assertEqual(worker_kwargs["parameters"].input_image, "https://example.com/first.png")
        self.assertEqual(worker_kwargs["parameters"].prompt, "Enhanced image prompt")
        self.assertEqual(worker_kwargs["input_attachments"], [first])
        self.assertEqual(worker_kwargs["input_image_urls"], ["https://example.com/first.png"])
        self.assertEqual(worker_kwargs["input_image_sizes"], ["4k"])
        self.assertEqual(worker_kwargs["output_image_sizes"], ["2K"])

    def test_execute_stops_before_upscaling_and_admission_when_preflight_fails(self):
        preflight_error = ValidationError("Image generation is not affordable", MISSING_CONTENT)
        self.di.spending_service.validate_pre_flight.side_effect = preflight_error

        with patch.object(
            smart_image_generator,
            "IMAGE_GENERATION_SLOTS",
        ) as slots, patch.object(
            smart_image_generator,
            "Thread",
        ) as thread, patch.object(
            smart_image_generator.prompt_resolvers,
            "copywriting_image_prompt_upscaler",
        ) as prompt_upscaler:
            with self.assertRaises(ValidationError) as context:
                self._generator().execute()

        self.assertIs(context.exception, preflight_error)
        prompt_upscaler.assert_not_called()
        self.copywriter.invoke.assert_not_called()
        slots.acquire.assert_not_called()
        thread.assert_not_called()

    def test_execute_rejects_busy_service_after_upscaling(self):
        with patch.object(
            smart_image_generator,
            "IMAGE_GENERATION_SLOTS",
        ) as slots, patch.object(
            smart_image_generator,
            "Thread",
        ) as thread, patch.object(
            smart_image_generator.prompt_resolvers,
            "copywriting_image_prompt_upscaler",
            return_value = "Copywriter system prompt",
        ):
            slots.acquire.return_value = False

            with self.assertRaises(ExternalServiceError) as context:
                self._generator().execute()

        self.assertEqual(context.exception.error_code, IMAGE_GENERATION_FAILED)
        self.copywriter.invoke.assert_called_once()
        thread.assert_not_called()
        slots.release.assert_not_called()

    def test_execute_does_not_acquire_slot_when_upscaling_fails(self):
        self.copywriter.invoke.side_effect = RuntimeError("Copywriter unavailable")

        with patch.object(
            smart_image_generator,
            "IMAGE_GENERATION_SLOTS",
        ) as slots, patch.object(
            smart_image_generator,
            "Thread",
        ) as thread, patch.object(
            smart_image_generator.prompt_resolvers,
            "copywriting_image_prompt_upscaler",
            return_value = "Copywriter system prompt",
        ):
            with self.assertRaises(RuntimeError):
                self._generator().execute()

        slots.acquire.assert_not_called()
        slots.release.assert_not_called()
        thread.assert_not_called()

    def test_execute_releases_slot_when_worker_cannot_start(self):
        worker = Mock()
        worker.start.side_effect = RuntimeError("Thread unavailable")

        with patch.object(
            smart_image_generator,
            "IMAGE_GENERATION_SLOTS",
        ) as slots, patch.object(
            smart_image_generator,
            "Thread",
            return_value = worker,
        ), patch.object(
            smart_image_generator.prompt_resolvers,
            "copywriting_image_prompt_upscaler",
            return_value = "Copywriter system prompt",
        ):
            slots.acquire.return_value = True

            with self.assertRaises(ExternalServiceError) as context:
                self._generator().execute()

        self.assertEqual(context.exception.error_code, IMAGE_GENERATION_FAILED)
        slots.release.assert_called_once_with()

    def test_background_worker_releases_generation_scope_then_sets_upload_action_and_delivers(self):
        first = self._attachment("first")
        parameters = map_to_model_parameters(
            self.image_tool.definition,
            prompt = "Enhanced image prompt",
            input_urls = ["https://example.com/first.png"],
        )
        events = []
        worker_context = MagicMock()
        worker_db = Mock()
        worker_context.__enter__.return_value = worker_db
        worker_di = Mock(spec = DI)
        generator = Mock()
        generator.error = None
        generator.execute.side_effect = lambda: (
            events.append("generation completed"),
            "https://example.com/image.png",
        )[1]
        worker_di.simple_image_generator.return_value = generator
        worker_di.rollback_db_session.side_effect = lambda: events.append("accounting transaction released")
        platform_sdk = worker_di.platform_bot_sdk.return_value
        platform_sdk.set_chat_action.side_effect = lambda **_: events.append("upload action")
        platform_sdk.smart_send_photo.side_effect = lambda **_: events.append("image delivery started")

        with patch.object(
            smart_image_generator,
            "get_detached_session",
            return_value = worker_context,
        ) as get_session, patch.object(
            smart_image_generator,
            "DI",
            return_value = worker_di,
        ) as di_factory, patch.object(
            smart_image_generator,
            "IMAGE_GENERATION_SLOTS",
        ) as slots:
            smart_image_generator._run_image_worker(
                configured_image_gen_tool = self.image_tool,
                parameters = parameters,
                input_attachments = [first],
                input_image_urls = ["https://example.com/first.png"],
                input_image_sizes = ["2k"],
                output_image_sizes = ["2k"],
                invoker_id = self.invoker_id,
                invoker_chat_id = self.chat_id,
                external_chat_id = "12345",
                media_mode = ChatConfigDB.MediaMode.photo,
            )

        get_session.assert_called_once_with()
        self.assertEqual(events, [
            "generation completed",
            "accounting transaction released",
            "upload action",
            "image delivery started",
        ])
        di_factory.assert_called_once_with(worker_db, self.invoker_id.hex, self.chat_id.hex)
        worker_di.simple_image_generator.assert_called_once_with(
            configured_tool = self.image_tool,
            parameters = parameters,
            input_attachments = [first],
            input_image_urls = ["https://example.com/first.png"],
            input_image_sizes = ["2k"],
            output_image_sizes = ["2k"],
        )
        worker_di.rollback_db_session.assert_called_once_with()
        platform_sdk.set_chat_action.assert_called_once_with(chat_id = "12345", action = "upload_photo")
        platform_sdk.smart_send_photo.assert_called_once_with(
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_id = "12345",
            photo_url = "https://example.com/image.png",
            thumbnail = "https://example.com/image.png",
        )
        worker_context.__exit__.assert_called_once()
        slots.release.assert_called_once_with()

    def test_background_worker_notifies_chat_with_formatted_failure(self):
        parameters = map_to_model_parameters(self.image_tool.definition, prompt = "Enhanced image prompt")
        known_error = ExternalServiceError("Replicate unavailable", IMAGE_GENERATION_FAILED)
        cases = [
            (known_error, None, known_error),
            (
                RuntimeError("Replicate unavailable"),
                None,
                ExternalServiceError(
                    "Unexpected image generation or delivery failure: Replicate unavailable",
                    IMAGE_GENERATION_FAILED,
                ),
            ),
            (
                None,
                "Provider returned no image",
                ExternalServiceError(
                    "Image generator failure: Provider returned no image",
                    IMAGE_GENERATION_FAILED,
                ),
            ),
        ]

        for raised_error, generator_error, expected_error in cases:
            with self.subTest(error_type = type(raised_error).__name__, generator_error = generator_error):
                generation_context = MagicMock()
                notification_context = MagicMock()
                generation_context.__enter__.return_value = Mock()
                notification_context.__enter__.return_value = Mock()
                generation_di = Mock(spec = DI)
                notification_di = Mock(spec = DI)
                generator = generation_di.simple_image_generator.return_value
                generator.error = generator_error
                if raised_error is not None:
                    generator.execute.side_effect = raised_error
                else:
                    generator.execute.return_value = None
                notification_di.require_invoker_chat.return_value = self.chat
                notification_di.tool_choice_resolver.require_tool.return_value = self.copywriter_tool
                notification_di.sys_announcements_service.return_value.execute.return_value = (
                    self.chat,
                    AIMessage(content = "Localized image failure notification"),
                )

                with patch.object(
                    smart_image_generator,
                    "get_detached_session",
                    side_effect = [generation_context, notification_context],
                ), patch.object(
                    smart_image_generator,
                    "DI",
                    side_effect = [generation_di, notification_di],
                ), patch.object(
                    smart_image_generator,
                    "IMAGE_GENERATION_SLOTS",
                ) as slots:
                    smart_image_generator._run_image_worker(
                        configured_image_gen_tool = self.image_tool,
                        parameters = parameters,
                        input_attachments = [],
                        input_image_urls = [],
                        input_image_sizes = None,
                        output_image_sizes = ["2k"],
                        invoker_id = self.invoker_id,
                        invoker_chat_id = self.chat_id,
                        external_chat_id = "12345",
                        media_mode = ChatConfigDB.MediaMode.photo,
                    )

                notification_di.tool_choice_resolver.require_tool.assert_called_once_with(
                    purpose = SysAnnouncementsService.TOOL_TYPE,
                    default_tool = default_tool_for(SysAnnouncementsService.TOOL_TYPE),
                )
                notification_di.sys_announcements_service.assert_called_once_with(
                    raw_information = f"Your image could not be generated or delivered.\n\n{str(expected_error)}",
                    target_chat = self.chat,
                    configured_tool = self.copywriter_tool,
                )
                notification_di.platform_bot_sdk.return_value.send_text_message.assert_called_once_with(
                    chat_id = "12345",
                    text = "Localized image failure notification",
                )
                notification_di.platform_bot_sdk.return_value.smart_send_photo.assert_not_called()
                slots.release.assert_called_once_with()
