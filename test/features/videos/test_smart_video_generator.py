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
from features.chat.llm_tools.llm_tool_library import ALL_LLM_TOOLS, generate_video
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import GPT_5_NANO, VIDEO_GEN_P_VIDEO
from features.external_tools.intelligence_presets import default_tool_for
from features.users.user import User
from features.videos import smart_video_generator
from features.videos.smart_video_generator import SmartVideoGenerator
from features.videos.video_api_utils import map_to_model_parameters
from util.error_codes import MISSING_CONTENT, VIDEO_GENERATION_FAILED
from util.errors import ExternalServiceError, ValidationError


class SmartVideoGeneratorTest(unittest.TestCase):

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
        self.video_tool = ConfiguredTool(
            definition = VIDEO_GEN_P_VIDEO,
            token = SecretStr("replicate-token"),
            purpose = ToolType.videos_gen,
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
        self.copywriter.invoke.return_value = AIMessage(content = "Enhanced video prompt")
        self.di = Mock(spec = DI)
        self.di.chat_langchain_model.return_value = self.copywriter
        self.di.require_invoker_chat.return_value = self.chat
        self.di.require_invoker_chat_type.return_value = self.chat.chat_type
        self.di.invoker = User(id = self.invoker_id)

    def _generator(
        self,
        attachment_ids: list[str] | None = None,
        urls: list[str] | None = None,
    ) -> SmartVideoGenerator:
        return SmartVideoGenerator(
            raw_prompt = "Make them shake hands",
            attachment_ids = attachment_ids or [],
            urls = urls or [],
            configured_copywriter_tool = self.copywriter_tool,
            configured_video_gen_tool = self.video_tool,
            di = self.di,
        )

    def test_constructor_rejects_empty_prompt_before_resolving_attachments(self):
        with self.assertRaises(ValidationError) as context:
            SmartVideoGenerator(
                raw_prompt = " ",
                attachment_ids = ["attachment"],
                urls = [],
                configured_copywriter_tool = self.copywriter_tool,
                configured_video_gen_tool = self.video_tool,
                di = self.di,
            )

        self.assertEqual(context.exception.error_code, MISSING_CONTENT)
        self.di.chat_attachment_service.resolve_image_attachments.assert_not_called()

    def test_execute_screenwrites_synchronously_before_starting_worker(self):
        events = []
        worker = Mock()
        worker.start.side_effect = lambda: events.append("worker")
        self.copywriter.invoke.side_effect = lambda messages: (
            events.append("screenwriter"),
            AIMessage(content = "Enhanced video prompt"),
        )[1]

        with patch.object(
            smart_video_generator,
            "VIDEO_GENERATION_SLOTS",
        ) as slots, patch.object(
            smart_video_generator,
            "Thread",
            return_value = worker,
        ) as thread, patch.object(
            smart_video_generator.prompt_resolvers,
            "copywriting_video_screenwriter",
            return_value = "Screenwriter system prompt",
        ):
            slots.acquire.return_value = True

            result = self._generator().execute()

        self.assertEqual(events, ["screenwriter", "worker"])
        self.assertEqual(
            result,
            {
                "status": "started",
                "description": "Video generation has started. You will receive a notification when the video is ready.",
                "used_reference_images": 0,
                "ignored_reference_images": 0,
            },
        )
        messages = self.copywriter.invoke.call_args.args[0]
        self.assertEqual(messages, [
            SystemMessage("Screenwriter system prompt"),
            HumanMessage("Make them shake hands"),
        ])
        worker_kwargs = thread.call_args.kwargs["kwargs"]
        self.assertEqual(worker_kwargs["parameters"].prompt, "Enhanced video prompt")
        self.assertNotIn("di", worker_kwargs)
        self.assertIs(thread.call_args.kwargs["target"], smart_video_generator._run_video_worker)
        self.assertTrue(thread.call_args.kwargs["daemon"])
        slots.acquire.assert_called_once_with(blocking = False)
        slots.release.assert_not_called()

    def test_llm_tool_parses_references_and_returns_immediate_acknowledgement(self):
        generator = Mock()
        generator.execute.return_value = {
            "status": "started",
            "description": "Video generation has started.",
            "used_reference_images": 2,
            "ignored_reference_images": 1,
        }
        self.di.tool_choice_resolver.require_tool.side_effect = [self.copywriter_tool, self.video_tool]
        self.di.smart_video_generator.return_value = generator

        result = json.loads(generate_video(
            di = self.di,
            prompt = "Make them shake hands",
            attachment_ids = "first, second",
            urls = "https://example.com/first.png, https://example.com/second.png",
            duration = "long",
            aspect_ratio = "16:9",
            size = "2K",
        ))

        self.assertIs(ALL_LLM_TOOLS["generate_video"], generate_video)
        self.di.tool_choice_resolver.require_tool.assert_has_calls([
            call(
                SmartVideoGenerator.COPYWRITER_TOOL_TYPE,
                default_tool_for(SmartVideoGenerator.COPYWRITER_TOOL_TYPE),
            ),
            call(
                SmartVideoGenerator.VIDEO_GEN_TOOL_TYPE,
                default_tool_for(SmartVideoGenerator.VIDEO_GEN_TOOL_TYPE),
            ),
        ])
        self.di.smart_video_generator.assert_called_once_with(
            raw_prompt = "Make them shake hands",
            attachment_ids = ["first", "second"],
            urls = ["https://example.com/first.png", "https://example.com/second.png"],
            configured_copywriter_tool = self.copywriter_tool,
            configured_video_gen_tool = self.video_tool,
            duration = "long",
            aspect_ratio = "16:9",
            output_size = "2K",
        )
        generator.execute.assert_called_once_with()
        self.assertEqual(result, {
            "result": "Success",
            "status": "started",
            "description": "Video generation has started.",
            "used_reference_images": 2,
            "ignored_reference_images": 1,
            "next_step": "Tell the partner that video generation started and it will be sent once ready",
        })

    def test_execute_truncates_references_before_screenwriting_and_worker_handoff(self):
        attachments = [
            ChatAttachment(
                id = "first",
                chat_id = self.chat_id,
                uploader_user_id = self.invoker_id,
                mime_type = "image/png",
                extension = "png",
            ),
            ChatAttachment(
                id = "ignored",
                chat_id = self.chat_id,
                uploader_user_id = self.invoker_id,
                mime_type = "image/png",
                extension = "png",
            ),
        ]
        self.di.chat_attachment_service.resolve_image_attachments.return_value = attachments
        self.di.chat_attachment_service.create_public_url.return_value = PublicAttachment(
            id = "first",
            url = "https://example.com/first.png",
            valid_until = 1,
        )
        worker = Mock()

        with patch.object(
            smart_video_generator,
            "VIDEO_GENERATION_SLOTS",
        ) as slots, patch.object(
            smart_video_generator,
            "Thread",
            return_value = worker,
        ) as thread, patch.object(
            smart_video_generator.prompt_resolvers,
            "copywriting_video_screenwriter",
            return_value = "Screenwriter system prompt",
        ) as screenwriter:
            slots.acquire.return_value = True

            result = self._generator(
                attachment_ids = ["first", "ignored"],
                urls = ["https://example.com/reference.png"],
            ).execute()

        self.assertEqual(
            result,
            {
                "status": "started",
                "description": "Video generation has started. You will receive a notification when the video is ready.",
                "used_reference_images": 1,
                "ignored_reference_images": 1,
            },
        )
        self.di.chat_attachment_service.resolve_image_attachments.assert_called_once_with(
            ["first", "ignored"],
            ["https://example.com/reference.png"],
        )
        self.di.chat_attachment_service.create_public_url.assert_called_once_with(attachments[0])
        screenwriter.assert_called_once_with(self.chat.chat_type, 1)
        parameters = thread.call_args.kwargs["kwargs"]["parameters"]
        self.assertEqual(parameters.image, "https://example.com/first.png")
        self.assertIsNone(parameters.reference_images)

    def test_execute_rejects_busy_service_after_screenwriting(self):
        with patch.object(
            smart_video_generator,
            "VIDEO_GENERATION_SLOTS",
        ) as slots, patch.object(
            smart_video_generator,
            "Thread",
        ) as thread, patch.object(
            smart_video_generator.prompt_resolvers,
            "copywriting_video_screenwriter",
            return_value = "Screenwriter system prompt",
        ):
            slots.acquire.return_value = False

            with self.assertRaises(ExternalServiceError) as context:
                self._generator().execute()

        self.assertEqual(context.exception.error_code, VIDEO_GENERATION_FAILED)
        self.copywriter.invoke.assert_called_once()
        thread.assert_not_called()
        slots.release.assert_not_called()

    def test_execute_does_not_acquire_slot_when_screenwriting_fails(self):
        self.copywriter.invoke.side_effect = RuntimeError("Copywriter unavailable")

        with patch.object(
            smart_video_generator,
            "VIDEO_GENERATION_SLOTS",
        ) as slots, patch.object(
            smart_video_generator,
            "Thread",
        ) as thread, patch.object(
            smart_video_generator.prompt_resolvers,
            "copywriting_video_screenwriter",
            return_value = "Screenwriter system prompt",
        ):
            slots.acquire.return_value = True

            with self.assertRaises(RuntimeError):
                self._generator().execute()

        slots.acquire.assert_not_called()
        slots.release.assert_not_called()
        thread.assert_not_called()

    def test_execute_releases_slot_when_worker_cannot_start(self):
        worker = Mock()
        worker.start.side_effect = RuntimeError("Thread unavailable")

        with patch.object(
            smart_video_generator,
            "VIDEO_GENERATION_SLOTS",
        ) as slots, patch.object(
            smart_video_generator,
            "Thread",
            return_value = worker,
        ), patch.object(
            smart_video_generator.prompt_resolvers,
            "copywriting_video_screenwriter",
            return_value = "Screenwriter system prompt",
        ):
            slots.acquire.return_value = True

            with self.assertRaises(ExternalServiceError) as context:
                self._generator().execute()

        self.assertEqual(context.exception.error_code, VIDEO_GENERATION_FAILED)
        slots.release.assert_called_once_with()

    def test_background_worker_reuses_generation_scope_for_delivery(self):
        parameters = map_to_model_parameters(VIDEO_GEN_P_VIDEO, prompt = "Enhanced video prompt")
        events = []
        worker_context = MagicMock()
        worker_db = Mock()
        worker_context.__enter__.return_value = worker_db
        worker_di = Mock(spec = DI)
        worker_di.simple_video_generator.return_value.execute.side_effect = lambda: (
            events.append("generation completed"),
            "https://example.com/video.mp4",
        )[1]
        worker_di.rollback_db_session.side_effect = lambda: events.append("accounting transaction released")
        worker_di.platform_bot_sdk.return_value.smart_send_video.side_effect = lambda **_: events.append(
            "video delivery started",
        )

        with patch.object(
            smart_video_generator,
            "get_detached_session",
            return_value = worker_context,
        ) as get_session, patch.object(
            smart_video_generator,
            "DI",
            return_value = worker_di,
        ) as di_factory, patch.object(
            smart_video_generator,
            "VIDEO_GENERATION_SLOTS",
        ) as slots:
            smart_video_generator._run_video_worker(
                configured_video_gen_tool = self.video_tool,
                parameters = parameters,
                invoker_id = self.invoker_id,
                invoker_chat_id = self.chat_id,
                external_chat_id = "12345",
                media_mode = ChatConfigDB.MediaMode.photo,
            )

        get_session.assert_called_once_with()
        self.assertEqual(
            events,
            ["generation completed", "accounting transaction released", "video delivery started"],
        )
        di_factory.assert_called_once_with(worker_db, self.invoker_id.hex, self.chat_id.hex)
        worker_di.simple_video_generator.assert_called_once_with(self.video_tool, parameters)
        worker_di.rollback_db_session.assert_called_once_with()
        worker_di.platform_bot_sdk.return_value.smart_send_video.assert_called_once_with(
            media_mode = ChatConfigDB.MediaMode.photo,
            chat_id = "12345",
            video_url = "https://example.com/video.mp4",
        )
        worker_context.__exit__.assert_called_once()
        slots.release.assert_called_once_with()

    def test_background_worker_notifies_chat_with_formatted_failure(self):
        parameters = map_to_model_parameters(VIDEO_GEN_P_VIDEO, prompt = "Enhanced video prompt")
        known_error = ExternalServiceError("Replicate unavailable", VIDEO_GENERATION_FAILED)
        cases = [
            (known_error, known_error),
            (
                RuntimeError("Replicate unavailable"),
                ExternalServiceError(
                    "Unexpected video generation or delivery failure: Replicate unavailable",
                    VIDEO_GENERATION_FAILED,
                ),
            ),
        ]

        for raised_error, expected_error in cases:
            with self.subTest(error_type = type(raised_error).__name__):
                generation_context = MagicMock()
                notification_context = MagicMock()
                generation_context.__enter__.return_value = Mock()
                notification_context.__enter__.return_value = Mock()
                generation_di = Mock(spec = DI)
                notification_di = Mock(spec = DI)
                generation_di.simple_video_generator.return_value.execute.side_effect = raised_error
                notification_di.require_invoker_chat.return_value = self.chat
                notification_di.tool_choice_resolver.require_tool.return_value = self.copywriter_tool
                notification_di.sys_announcements_service.return_value.execute.return_value = (
                    self.chat,
                    AIMessage(content = "Localized video failure notification"),
                )

                with patch.object(
                    smart_video_generator,
                    "get_detached_session",
                    side_effect = [generation_context, notification_context],
                ), patch.object(
                    smart_video_generator,
                    "DI",
                    side_effect = [generation_di, notification_di],
                ), patch.object(
                    smart_video_generator,
                    "VIDEO_GENERATION_SLOTS",
                ) as slots:
                    smart_video_generator._run_video_worker(
                        configured_video_gen_tool = self.video_tool,
                        parameters = parameters,
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
                    raw_information = f"Your video could not be generated or delivered.\n\n{str(expected_error)}",
                    target_chat = self.chat,
                    configured_tool = self.copywriter_tool,
                )
                notification_di.platform_bot_sdk.return_value.send_text_message.assert_called_once_with(
                    chat_id = "12345",
                    text = "Localized video failure notification",
                )
                notification_di.platform_bot_sdk.return_value.smart_send_video.assert_not_called()
                slots.release.assert_called_once_with()
