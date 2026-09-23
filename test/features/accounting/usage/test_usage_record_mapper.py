import unittest
import uuid
from unittest.mock import patch

import stubs

from db.model.usage_record import UsageRecordDB
from features.accounting.usage.usage_record import UsageRecord
from features.accounting.usage.usage_record_mapper import db, domain
from features.external_tools.external_tool import ToolType


class UsageRecordMapperTest(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None

    def test_domain_to_db_none(self):
        db_obj = db(None)
        self.assertIsNone(db_obj)

    def test_domain_to_db(self):
        # The mapper.db function takes a domain model and returns a DB model
        # Note: generated IDs like 'id' are not part of domain model usually, but created by DB or passed in.
        # UsageRecord domain model doesn't have an ID.
        record = stubs.domain.usage_record(
            payer_id = uuid.uuid4(),
            output_image_sizes = ["1024x1024"],
            output_video_size = "2k",
            output_video_duration_seconds = 5,
        )

        db_obj = db(record)

        self.assertIsInstance(db_obj, UsageRecordDB)
        self.assertEqual(db_obj.user_id, record.user_id)
        self.assertEqual(db_obj.payer_id, record.payer_id)
        self.assertTrue(db_obj.uses_credits)
        self.assertEqual(db_obj.tool_id, record.tool.id)
        self.assertEqual(db_obj.timestamp, record.timestamp)
        self.assertEqual(db_obj.output_image_sizes, record.output_image_sizes)
        self.assertEqual(db_obj.output_video_size, record.output_video_size)
        self.assertEqual(db_obj.output_video_duration_seconds, record.output_video_duration_seconds)
        self.assertEqual(db_obj.total_cost_credits, record.total_cost_credits)
        self.assertEqual(db_obj.purpose, ToolType.chat.value)

    def test_db_to_domain(self):
        # The domain() mapper iterates over ALL_EXTERNAL_TOOLS imported in the module.
        # The factory default tool should be found automatically.
        record = stubs.db.usage_record_db(
            payer_id = uuid.uuid4(),
            output_image_sizes = ["1024x1024"],
            output_video_size = "2k",
            output_video_duration_seconds = 5,
        )

        domain_obj = domain(record)

        self.assertIsInstance(domain_obj, UsageRecord)
        self.assertEqual(domain_obj.user_id, record.user_id)
        self.assertEqual(domain_obj.payer_id, record.payer_id)
        self.assertTrue(domain_obj.uses_credits)
        self.assertEqual(domain_obj.tool.id, record.tool_id)
        self.assertEqual(domain_obj.tool.name, record.tool_name)
        self.assertEqual(domain_obj.output_image_sizes, record.output_image_sizes)
        self.assertEqual(domain_obj.output_video_size, record.output_video_size)
        self.assertEqual(domain_obj.output_video_duration_seconds, record.output_video_duration_seconds)
        self.assertEqual(domain_obj.total_cost_credits, record.total_cost_credits)

        # Verify tool_purpose conversion string -> Enum
        self.assertEqual(domain_obj.tool_purpose, ToolType.chat)

    def test_db_to_domain_none(self):
        domain_obj = domain(None)
        self.assertIsNone(domain_obj)

    def test_db_to_domain_deprecated_tool_and_purpose(self):
        # Test case where tool is not found in library and purpose is invalid
        record = stubs.db.usage_record_db(
            purpose = "unknown_purpose_that_does_not_exist",
        )

        with patch("features.accounting.usage.usage_record_mapper.ALL_EXTERNAL_TOOLS", []):
            domain_obj = domain(record)

            self.assertIsInstance(domain_obj, UsageRecord)
            # Should have reconstructed a deprecated tool
            self.assertEqual(domain_obj.tool.id, record.tool_id)
            self.assertEqual(domain_obj.tool.name, record.tool_name)
            self.assertEqual(domain_obj.tool.types, [])
            self.assertEqual(domain_obj.tool.provider.id, record.provider_id)
            self.assertEqual(domain_obj.tool.provider.name, record.provider_name)
            # Purpose should fall back to deprecated
            self.assertEqual(domain_obj.tool_purpose, ToolType.deprecated)

    def test_db_to_domain_null_participant_details(self):
        record = stubs.db.usage_record_db(participant_details = None)
        domain_obj = domain(record)
        self.assertIsNone(domain_obj.participant_details)

    def test_db_to_domain_with_participant_details(self):
        uid1 = uuid.uuid4()
        uid2 = uuid.uuid4()
        participant_details = {
            "payer": {"user_id": str(uid1), "full_name": "Payer", "platform": "Telegram", "handle": "ph"},
            "owner": {"user_id": str(uid2), "full_name": "Owner", "platform": "WhatsApp", "handle": "oh"},
            "counterpart": None,
        }
        record = stubs.db.usage_record_db(participant_details = participant_details)

        domain_obj = domain(record)

        self.assertIsNotNone(domain_obj.participant_details)
        self.assertEqual(domain_obj.participant_details.payer.user_id, uid1)
        self.assertEqual(domain_obj.participant_details.payer.full_name, "Payer")
        self.assertEqual(domain_obj.participant_details.payer.platform, "Telegram")
        self.assertEqual(domain_obj.participant_details.payer.handle, "ph")
        self.assertEqual(domain_obj.participant_details.owner.user_id, uid2)
        self.assertEqual(domain_obj.participant_details.owner.platform, "WhatsApp")
        self.assertIsNone(domain_obj.participant_details.counterpart)

    def test_domain_to_db_with_participant_details(self):
        uid1 = uuid.uuid4()
        uid2 = uuid.uuid4()
        payer = stubs.domain.participant_info(user_id = uid1, platform = "Telegram")
        owner = stubs.domain.participant_info(user_id = uid1)
        counterpart = stubs.domain.participant_info(user_id = uid2, platform = None)
        participant_details = stubs.domain.participant_details(payer = payer, owner = owner, counterpart = counterpart)
        record = stubs.domain.usage_record(participant_details = participant_details)

        db_obj = db(record)

        self.assertIsNotNone(db_obj.participant_details)
        self.assertEqual(db_obj.participant_details["payer"]["user_id"], str(uid1))
        self.assertEqual(db_obj.participant_details["payer"]["platform"], "Telegram")
        self.assertEqual(db_obj.participant_details["owner"]["user_id"], str(uid1))
        self.assertEqual(db_obj.participant_details["counterpart"]["user_id"], str(uid2))
        self.assertIsNone(db_obj.participant_details["counterpart"]["platform"])

    def test_participant_details_round_trip(self):
        uid1 = uuid.uuid4()
        uid2 = uuid.uuid4()
        payer = stubs.domain.participant_info(user_id = uid1, full_name = "Payer")
        owner = stubs.domain.participant_info(user_id = uid1)
        counterpart = stubs.domain.participant_info(user_id = uid2, platform = None)
        participant_details = stubs.domain.participant_details(payer = payer, owner = owner, counterpart = counterpart)
        record = stubs.domain.usage_record(participant_details = participant_details)

        db_obj = db(record)
        restored = domain(db_obj)

        self.assertEqual(restored.participant_details.payer.user_id, uid1)
        self.assertEqual(restored.participant_details.payer.full_name, "Payer")
        self.assertEqual(restored.participant_details.owner.user_id, uid1)
        self.assertEqual(restored.participant_details.counterpart.user_id, uid2)
        self.assertIsNone(restored.participant_details.counterpart.platform)
