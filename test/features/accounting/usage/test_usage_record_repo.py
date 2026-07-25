import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from db.sql_util import SQLUtil

from db.model.usage_record import UsageRecordDB
from features.accounting.usage.usage_record import UsageRecord
from features.accounting.usage.usage_record_repo import UsageRecordRepository
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import CLAUDE_4_5_HAIKU, GPT_5_5, TRANSFER_TOOL
from features.users.user import User


class UsageRecordRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: UsageRecordRepository
    user: User

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.usage_record_repo()
        self.user = self.sql.user_repo().save(User(connect_key = "TEST-KEY-1234"))

    def tearDown(self):
        self.sql.end_session()

    def _create_record(
        self,
        user_id = None,
        payer_id = None,
        tool = GPT_5_5,
        tool_purpose = ToolType.chat,
        total_cost_credits = 1.0,
        timestamp = None,
        counterpart_id = None,
    ) -> UsageRecord:
        actual_user_id = user_id or self.user.id
        return UsageRecord(
            user_id = actual_user_id,
            payer_id = payer_id or actual_user_id,
            tool = tool,
            tool_purpose = tool_purpose,
            timestamp = timestamp or datetime.now(timezone.utc),
            model_cost_credits = 0,
            remote_runtime_cost_credits = 0,
            api_call_cost_credits = 0,
            maintenance_fee_credits = 0,
            total_cost_credits = total_cost_credits,
            runtime_seconds = 1.0,
            counterpart_id = counterpart_id,
        )

    def test_create(self):
        record = UsageRecord(
            user_id = self.user.id,
            payer_id = self.user.id,
            tool = GPT_5_5,
            tool_purpose = ToolType.vision,
            model_cost_credits = 0.5,
            remote_runtime_cost_credits = 0.1,
            api_call_cost_credits = 0.0,
            maintenance_fee_credits = 0.1,
            total_cost_credits = 0.7,
            runtime_seconds = 1.5,
            output_image_sizes = ["1024x1024"],
        )

        persisted = self.repo.create(record)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.user_id, self.user.id)
        self.assertEqual(persisted.tool.id, record.tool.id)
        self.assertEqual(persisted.tool_purpose, ToolType.vision)
        self.assertEqual(persisted.total_cost_credits, 0.7)
        self.assertEqual(persisted.output_image_sizes, ["1024x1024"])

    def test_get(self):
        record = self._create_record()
        self.repo.create(record)

        db_record = self.sql.get_session().query(UsageRecordDB).filter(
            UsageRecordDB.user_id == self.user.id,
        ).first()

        fetched = self.repo.get(db_record.id)

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.user_id, self.user.id)
        self.assertEqual(fetched.tool.id, record.tool.id)

    def test_get_nonexistent(self):
        fetched = self.repo.get(uuid4())
        self.assertIsNone(fetched)

    def test_get_by_user_pagination_limit(self):
        for _ in range(3):
            self.repo.create(self._create_record())

        records = self.repo.get_by_user(self.user.id, limit = 2)
        self.assertEqual(len(records), 2)

        records_all = self.repo.get_by_user(self.user.id, limit = 10)
        self.assertEqual(len(records_all), 3)

    def test_get_by_user_pagination_skip(self):
        for _ in range(5):
            self.repo.create(self._create_record())

        records = self.repo.get_by_user(self.user.id, skip = 2, limit = 10)
        self.assertEqual(len(records), 3)

    def test_get_by_user_start_date_filter(self):
        now = datetime.now(timezone.utc)
        self.repo.create(self._create_record(timestamp = now - timedelta(days = 2)))
        self.repo.create(self._create_record(timestamp = now))

        records = self.repo.get_by_user(self.user.id, start_date = now - timedelta(hours = 1))

        self.assertEqual(len(records), 1)

    def test_get_by_user_end_date_filter(self):
        now = datetime.now(timezone.utc)
        self.repo.create(self._create_record(timestamp = now - timedelta(days = 2)))
        self.repo.create(self._create_record(timestamp = now))

        records = self.repo.get_by_user(self.user.id, end_date = now - timedelta(days = 1))

        self.assertEqual(len(records), 1)

    def test_get_by_user_date_range_filter(self):
        now = datetime.now(timezone.utc)
        self.repo.create(self._create_record(timestamp = now - timedelta(days = 5)))
        self.repo.create(self._create_record(timestamp = now - timedelta(days = 2)))
        self.repo.create(self._create_record(timestamp = now))

        records = self.repo.get_by_user(
            self.user.id,
            start_date = now - timedelta(days = 3),
            end_date = now - timedelta(days = 1),
        )

        self.assertEqual(len(records), 1)

    def test_get_by_user_include_sponsored(self):
        sponsored_user = self.sql.user_repo().save(User(connect_key = "SPONSORED-KEY"))

        self.repo.create(self._create_record(total_cost_credits = 10))
        self.repo.create(self._create_record(
            user_id = sponsored_user.id,
            payer_id = self.user.id,
            total_cost_credits = 20,
        ))

        records = self.repo.get_by_user(self.user.id, include_sponsored = True)

        self.assertEqual(len(records), 2)

    def test_get_by_user_exclude_self(self):
        sponsored_user = self.sql.user_repo().save(User(connect_key = "SPONSORED-KEY"))

        self.repo.create(self._create_record(total_cost_credits = 10))
        self.repo.create(self._create_record(
            user_id = sponsored_user.id,
            payer_id = self.user.id,
            total_cost_credits = 20,
        ))

        records = self.repo.get_by_user(self.user.id, include_sponsored = True, exclude_self = True)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].user_id, sponsored_user.id)

    def test_get_aggregates_by_user(self):
        self.repo.create(self._create_record(
            tool = GPT_5_5,
            tool_purpose = ToolType.chat,
            total_cost_credits = 10,
        ))
        self.repo.create(self._create_record(
            tool = GPT_5_5,
            tool_purpose = ToolType.chat,
            total_cost_credits = 5,
        ))
        self.repo.create(self._create_record(
            tool = CLAUDE_4_5_HAIKU,
            tool_purpose = ToolType.images_gen,
            total_cost_credits = 20,
        ))

        stats = self.repo.get_aggregates_by_user(self.user.id)

        self.assertEqual(stats.total_records, 3)
        self.assertEqual(stats.total_cost_credits, 35.0)
        self.assertEqual(stats.total_runtime_seconds, 3.0)

        # by_tool (keyed by tool_id)
        self.assertEqual(len(stats.by_tool), 2)
        self.assertEqual(stats.by_tool[GPT_5_5.id].record_count, 2)
        self.assertEqual(stats.by_tool[GPT_5_5.id].total_cost, 15.0)
        self.assertEqual(stats.by_tool[CLAUDE_4_5_HAIKU.id].record_count, 1)
        self.assertEqual(stats.by_tool[CLAUDE_4_5_HAIKU.id].total_cost, 20.0)

        # by_purpose
        self.assertEqual(len(stats.by_purpose), 2)
        self.assertEqual(stats.by_purpose[ToolType.chat.value].record_count, 2)
        self.assertEqual(stats.by_purpose[ToolType.chat.value].total_cost, 15.0)
        self.assertEqual(stats.by_purpose[ToolType.images_gen.value].record_count, 1)
        self.assertEqual(stats.by_purpose[ToolType.images_gen.value].total_cost, 20.0)

        # by_provider (keyed by provider_id)
        self.assertEqual(len(stats.by_provider), 2)
        self.assertEqual(stats.by_provider[GPT_5_5.provider.id].record_count, 2)
        self.assertEqual(stats.by_provider[GPT_5_5.provider.id].total_cost, 15.0)
        self.assertEqual(stats.by_provider[CLAUDE_4_5_HAIKU.provider.id].record_count, 1)
        self.assertEqual(stats.by_provider[CLAUDE_4_5_HAIKU.provider.id].total_cost, 20.0)

        # all_tools_used (list of ToolInfo)
        tool_ids = [t.id for t in stats.all_tools_used]
        self.assertIn(GPT_5_5.id, tool_ids)
        self.assertIn(CLAUDE_4_5_HAIKU.id, tool_ids)
        self.assertIn(ToolType.chat.value, stats.all_purposes_used)
        self.assertIn(ToolType.images_gen.value, stats.all_purposes_used)

    def test_get_aggregates_by_user_empty(self):
        stats = self.repo.get_aggregates_by_user(self.user.id)

        self.assertEqual(stats.total_records, 0)
        self.assertEqual(stats.total_cost_credits, 0.0)
        self.assertEqual(stats.total_runtime_seconds, 0.0)
        self.assertEqual(len(stats.by_tool), 0)
        self.assertEqual(len(stats.by_purpose), 0)
        self.assertEqual(len(stats.by_provider), 0)
        self.assertEqual(len(stats.all_tools_used), 0)
        self.assertEqual(len(stats.all_purposes_used), 0)
        self.assertEqual(len(stats.all_providers_used), 0)

    def test_get_aggregates_by_user_with_date_filter(self):
        now = datetime.now(timezone.utc)
        self.repo.create(self._create_record(
            timestamp = now - timedelta(days = 5),
            total_cost_credits = 100,
        ))
        self.repo.create(self._create_record(
            timestamp = now,
            total_cost_credits = 10,
        ))

        stats = self.repo.get_aggregates_by_user(
            self.user.id,
            start_date = now - timedelta(hours = 1),
        )

        self.assertEqual(stats.total_records, 1)
        self.assertEqual(stats.total_cost_credits, 10.0)

    def test_get_aggregates_by_user_include_sponsored(self):
        sponsored_user = self.sql.user_repo().save(User(connect_key = "SPONSORED-KEY"))

        self.repo.create(self._create_record(total_cost_credits = 10))
        self.repo.create(self._create_record(
            user_id = sponsored_user.id,
            payer_id = self.user.id,
            total_cost_credits = 20,
        ))

        stats = self.repo.get_aggregates_by_user(self.user.id, include_sponsored = True)

        self.assertEqual(stats.total_records, 2)
        self.assertEqual(stats.total_cost_credits, 30.0)

    def test_get_by_user_tool_filter(self):
        self.repo.create(self._create_record(tool = GPT_5_5))
        self.repo.create(self._create_record(tool = GPT_5_5))
        self.repo.create(self._create_record(tool = CLAUDE_4_5_HAIKU))

        records = self.repo.get_by_user(self.user.id, tool_id = GPT_5_5.id)

        self.assertEqual(len(records), 2)
        for r in records:
            self.assertEqual(r.tool.id, GPT_5_5.id)

    def test_get_by_user_purpose_filter(self):
        self.repo.create(self._create_record(tool_purpose = ToolType.chat))
        self.repo.create(self._create_record(tool_purpose = ToolType.chat))
        self.repo.create(self._create_record(tool_purpose = ToolType.images_gen))

        records = self.repo.get_by_user(self.user.id, purpose = ToolType.chat.value)

        self.assertEqual(len(records), 2)
        for r in records:
            self.assertEqual(r.tool_purpose, ToolType.chat)

    def test_get_by_user_provider_filter(self):
        self.repo.create(self._create_record(tool = GPT_5_5))
        self.repo.create(self._create_record(tool = GPT_5_5))
        self.repo.create(self._create_record(tool = CLAUDE_4_5_HAIKU))

        records = self.repo.get_by_user(self.user.id, provider_id = GPT_5_5.provider.id)

        self.assertEqual(len(records), 2)
        for r in records:
            self.assertEqual(r.tool.provider.id, GPT_5_5.provider.id)

    def test_get_aggregates_by_user_with_filter_keeps_all_lists_unfiltered(self):
        # Create records with different tools
        self.repo.create(self._create_record(
            tool = GPT_5_5,
            tool_purpose = ToolType.chat,
            total_cost_credits = 10,
        ))
        self.repo.create(self._create_record(
            tool = CLAUDE_4_5_HAIKU,
            tool_purpose = ToolType.images_gen,
            total_cost_credits = 20,
        ))

        # Filter by GPT_5_5 only
        stats = self.repo.get_aggregates_by_user(self.user.id, tool_id = GPT_5_5.id)

        # Totals should be filtered (only GPT_5_5)
        self.assertEqual(stats.total_records, 1)
        self.assertEqual(stats.total_cost_credits, 10.0)
        self.assertEqual(len(stats.by_tool), 1)
        self.assertIn(GPT_5_5.id, stats.by_tool)

        # But all_*_used lists should include ALL tools in the date range (unfiltered)
        tool_ids = [t.id for t in stats.all_tools_used]
        self.assertEqual(len(tool_ids), 2)
        self.assertIn(GPT_5_5.id, tool_ids)
        self.assertIn(CLAUDE_4_5_HAIKU.id, tool_ids)

        # Same for purposes
        self.assertEqual(len(stats.all_purposes_used), 2)
        self.assertIn(ToolType.chat.value, stats.all_purposes_used)
        self.assertIn(ToolType.images_gen.value, stats.all_purposes_used)

        # Same for providers
        provider_ids = [p.id for p in stats.all_providers_used]
        self.assertEqual(len(provider_ids), 2)
        self.assertIn(GPT_5_5.provider.id, provider_ids)
        self.assertIn(CLAUDE_4_5_HAIKU.provider.id, provider_ids)

    def test_get_by_user_includes_transfers_by_default(self):
        self.repo.create(self._create_record(tool = GPT_5_5, tool_purpose = ToolType.chat))
        self.repo.create(self._create_record(tool = TRANSFER_TOOL, tool_purpose = ToolType.credit_transfer))

        records = self.repo.get_by_user(self.user.id)

        self.assertEqual(len(records), 2)

    def test_get_by_user_exclude_transfers(self):
        self.repo.create(self._create_record(tool = GPT_5_5, tool_purpose = ToolType.chat))
        self.repo.create(self._create_record(tool = TRANSFER_TOOL, tool_purpose = ToolType.credit_transfer))

        records = self.repo.get_by_user(self.user.id, include_transfers = False)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].tool_purpose, ToolType.chat)

    def test_get_by_user_only_transfers(self):
        self.repo.create(self._create_record(tool = GPT_5_5, tool_purpose = ToolType.chat))
        self.repo.create(self._create_record(tool = TRANSFER_TOOL, tool_purpose = ToolType.credit_transfer))
        self.repo.create(self._create_record(tool = TRANSFER_TOOL, tool_purpose = ToolType.credit_transfer))

        records = self.repo.get_by_user(self.user.id, only_transfers = True)

        self.assertEqual(len(records), 2)
        for r in records:
            self.assertEqual(r.tool_purpose, ToolType.credit_transfer)

    def test_get_aggregates_includes_transfers_by_default(self):
        self.repo.create(self._create_record(tool = GPT_5_5, tool_purpose = ToolType.chat, total_cost_credits = 10))
        self.repo.create(self._create_record(
            tool = TRANSFER_TOOL, tool_purpose = ToolType.credit_transfer, total_cost_credits = 50,
        ))

        stats = self.repo.get_aggregates_by_user(self.user.id)

        self.assertEqual(stats.total_records, 2)
        self.assertEqual(stats.total_cost_credits, 60.0)
        self.assertIn(ToolType.credit_transfer.value, stats.all_purposes_used)

    def test_get_aggregates_exclude_transfers(self):
        self.repo.create(self._create_record(tool = GPT_5_5, tool_purpose = ToolType.chat, total_cost_credits = 10))
        self.repo.create(self._create_record(
            tool = TRANSFER_TOOL, tool_purpose = ToolType.credit_transfer, total_cost_credits = 50,
        ))

        stats = self.repo.get_aggregates_by_user(self.user.id, include_transfers = False)

        self.assertEqual(stats.total_records, 1)
        self.assertEqual(stats.total_cost_credits, 10.0)
        self.assertNotIn(ToolType.credit_transfer.value, stats.all_purposes_used)

    def test_get_aggregates_only_transfers(self):
        self.repo.create(self._create_record(tool = GPT_5_5, tool_purpose = ToolType.chat, total_cost_credits = 10))
        self.repo.create(self._create_record(
            tool = TRANSFER_TOOL, tool_purpose = ToolType.credit_transfer, total_cost_credits = 50,
        ))

        stats = self.repo.get_aggregates_by_user(self.user.id, only_transfers = True)

        self.assertEqual(stats.total_records, 1)
        self.assertEqual(stats.total_cost_credits, 50.0)
        self.assertNotIn(ToolType.chat.value, stats.all_purposes_used)

    def test_get_by_user_includes_incoming_transfer_as_counterpart(self):
        other_user = self.sql.user_repo().save(User(connect_key = "OTHER-KEY"))
        self.repo.create(self._create_record(tool = GPT_5_5, tool_purpose = ToolType.chat))
        self.repo.create(self._create_record(
            user_id = other_user.id,
            payer_id = other_user.id,
            tool = TRANSFER_TOOL,
            tool_purpose = ToolType.credit_transfer,
            total_cost_credits = 25,
            counterpart_id = self.user.id,
        ))

        records = self.repo.get_by_user(self.user.id)

        self.assertEqual(len(records), 2)
        purposes = {r.tool_purpose for r in records}
        self.assertIn(ToolType.credit_transfer, purposes)
        self.assertIn(ToolType.chat, purposes)

    def test_get_by_user_excludes_incoming_transfer_when_transfers_excluded(self):
        other_user = self.sql.user_repo().save(User(connect_key = "OTHER-KEY"))
        self.repo.create(self._create_record(tool = GPT_5_5, tool_purpose = ToolType.chat))
        self.repo.create(self._create_record(
            user_id = other_user.id,
            payer_id = other_user.id,
            tool = TRANSFER_TOOL,
            tool_purpose = ToolType.credit_transfer,
            total_cost_credits = 25,
            counterpart_id = self.user.id,
        ))

        records = self.repo.get_by_user(self.user.id, include_transfers = False)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].tool_purpose, ToolType.chat)

    def test_get_by_user_only_transfers_includes_counterpart(self):
        other_user = self.sql.user_repo().save(User(connect_key = "OTHER-KEY"))
        self.repo.create(self._create_record(tool = GPT_5_5, tool_purpose = ToolType.chat))
        self.repo.create(self._create_record(
            user_id = other_user.id,
            payer_id = other_user.id,
            tool = TRANSFER_TOOL,
            tool_purpose = ToolType.credit_transfer,
            total_cost_credits = 25,
            counterpart_id = self.user.id,
        ))

        records = self.repo.get_by_user(self.user.id, only_transfers = True)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].tool_purpose, ToolType.credit_transfer)
        self.assertEqual(records[0].counterpart_id, self.user.id)

    def test_get_aggregates_includes_incoming_transfer_as_counterpart(self):
        other_user = self.sql.user_repo().save(User(connect_key = "OTHER-KEY"))
        self.repo.create(self._create_record(tool = GPT_5_5, tool_purpose = ToolType.chat, total_cost_credits = 10))
        self.repo.create(self._create_record(
            user_id = other_user.id,
            payer_id = other_user.id,
            tool = TRANSFER_TOOL,
            tool_purpose = ToolType.credit_transfer,
            total_cost_credits = 25,
            counterpart_id = self.user.id,
        ))

        stats = self.repo.get_aggregates_by_user(self.user.id)

        self.assertEqual(stats.total_records, 2)
        self.assertEqual(stats.total_cost_credits, 35.0)

    def test_delete_older_than(self):
        self.repo.create(self._create_record(timestamp = datetime.now(timezone.utc) - timedelta(days = 31)))
        self.repo.create(self._create_record(timestamp = datetime.now(timezone.utc) - timedelta(days = 31)))
        self.repo.create(self._create_record(timestamp = datetime.now(timezone.utc)))
        cutoff = datetime.now(timezone.utc) - timedelta(days = 30)

        deleted_count = self.repo.delete_older_than(cutoff)

        self.assertEqual(deleted_count, 2)
        remaining = self.repo.get_by_user(self.user.id)
        self.assertEqual(len(remaining), 1)
