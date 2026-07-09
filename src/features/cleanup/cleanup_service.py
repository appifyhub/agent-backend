from dataclasses import dataclass, field
from datetime import datetime, timedelta

from util import log
from util.config import config


@dataclass
class CleanupResult:
    attachments_deleted: int = field(default = 0)
    orphaned_attachments_deleted: int = field(default = 0)
    messages_deleted: int = field(default = 0)
    cache_entries_cleared: int = field(default = 0)
    usage_records_deleted: int = field(default = 0)
    price_alerts_deleted: int = field(default = 0)
    sponsorships_deleted: int = field(default = 0)


class CleanupService:

    def __init__(self, di):
        self.__di = di

    def run(self) -> CleanupResult:
        result = CleanupResult()
        log.i("Cleanup starting...")

        message_cutoff = datetime.now() - timedelta(days = config.cleanup_message_retention_days)
        try:
            result.attachments_deleted = self.__di.chat_message_attachment_service.cleanup_old_attachments(message_cutoff)
            log.i(f"  Cleanup phase 1A: deleted {result.attachments_deleted} attachments")
            result.messages_deleted = self.__di.chat_message_repo.delete_older_than(message_cutoff)
            log.i(f"  Cleanup phase 1B: deleted {result.messages_deleted} messages")
            result.orphaned_attachments_deleted = self.__di.chat_message_attachment_service.cleanup_orphaned_attachments(message_cutoff)  # noqa: E501
            log.i(f"  Cleanup phase 1C: deleted {result.orphaned_attachments_deleted} orphaned attachments")
        except Exception as e:
            log.e(f"  Cleanup phase 1 (messages / attachments) failed: {e}")

        try:
            result.cache_entries_cleared = self.__di.tools_cache_repo.delete_expired()
            log.i(f"  Cleanup phase 2: cleared {result.cache_entries_cleared} cache entries")
        except Exception as e:
            log.e(f"  Cleanup phase 2 (cache) failed: {e}")

        try:
            result.usage_records_deleted = self.__di.usage_record_repo.delete_older_than(message_cutoff)
            log.i(f"  Cleanup phase 3: deleted {result.usage_records_deleted} usage records")
        except Exception as e:
            log.e(f"  Cleanup phase 3 (usage records) failed: {e}")

        try:
            price_alert_cutoff = datetime.now() - timedelta(days = config.cleanup_price_alert_staleness_days)
            result.price_alerts_deleted = self.__di.price_alert_repo.delete_stale(price_alert_cutoff)
            log.i(f"  Cleanup phase 4: deleted {result.price_alerts_deleted} price alerts")
        except Exception as e:
            log.e(f"  Cleanup phase 4 (price alerts) failed: {e}")

        try:
            sponsorship_cutoff = datetime.now() - timedelta(days = config.cleanup_sponsorship_staleness_days)
            result.sponsorships_deleted = self.__di.sponsorship_repo.delete_unaccepted_older_than(sponsorship_cutoff)
            log.i(f"  Cleanup phase 5: deleted {result.sponsorships_deleted} sponsorships")
        except Exception as e:
            log.e(f"  Cleanup phase 5 (sponsorships) failed: {e}")

        log.i("Cleanup completed.")
        return result
