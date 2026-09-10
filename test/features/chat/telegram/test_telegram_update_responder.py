import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.config.chat_config import ChatConfig
from features.chat.ingested_chat_message import IngestedChatMessage
from features.chat.message.chat_message import ChatMessage
from features.chat.message_burst import ScheduledChatMessageBurst
from features.chat.message_burst_service import MessageBurstService
from features.chat.telegram.model.update import Update
from features.chat.telegram.telegram_update_responder import (
    _ingest_update,
    _IngressOutcome,
    respond_to_update,
)
from features.integrations.integrations import resolve_agent_user, resolve_external_handle
from features.users.user import User


class TelegramUpdateResponderTest(unittest.TestCase):

    def setUp(self):
        self.chat = ChatConfig(
            chat_id = UUID(int = 10),
            external_id = "123",
            is_private = False,
            reply_chance_percent = 0,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.author = User(
            id = UUID(int = 20),
            full_name = "Test User",
            telegram_user_id = 20,
            telegram_username = "test_user",
        )
        self.message = ChatMessage(
            chat_id = self.chat.chat_id,
            message_id = "message-1",
            ingestion_order = 7,
            author_id = self.author.id,
            sent_at = datetime(2026, 1, 2, 12, 0, 0),
            text = "hello",
        )
        self.ingested = IngestedChatMessage(
            chat = self.chat,
            author = self.author,
            message = self.message,
            attachments = [],
            raw_message_text = "hello",
        )
        self.di = Mock(spec = DI)
        self.burst_service = Mock(spec = MessageBurstService)
        # noinspection PyPropertyAccess
        self.di.message_burst_service = self.burst_service

    def test_command_is_processed_without_creating_burst(self):
        agent = resolve_agent_user(self.ingested.chat.chat_type)
        agent_handle = resolve_external_handle(agent, self.ingested.chat.chat_type)
        self.ingested.raw_message_text = f"/help@{agent_handle}"
        self.di.telegram_chat_inbound_service.ingest_update.return_value = self.ingested
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
            outcome = _ingest_update(Mock(spec = Update))

        self.assertIsNone(outcome.scheduled_burst)
        self.burst_service.process_message.assert_called_once_with(
            self.ingested,
            command_only = True,
        )
        self.burst_service.record.assert_not_called()

    def test_async_responder_offloads_ingestion_and_processing(self):
        scheduled = self._scheduled_burst()
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
            result = asyncio.run(respond_to_update(Mock(spec = Update)))

        self.assertTrue(result)
        to_thread.assert_awaited_once()
        di_factory.assert_called_once_with(
            invoker_id = scheduled.author_id.hex,
            invoker_chat_id = scheduled.chat_id.hex,
        )
        self.burst_service.process_after_quiet_period.assert_awaited_once()

    def _scheduled_burst(self, message_count: int = 1) -> ScheduledChatMessageBurst:
        return ScheduledChatMessageBurst(
            chat_id = self.chat.chat_id,
            author_id = self.author.id,
            message_count = message_count,
            wait_seconds = 0.5,
        )
