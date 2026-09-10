import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.ingested_chat_message import IngestedChatMessage
from features.chat.message.chat_message import ChatMessage
from features.chat.message_burst import ScheduledChatMessageBurst
from features.chat.message_burst_service import MessageBurstService
from features.chat.whatsapp.model.update import Update
from features.chat.whatsapp.whatsapp_update_responder import (
    _ingest_update,
    _IngressOutcome,
    respond_to_update,
)
from features.users.user import User


class WhatsAppUpdateResponderTest(unittest.TestCase):

    def setUp(self):
        self.chat = ChatConfig(
            chat_id = UUID(int = 10),
            external_id = "123",
            is_private = True,
            reply_chance_percent = 0,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        self.author = User(
            id = UUID(int = 20),
            full_name = "Test User",
            whatsapp_user_id = "20",
        )
        self.message = ChatMessage(
            chat_id = self.chat.chat_id,
            message_id = "message-1",
            ingestion_order = 7,
            author_id = self.author.id,
            sent_at = datetime(2026, 1, 2, 12, 0, 0),
            text = "hello",
        )
        self.ingested = self._ingested(self.message, raw_text = "hello")
        self.di = Mock(spec = DI)
        self.burst_service = Mock(spec = MessageBurstService)
        # noinspection PyPropertyAccess
        self.di.message_burst_service = self.burst_service

    def test_photo_and_prompt_deliveries_schedule_same_author_bursts(self):
        photo_message = self.message
        prompt_message = ChatMessage(
            chat_id = self.chat.chat_id,
            message_id = "message-2",
            ingestion_order = 8,
            author_id = self.author.id,
            sent_at = self.message.sent_at + timedelta(milliseconds = 100),
            text = "describe these",
        )
        photo = self._ingested(photo_message, raw_text = "")
        prompt = self._ingested(prompt_message, raw_text = "describe these")
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [photo, prompt]
        first_scheduled = self._scheduled_burst(message_count = 1)
        second_scheduled = self._scheduled_burst(message_count = 2)
        session = MagicMock()
        self.burst_service.record.side_effect = [first_scheduled, second_scheduled]
        with (
            patch(
                "features.chat.whatsapp.whatsapp_update_responder.get_detached_session",
                return_value = session,
            ),
            patch(
                "features.chat.whatsapp.whatsapp_update_responder.DI",
                return_value = self.di,
            ),
        ):
            outcome = _ingest_update(Update(object = "whatsapp_business_account", entry = []))

        self.assertEqual(outcome.scheduled_bursts, [first_scheduled, second_scheduled])
        self.assertEqual(self.burst_service.record.call_count, 2)
        self.assertEqual(
            [record.kwargs["message"].author_id for record in self.burst_service.record.call_args_list],
            [self.author.id, self.author.id],
        )

    def test_different_group_authors_schedule_independent_bursts(self):
        self.chat.is_private = False
        other_author = User(
            id = UUID(int = 21),
            full_name = "Other User",
            whatsapp_user_id = "21",
        )
        other_message = ChatMessage(
            chat_id = self.chat.chat_id,
            message_id = "message-2",
            ingestion_order = 8,
            author_id = other_author.id,
            sent_at = self.message.sent_at,
            text = "other",
        )
        other = IngestedChatMessage(
            chat = self.chat,
            author = other_author,
            message = other_message,
            attachments = [],
            raw_message_text = "other",
        )
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [self.ingested, other]
        session = MagicMock()
        self.burst_service.record.side_effect = [
            self._scheduled_burst(author_id = self.author.id),
            self._scheduled_burst(author_id = other_author.id),
        ]
        with (
            patch(
                "features.chat.whatsapp.whatsapp_update_responder.get_detached_session",
                return_value = session,
            ),
            patch(
                "features.chat.whatsapp.whatsapp_update_responder.DI",
                return_value = self.di,
            ),
        ):
            _ingest_update(Update(object = "whatsapp_business_account", entry = []))

        self.assertEqual(
            [item.kwargs["message"].author_id for item in self.burst_service.record.call_args_list],
            [self.author.id, other_author.id],
        )

    def test_command_does_not_extend_conversational_burst(self):
        command = self._ingested(self.message, raw_text = "/help")
        prompt_message = ChatMessage(
            chat_id = self.chat.chat_id,
            message_id = "message-2",
            ingestion_order = 8,
            author_id = self.author.id,
            sent_at = self.message.sent_at + timedelta(milliseconds = 100),
            text = "prompt",
        )
        prompt = self._ingested(prompt_message, raw_text = "prompt")
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [command, prompt]
        self.burst_service.process_message.return_value = False
        session = MagicMock()
        self.burst_service.record.return_value = self._scheduled_burst()
        with (
            patch(
                "features.chat.whatsapp.whatsapp_update_responder.get_detached_session",
                return_value = session,
            ),
            patch(
                "features.chat.whatsapp.whatsapp_update_responder.DI",
                return_value = self.di,
            ),
        ):
            outcome = _ingest_update(Update(object = "whatsapp_business_account", entry = []))

        self.burst_service.process_message.assert_called_once_with(
            command,
            command_only = True,
        )
        self.burst_service.record.assert_called_once()
        self.assertEqual(self.burst_service.record.call_args.kwargs["message"], prompt_message)
        self.assertEqual(len(outcome.scheduled_bursts), 1)

    def test_async_responder_processes_every_scheduled_burst(self):
        first = self._scheduled_burst(message_count = 1)
        second = self._scheduled_burst(message_count = 2, author_id = UUID(int = 21))
        second_di = Mock(spec = DI)
        second_burst_service = Mock(spec = MessageBurstService)
        # noinspection PyPropertyAccess
        second_di.message_burst_service = second_burst_service
        self.burst_service.process_after_quiet_period.return_value = False
        second_burst_service.process_after_quiet_period.return_value = True
        with (
            patch(
                "features.chat.whatsapp.whatsapp_update_responder.asyncio.to_thread",
                new = AsyncMock(return_value = _IngressOutcome(scheduled_bursts = [first, second])),
            ),
            patch(
                "features.chat.whatsapp.whatsapp_update_responder.DI",
                side_effect = [self.di, second_di],
            ) as di_factory,
        ):
            result = asyncio.run(
                respond_to_update(Update(object = "whatsapp_business_account", entry = [])),
            )

        self.assertTrue(result)
        self.assertEqual(
            di_factory.call_args_list,
            [
                call(
                    invoker_id = first.author_id.hex,
                    invoker_chat_id = first.chat_id.hex,
                ),
                call(
                    invoker_id = second.author_id.hex,
                    invoker_chat_id = second.chat_id.hex,
                ),
            ],
        )
        self.burst_service.process_after_quiet_period.assert_awaited_once()
        self.assertEqual(
            self.burst_service.process_after_quiet_period.await_args.kwargs["scheduled"],
            first,
        )
        second_burst_service.process_after_quiet_period.assert_awaited_once()
        self.assertEqual(
            second_burst_service.process_after_quiet_period.await_args.kwargs["scheduled"],
            second,
        )

    def _ingested(
        self,
        message: ChatMessage,
        raw_text: str,
    ) -> IngestedChatMessage:
        return IngestedChatMessage(
            chat = self.chat,
            author = self.author,
            message = message,
            attachments = [],
            raw_message_text = raw_text,
        )

    def _scheduled_burst(
        self,
        message_count: int = 1,
        author_id: UUID | None = None,
    ) -> ScheduledChatMessageBurst:
        return ScheduledChatMessageBurst(
            chat_id = self.chat.chat_id,
            author_id = author_id or self.author.id,
            message_count = message_count,
            wait_seconds = 0.5,
        )
