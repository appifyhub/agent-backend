import unittest
from unittest.mock import MagicMock, patch

from features.cleanup.cleanup_service import CleanupResult, CleanupService


class CleanupServiceTest(unittest.TestCase):

    def _make_service(
        self,
        attachments_deleted = 0,
        messages_deleted = 0,
        cache_cleared = 0,
        usage_deleted = 0,
        alerts_deleted = 0,
        sponsorships_deleted = 0,
    ) -> CleanupService:
        di = MagicMock()
        di.chat_message_attachment_repo.delete_by_old_messages.return_value = attachments_deleted
        di.chat_message_repo.delete_older_than.return_value = messages_deleted
        di.tools_cache_repo.delete_expired.return_value = cache_cleared
        di.usage_record_repo.delete_older_than.return_value = usage_deleted
        di.price_alert_repo.delete_stale.return_value = alerts_deleted
        di.sponsorship_repo.delete_unaccepted_older_than.return_value = sponsorships_deleted
        return CleanupService(di)

    @patch("features.cleanup.cleanup_service.log")
    def test_run_returns_all_phase_counts(self, _):
        service = self._make_service(
            attachments_deleted = 5,
            messages_deleted = 10,
            cache_cleared = 3,
            usage_deleted = 7,
            alerts_deleted = 2,
            sponsorships_deleted = 1,
        )

        result = service.run()

        self.assertIsInstance(result, CleanupResult)
        self.assertEqual(result.attachments_deleted, 5)
        self.assertEqual(result.messages_deleted, 10)
        self.assertEqual(result.cache_entries_cleared, 3)
        self.assertEqual(result.usage_records_deleted, 7)
        self.assertEqual(result.price_alerts_deleted, 2)
        self.assertEqual(result.sponsorships_deleted, 1)

        calls = service._CleanupService__di.mock_calls
        attachment_delete = "chat_message_attachment_repo.delete_by_old_messages"
        message_delete = "chat_message_repo.delete_older_than"
        self.assertLess(
            next(i for i, call in enumerate(calls) if call[0] == attachment_delete),
            next(i for i, call in enumerate(calls) if call[0] == message_delete),
        )

    @patch("features.cleanup.cleanup_service.log")
    def test_attachment_failure_skips_message_deletion(self, _):
        service = self._make_service()
        service._CleanupService__di.chat_message_attachment_repo.delete_by_old_messages.side_effect = RuntimeError("DB error")

        result = service.run()

        service._CleanupService__di.chat_message_repo.delete_older_than.assert_not_called()
        self.assertEqual(result.attachments_deleted, 0)
        self.assertEqual(result.messages_deleted, 0)

    @patch("features.cleanup.cleanup_service.log")
    def test_phase_failure_does_not_block_subsequent_phases(self, _):
        service = self._make_service(
            cache_cleared = 3,
            alerts_deleted = 2,
            sponsorships_deleted = 1,
        )
        service._CleanupService__di.usage_record_repo.delete_older_than.side_effect = RuntimeError("DB error")

        result = service.run()

        self.assertEqual(result.cache_entries_cleared, 3)
        self.assertEqual(result.usage_records_deleted, 0)
        self.assertEqual(result.price_alerts_deleted, 2)
        self.assertEqual(result.sponsorships_deleted, 1)

    @patch("features.cleanup.cleanup_service.log")
    def test_run_with_zero_deletions(self, _):
        service = self._make_service()

        result = service.run()

        self.assertEqual(result, CleanupResult())
