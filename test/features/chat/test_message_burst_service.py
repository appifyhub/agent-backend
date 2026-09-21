import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch
from uuid import UUID

import stubs
from langchain_core.messages import AIMessage

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.message_burst_service import MessageBurstService
from features.integrations.integrations import resolve_agent_user, resolve_external_handle


class MessageBurstServiceTest(unittest.TestCase):

    def setUp(self):
        self.di = Mock(spec = DI)
        self.service = MessageBurstService(self.di)
        self.di.tool_choice_resolver.get_tool.return_value = Mock()
        self.di.chat_agent.return_value.execute.return_value = AIMessage("response")
        self.di.domain_langchain_mapper.map_bot_message_to_storage.return_value = [
            Mock(text = "response"),
        ]

    def test_explicit_address_ignores_quoted_mentions(self):
        chat_type = ChatConfigDB.ChatType.telegram
        handle = resolve_external_handle(resolve_agent_user(chat_type), chat_type)

        self.assertTrue(self.service.is_explicitly_addressed(f"hello @{handle}", chat_type))
        self.assertFalse(self.service.is_explicitly_addressed(f">> hello @{handle}\nnot addressed", chat_type))

    def test_claimed_message_uses_cutoff_and_aggregate_addressing(self):
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
            raw_message_text = "hello",
        )

        claim = stubs.domain.claimed_chat_message_burst(
            chat_id = message.chat_id,
            author_id = message.author_id,
            message_count = 1,
            last_message_sent_at = message.sent_at,
            last_message_ingestion_order = message.ingestion_order,
        )

        result = self.service.process_message(ingested, claim = claim)

        self.assertTrue(result)
        self.di.chat_agent.assert_called_once_with(
            trigger_message_text = "hello",
            trigger_message_id = "message-1",
            configured_tool = self.di.tool_choice_resolver.get_tool.return_value,
            cutoff_sent_at = claim.last_message_sent_at,
            cutoff_ingestion_order = claim.last_message_ingestion_order,
            explicitly_addressed = True,
        )
        self.di.chat_agent.return_value.execute.assert_called_once()
        self.di.telegram_bot_sdk.send_text_message.assert_called_once_with(
            chat,
            "response",
        )

    def test_reaction_response_is_stored_and_sent(self):
        chat = stubs.domain.chat_config(
            chat_id = UUID(int = 10),
            external_id = "123",
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
            raw_message_text = "hello",
        )

        self.di.chat_agent.return_value.execute.return_value = AIMessage("👍")

        result = self.service.process_message(
            ingested,
            claim = stubs.domain.claimed_chat_message_burst(
                chat_id = message.chat_id,
                author_id = message.author_id,
                message_count = 1,
                last_message_sent_at = message.sent_at,
                last_message_ingestion_order = message.ingestion_order,
            ),
        )

        self.assertTrue(result)
        saved = self.di.chat_message_repo.save.call_args.args[0]
        self.assertEqual(saved.message_id, "reaction:message-1")
        self.assertEqual(saved.text, "<reaction>👍</reaction>")
        self.di.platform_bot_sdk.return_value.set_reaction.assert_called_once_with(
            "123",
            "message-1",
            "👍",
        )

    def test_whatsapp_message_marks_final_message_read(self):
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
            raw_message_text = "hello",
        )

        chat.chat_type = ChatConfigDB.ChatType.whatsapp

        result = self.service.process_message(
            ingested,
            claim = stubs.domain.claimed_chat_message_burst(
                chat_id = message.chat_id,
                author_id = message.author_id,
                message_count = 1,
                last_message_sent_at = message.sent_at,
                last_message_ingestion_order = message.ingestion_order,
                is_addressed = False,
            ),
        )

        self.assertTrue(result)
        self.di.whatsapp_bot_sdk.send_text_message.assert_called_once_with(
            chat,
            "response",
        )
        self.di.whatsapp_bot_sdk.mark_as_read.assert_called_once_with("message-1")

    def test_delayed_attempt_opens_no_database_session_before_sleep_finishes(self):
        message = stubs.domain.chat_message(
            chat_id = UUID(int = 10),
            message_id = "message-1",
            ingestion_order = 7,
            author_id = UUID(int = 20),
            sent_at = datetime(2026, 1, 2, 12, 0, 0),
            text = "hello",
        )
        sleep_started = asyncio.Event()
        release_sleep = asyncio.Event()
        detached_di = Mock(spec = DI)
        detached_repo = Mock()
        detached_repo.claim.return_value = None
        # noinspection PyPropertyAccess
        detached_di.chat_message_burst_repo = detached_repo
        self.di.clone.return_value = detached_di
        session = MagicMock()

        async def suspended_sleep(delay_s):
            self.assertEqual(delay_s, 0.5)
            sleep_started.set()
            await release_sleep.wait()

        async def scenario():
            with (
                patch(
                    "features.chat.message_burst_service.asyncio.sleep",
                    side_effect = suspended_sleep,
                ),
                patch(
                    "features.chat.message_burst_service.get_detached_session",
                    return_value = session,
                ) as get_session,
            ):
                task = asyncio.create_task(
                    self.service.process_after_quiet_period(
                        stubs.domain.scheduled_chat_message_burst(
                            chat_id = message.chat_id,
                            author_id = message.author_id,
                            message_count = 1,
                            wait_seconds = 0.5,
                        ),
                    ),
                )
                await sleep_started.wait()
                get_session.assert_not_called()
                release_sleep.set()
                self.assertFalse(await task)
                get_session.assert_called_once()

        asyncio.run(scenario())

    def test_obsolete_timer_noops_and_completion_schedules_waiting_messages(self):
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
            raw_message_text = "hello",
        )

        first = stubs.domain.scheduled_chat_message_burst(
            chat_id = message.chat_id,
            author_id = message.author_id,
            message_count = 1,
            wait_seconds = 0.5,
        )
        second = stubs.domain.scheduled_chat_message_burst(
            chat_id = message.chat_id,
            author_id = message.author_id,
            message_count = 2,
            wait_seconds = 0.5,
        )
        first_claim = stubs.domain.claimed_chat_message_burst(
            chat_id = message.chat_id,
            author_id = message.author_id,
            message_count = 1,
            last_message_sent_at = message.sent_at,
            last_message_ingestion_order = message.ingestion_order,
            is_addressed = False,
        )
        second_claim = stubs.domain.claimed_chat_message_burst(
            chat_id = message.chat_id,
            author_id = message.author_id,
            message_count = 2,
            last_message_sent_at = message.sent_at,
            last_message_ingestion_order = message.ingestion_order,
            is_addressed = False,
        )
        detached_service = Mock(spec = MessageBurstService)
        detached_di = Mock(spec = DI)
        detached_repo = Mock()
        detached_repo.claim.side_effect = [first_claim, second_claim]
        detached_repo.finalize.side_effect = [second, None]
        # noinspection PyPropertyAccess
        detached_di.chat_message_burst_repo = detached_repo
        # noinspection PyPropertyAccess
        detached_di.message_burst_service = detached_service
        detached_service.load_claimed_message.return_value = ingested
        detached_service.process_message.return_value = True
        self.di.clone.return_value = detached_di

        with (
            patch(
                "features.chat.message_burst_service.asyncio.sleep",
                new = AsyncMock(),
            ),
            patch(
                "features.chat.message_burst_service.get_detached_session",
                return_value = MagicMock(),
            ),
        ):
            result = asyncio.run(self.service.process_after_quiet_period(first))

        self.assertTrue(result)
        self.assertEqual(
            detached_service.process_message.call_args_list,
            [
                call(ingested, claim = first_claim),
                call(ingested, claim = second_claim),
            ],
        )
