from dataclasses import asdict
from datetime import datetime, timedelta
from unittest import TestCase
from uuid import uuid4

import stubs
from util.di_utils import di_for_tests

from di.di import DI
from features.cleanup.cleanup_service import CleanupService
from util.config import config


class CleanupServiceTest(TestCase):

    di: DI
    service: CleanupService

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user()))
        self.di.inject_invoker_chat(self.di.chat_config_repo.save(stubs.domain.chat_config()))
        self.di.user_repo.save(stubs.domain.user(
            id = stubs.domain.sponsorship().receiver_id,
            telegram_user_id = None,
            whatsapp_user_id = None,
            connect_key = "SPONSORSHIP-RECEIVER",
        ))
        self.service = self.di.cleanup_service

    def test_run_returns_all_phase_counts(self):
        now = datetime.now()
        retention = timedelta(days = config.cleanup_message_retention_days + 1)
        old = now - retention
        chats = [self.di.require_invoker_chat()] + [
            self.di.chat_config_repo.save(stubs.domain.chat_config(chat_id = uuid4(), external_id = f"chat-{index}"))
            for index in range(3)
        ]
        messages = [
            self.di.chat_message_repo.save(stubs.domain.chat_message(
                chat_id = chats[index % len(chats)].chat_id,
                message_id = f"message-{index}",
                ingestion_order = index + 1,
                sent_at = old,
            ))
            for index in range(10)
        ]
        for message in messages[:4]:
            self.di.chat_message_burst_repo.record_message(
                message, is_addressed = True, quiet_period_s = -retention.total_seconds(),
            )
        for index, message in enumerate(messages[:5]):
            self.di.chat_attachment_service.save(
                stubs.domain.chat_attachment(
                    id = f"attachment-{index}", external_id = None,
                    chat_id = message.chat_id, message_id = message.message_id,
                ),
                content = b"attachment content",
            )
        for index in range(2):
            self.di.chat_attachment_service.save(
                stubs.domain.chat_attachment(
                    id = f"orphan-{index}", external_id = None, message_id = None, created_at = old,
                ),
                content = b"orphan content",
            )
        for index in range(3):
            self.di.tools_cache_repo.save(stubs.domain.tools_cache(key = f"cache-{index}", expires_at = old))
        for _ in range(7):
            self.di.usage_record_repo.create(stubs.domain.usage_record(timestamp = old))
        for asset in ("BTC", "ETH"):
            self.di.price_alert_repo.save(stubs.domain.price_alert(
                asset_id = asset,
                last_price_time = now - timedelta(days = config.cleanup_price_alert_staleness_days + 1),
            ))
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            accepted_at = None,
            sponsored_at = now - timedelta(days = config.cleanup_sponsorship_staleness_days + 1),
        ))

        result = self.service.run()

        self.assertEqual(asdict(result), {
            "attachments_deleted": 5,
            "orphaned_attachments_deleted": 2,
            "messages_deleted": 10,
            "message_bursts_deleted": 4,
            "cache_entries_cleared": 3,
            "usage_records_deleted": 7,
            "price_alerts_deleted": 2,
            "sponsorships_deleted": 1,
        })
        self.assertEqual(self.di.chat_message_repo.get_all(), [])
        self.assertEqual(self.di.tools_cache_repo.get_all(), [])
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.di.invoker.id), [])
        self.assertEqual(self.di.price_alert_repo.get_all(), [])
        self.assertEqual(self.di.sponsorship_repo.get_all(), [])

    def test_run_with_zero_deletions(self):
        now = datetime.now()
        message = self.di.chat_message_repo.save(stubs.domain.chat_message(sent_at = now))
        self.di.chat_message_burst_repo.record_message(message, is_addressed = True, quiet_period_s = 60)
        attachment = self.di.chat_attachment_service.save(
            stubs.domain.chat_attachment(created_at = now),
            content = b"attachment content",
        )
        orphan = self.di.chat_attachment_service.save(
            stubs.domain.chat_attachment(
                id = "recent-orphan", external_id = None, message_id = None, created_at = now,
            ),
            content = b"orphan content",
        )
        cache = self.di.tools_cache_repo.save(stubs.domain.tools_cache(expires_at = now + timedelta(days = 1)))
        usage = self.di.usage_record_repo.create(stubs.domain.usage_record(timestamp = now))
        alert = self.di.price_alert_repo.save(stubs.domain.price_alert(last_price_time = now))
        sponsorship = self.di.sponsorship_repo.save(stubs.domain.sponsorship(sponsored_at = now, accepted_at = None))

        result = self.service.run()

        self.assertTrue(all(count == 0 for count in asdict(result).values()))
        self.assertEqual(self.di.chat_message_repo.get(message.chat_id, message.message_id), message)
        self.assertEqual(self.di.chat_attachment_service.get(attachment.id), attachment)
        self.assertEqual(self.di.chat_attachment_service.get(orphan.id), orphan)
        self.assertEqual(self.di.tools_cache_repo.get(cache.key), cache)
        self.assertEqual(self.di.usage_record_repo.get_by_user(self.di.invoker.id), [usage])
        self.assertEqual(self.di.price_alert_repo.get(alert.chat_id, alert.asset_type, alert.asset_id, alert.currency), alert)
        self.assertEqual(self.di.sponsorship_repo.get(sponsorship.sponsor_id, sponsorship.receiver_id), sponsorship)
