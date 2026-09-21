import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch
from uuid import UUID

import stubs

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.message_burst_service import MessageBurstService
from features.chat.whatsapp.whatsapp_update_responder import (
    _ingest_update,
    _IngressOutcome,
    respond_to_update,
)


class WhatsAppUpdateResponderTest(unittest.TestCase):

    def setUp(self):
        self.di = Mock(spec = DI)
        self.burst_service = Mock(spec = MessageBurstService)
        # noinspection PyPropertyAccess
        self.di.message_burst_service = self.burst_service

    def test_photo_and_prompt_deliveries_schedule_same_author_bursts(self):
        chat = stubs.domain.chat_config(
            chat_id = UUID(int = 10),
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        author = stubs.domain.user(
            id = UUID(int = 20),
        )
        photo_message = stubs.domain.chat_message(
            chat_id = chat.chat_id,
            message_id = "message-1",
            ingestion_order = 7,
            author_id = author.id,
            sent_at = datetime(2026, 1, 2, 12, 0, 0),
            text = "hello",
        )
        prompt_message = stubs.domain.chat_message(
            chat_id = chat.chat_id,
            message_id = "message-2",
            ingestion_order = 8,
            author_id = author.id,
            sent_at = photo_message.sent_at + timedelta(milliseconds = 100),
            text = "describe these",
        )
        photo = stubs.domain.ingested_chat_message(
            chat = chat,
            author = author,
            message = photo_message,
            attachments = [],
            raw_message_text = "",
        )
        prompt = stubs.domain.ingested_chat_message(
            chat = chat,
            author = author,
            message = prompt_message,
            attachments = [],
            raw_message_text = "describe these",
        )
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [photo, prompt]
        first_scheduled = stubs.domain.scheduled_chat_message_burst(
            chat_id = chat.chat_id,
            author_id = author.id,
            message_count = 1,
            wait_seconds = 0.5,
        )
        second_scheduled = stubs.domain.scheduled_chat_message_burst(
            chat_id = chat.chat_id,
            author_id = author.id,
            message_count = 2,
            wait_seconds = 0.5,
        )
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
            outcome = _ingest_update(stubs.external.whatsapp_update(entry = []))

        self.assertEqual(outcome.scheduled_bursts, [first_scheduled, second_scheduled])
        self.assertEqual(self.burst_service.record.call_count, 2)
        self.assertEqual(
            [record.kwargs["message"].author_id for record in self.burst_service.record.call_args_list],
            [author.id, author.id],
        )

    def test_different_group_authors_schedule_independent_bursts(self):
        chat = stubs.domain.chat_config(
            chat_id = UUID(int = 10),
            is_private = False,
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        author = stubs.domain.user(
            id = UUID(int = 20),
        )
        message = stubs.domain.chat_message(
            chat_id = chat.chat_id,
            message_id = "message-1",
            ingestion_order = 7,
            author_id = author.id,
            sent_at = datetime(2026, 1, 2, 12, 0, 0),
            text = "hello",
        )
        ingested = stubs.domain.ingested_chat_message(
            chat = chat,
            author = author,
            message = message,
            attachments = [],
            raw_message_text = "hello",
        )
        other_author = stubs.domain.user(
            id = UUID(int = 21),
        )
        other_message = stubs.domain.chat_message(
            chat_id = chat.chat_id,
            message_id = "message-2",
            ingestion_order = 8,
            author_id = other_author.id,
            sent_at = message.sent_at,
            text = "other",
        )
        other = stubs.domain.ingested_chat_message(
            chat = chat,
            author = other_author,
            message = other_message,
            attachments = [],
            raw_message_text = "other",
        )
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [ingested, other]
        session = MagicMock()
        self.burst_service.record.side_effect = [
            stubs.domain.scheduled_chat_message_burst(
                chat_id = chat.chat_id,
                author_id = author.id,
                message_count = 1,
                wait_seconds = 0.5,
            ),
            stubs.domain.scheduled_chat_message_burst(
                chat_id = chat.chat_id,
                author_id = other_author.id,
                message_count = 1,
                wait_seconds = 0.5,
            ),
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
            _ingest_update(stubs.external.whatsapp_update(entry = []))

        self.assertEqual(
            [item.kwargs["message"].author_id for item in self.burst_service.record.call_args_list],
            [author.id, other_author.id],
        )

    def test_command_does_not_extend_conversational_burst(self):
        chat = stubs.domain.chat_config(
            chat_id = UUID(int = 10),
            chat_type = ChatConfigDB.ChatType.whatsapp,
        )
        author = stubs.domain.user(
            id = UUID(int = 20),
        )
        message = stubs.domain.chat_message(
            chat_id = chat.chat_id,
            message_id = "message-1",
            ingestion_order = 7,
            author_id = author.id,
            sent_at = datetime(2026, 1, 2, 12, 0, 0),
            text = "hello",
        )
        command = stubs.domain.ingested_chat_message(
            chat = chat,
            author = author,
            message = message,
            attachments = [],
            raw_message_text = "/help",
        )
        prompt_message = stubs.domain.chat_message(
            chat_id = chat.chat_id,
            message_id = "message-2",
            ingestion_order = 8,
            author_id = author.id,
            sent_at = message.sent_at + timedelta(milliseconds = 100),
            text = "prompt",
        )
        prompt = stubs.domain.ingested_chat_message(
            chat = chat,
            author = author,
            message = prompt_message,
            attachments = [],
            raw_message_text = "prompt",
        )
        self.di.whatsapp_chat_inbound_service.ingest_update.return_value = [command, prompt]
        self.burst_service.process_message.return_value = False
        session = MagicMock()
        self.burst_service.record.return_value = stubs.domain.scheduled_chat_message_burst(
            chat_id = chat.chat_id,
            author_id = author.id,
            message_count = 1,
            wait_seconds = 0.5,
        )
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
            outcome = _ingest_update(stubs.external.whatsapp_update(entry = []))

        self.burst_service.process_message.assert_called_once_with(
            command,
            command_only = True,
        )
        self.burst_service.record.assert_called_once()
        self.assertEqual(self.burst_service.record.call_args.kwargs["message"], prompt_message)
        self.assertEqual(len(outcome.scheduled_bursts), 1)

    def test_async_responder_processes_every_scheduled_burst(self):
        chat_id = UUID(int = 10)
        author_id = UUID(int = 20)
        first = stubs.domain.scheduled_chat_message_burst(
            chat_id = chat_id,
            author_id = author_id,
            message_count = 1,
            wait_seconds = 0.5,
        )
        second = stubs.domain.scheduled_chat_message_burst(
            chat_id = chat_id,
            author_id = UUID(int = 21),
            message_count = 2,
            wait_seconds = 0.5,
        )
        outcome = _IngressOutcome(scheduled_bursts = [first, second])
        second_di = Mock(spec = DI)
        second_burst_service = Mock(spec = MessageBurstService)
        # noinspection PyPropertyAccess
        second_di.message_burst_service = second_burst_service
        self.burst_service.process_after_quiet_period.return_value = False
        second_burst_service.process_after_quiet_period.return_value = True
        with (
            patch(
                "features.chat.whatsapp.whatsapp_update_responder.asyncio.to_thread",
                new = AsyncMock(return_value = outcome),
            ),
            patch(
                "features.chat.whatsapp.whatsapp_update_responder.DI",
                side_effect = [self.di, second_di],
            ) as di_factory,
        ):
            result = asyncio.run(
                respond_to_update(stubs.external.whatsapp_update(entry = [])),
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
