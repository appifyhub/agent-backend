import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID

import stubs

from di.di import DI
from features.chat.message_burst_service import MessageBurstService
from features.chat.telegram.telegram_update_responder import (
    _ingest_update,
    _IngressOutcome,
    respond_to_update,
)
from features.integrations.integrations import resolve_agent_user, resolve_external_handle


class TelegramUpdateResponderTest(unittest.TestCase):

    def setUp(self):
        self.di = Mock(spec = DI)
        self.burst_service = Mock(spec = MessageBurstService)
        # noinspection PyPropertyAccess
        self.di.message_burst_service = self.burst_service
        self.di.telegram_chat_inbound_service = Mock()

    def test_command_is_processed_without_creating_burst(self):
        chat = stubs.domain.chat_config(
            chat_id = UUID(int = 10),
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
        agent = resolve_agent_user(ingested.chat.chat_type)
        agent_handle = resolve_external_handle(agent, ingested.chat.chat_type)
        ingested.raw_message_text = f"/help@{agent_handle}"
        self.di.telegram_chat_inbound_service.ingest_update.return_value = ingested
        self.burst_service.process_message.return_value = False
        session = MagicMock()
        with (
            patch(
                "features.chat.telegram.telegram_update_responder.get_detached_session",
                return_value = session,
            ),
            patch(
                "features.chat.telegram.telegram_update_responder.DI",
                return_value = self.di,
            ),
        ):
            outcome = _ingest_update(stubs.external.telegram_update())

        self.assertIsNone(outcome.scheduled_burst)
        self.burst_service.process_message.assert_called_once_with(
            ingested,
            command_only = True,
        )
        self.burst_service.record.assert_not_called()

    def test_async_responder_offloads_ingestion_and_processing(self):
        scheduled = stubs.domain.scheduled_chat_message_burst()
        self.burst_service.process_after_quiet_period.return_value = True
        with (
            patch(
                "features.chat.telegram.telegram_update_responder.asyncio.to_thread",
                new = AsyncMock(return_value = _IngressOutcome(scheduled_burst = scheduled)),
            ) as to_thread,
            patch(
                "features.chat.telegram.telegram_update_responder.DI",
                return_value = self.di,
            ) as di_factory,
        ):
            result = asyncio.run(respond_to_update(stubs.external.telegram_update()))

        self.assertTrue(result)
        to_thread.assert_awaited_once()
        di_factory.assert_called_once_with(
            invoker_id = scheduled.author_id.hex,
            invoker_chat_id = scheduled.chat_id.hex,
        )
        self.burst_service.process_after_quiet_period.assert_awaited_once()
