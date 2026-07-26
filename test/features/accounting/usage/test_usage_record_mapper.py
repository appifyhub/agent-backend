import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from db.model.usage_record import UsageRecordDB
from features.accounting.usage.participant_details import ParticipantDetails, ParticipantInfo
from features.accounting.usage.usage_record import UsageRecord
from features.accounting.usage.usage_record_mapper import db, domain
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_library import GPT_5_5


class UsageRecordMapperTest(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        # Use a real tool as requested by the user
        self.tool = GPT_5_5

        self.payer_id = uuid.uuid4()
        self.db_record = UsageRecordDB(
            id = uuid.uuid4(),
            user_id = uuid.uuid4(),
            payer_id = self.payer_id,
            uses_credits = True,
            chat_id = uuid.uuid4(),
            tool_id = self.tool.id,
            tool_name = self.tool.name,
            provider_id = self.tool.provider.id,
            provider_name = self.tool.provider.name,
            purpose = "chat",
            timestamp = datetime.now(timezone.utc),
            runtime_seconds = 1.5,
            remote_runtime_seconds = 0.5,
            model_cost_credits = 0.1,
            remote_runtime_cost_credits = 0.2,
            api_call_cost_credits = 0.3,
            maintenance_fee_credits = 0.4,
            total_cost_credits = 1.0,
            input_tokens = 100,
            output_tokens = 200,
            search_tokens = 50,
            total_tokens = 350,
            output_image_sizes = ["1024x1024"],
            input_image_sizes = ["512x512"],
            output_video_size = "2k",
            output_video_duration_seconds = 5,
        )

        self.domain_record = UsageRecord(
            user_id = self.db_record.user_id,
            payer_id = self.payer_id,
            uses_credits = True,
            chat_id = self.db_record.chat_id,
            tool = self.tool,
            tool_purpose = ToolType.chat,
            timestamp = self.db_record.timestamp,
            runtime_seconds = 1.5,
            remote_runtime_seconds = 0.5,
            model_cost_credits = 0.1,
            remote_runtime_cost_credits = 0.2,
            api_call_cost_credits = 0.3,
            maintenance_fee_credits = 0.4,
            total_cost_credits = 1.0,
            input_tokens = 100,
            output_tokens = 200,
            search_tokens = 50,
            total_tokens = 350,
            output_image_sizes = ["1024x1024"],
            input_image_sizes = ["512x512"],
            output_video_size = "2k",
            output_video_duration_seconds = 5,
        )

    def test_domain_to_db_none(self):
        db_obj = db(None)
        self.assertIsNone(db_obj)

    def test_domain_to_db(self):
        # The mapper.db function takes a domain model and returns a DB model
        # Note: generated IDs like 'id' are not part of domain model usually, but created by DB or passed in.
        # UsageRecord domain model doesn't have an ID.

        db_obj = db(self.domain_record)

        self.assertIsInstance(db_obj, UsageRecordDB)
        self.assertEqual(db_obj.user_id, self.domain_record.user_id)
        self.assertEqual(db_obj.payer_id, self.payer_id)
        self.assertTrue(db_obj.uses_credits)
        self.assertEqual(db_obj.tool_id, self.tool.id)
        self.assertEqual(db_obj.timestamp, self.domain_record.timestamp)
        self.assertEqual(db_obj.output_image_sizes, ["1024x1024"])
        self.assertEqual(db_obj.output_video_size, "2k")
        self.assertEqual(db_obj.output_video_duration_seconds, 5)
        self.assertEqual(db_obj.total_cost_credits, 1.0)
        self.assertEqual(db_obj.purpose, "chat")

    def test_db_to_domain(self):
        # The domain() mapper iterates over ALL_EXTERNAL_TOOLS imported in the module.
        # Since we are using a real tool (GPT_5_5), it should be found automatically.

        domain_obj = domain(self.db_record)

        self.assertIsInstance(domain_obj, UsageRecord)
        self.assertEqual(domain_obj.user_id, self.db_record.user_id)
        self.assertEqual(domain_obj.payer_id, self.payer_id)
        self.assertTrue(domain_obj.uses_credits)
        self.assertEqual(domain_obj.tool.id, self.tool.id)
        self.assertEqual(domain_obj.tool.name, self.tool.name)
        self.assertEqual(domain_obj.output_image_sizes, ["1024x1024"])
        self.assertEqual(domain_obj.output_video_size, "2k")
        self.assertEqual(domain_obj.output_video_duration_seconds, 5)
        self.assertEqual(domain_obj.total_cost_credits, 1.0)

        # Verify tool_purpose conversion string -> Enum
        self.assertEqual(domain_obj.tool_purpose, ToolType.chat)

    def test_db_to_domain_none(self):
        domain_obj = domain(None)
        self.assertIsNone(domain_obj)

    def test_db_to_domain_deprecated_tool_and_purpose(self):
        # Test case where tool is not found in library and purpose is invalid
        self.db_record.purpose = "unknown_purpose_that_does_not_exist"

        with patch("features.accounting.usage.usage_record_mapper.ALL_EXTERNAL_TOOLS", []):
            domain_obj = domain(self.db_record)

            self.assertIsInstance(domain_obj, UsageRecord)
            # Should have reconstructed a deprecated tool
            self.assertEqual(domain_obj.tool.id, self.tool.id)
            self.assertEqual(domain_obj.tool.name, self.tool.name)
            self.assertEqual(domain_obj.tool.types, [])
            self.assertEqual(domain_obj.tool.provider.id, self.tool.provider.id)
            # Purpose should fall back to deprecated
            self.assertEqual(domain_obj.tool_purpose, ToolType.deprecated)

    def test_db_to_domain_null_participant_details(self):
        self.db_record.participant_details = None
        domain_obj = domain(self.db_record)
        self.assertIsNone(domain_obj.participant_details)

    def test_db_to_domain_with_participant_details(self):
        uid1 = uuid.uuid4()
        uid2 = uuid.uuid4()
        self.db_record.participant_details = {
            "payer": {"user_id": str(uid1), "full_name": "Payer", "platform": "Telegram", "handle": "ph"},
            "owner": {"user_id": str(uid2), "full_name": "Owner", "platform": "WhatsApp", "handle": "oh"},
            "counterpart": None,
        }

        domain_obj = domain(self.db_record)

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
        payer = ParticipantInfo(user_id = uid1, full_name = "Payer", platform = "Telegram", handle = "ph")
        owner = ParticipantInfo(user_id = uid1, full_name = "Payer", platform = "Telegram", handle = "ph")
        counterpart = ParticipantInfo(user_id = uid2, full_name = "CP", platform = None, handle = None)
        self.domain_record.participant_details = ParticipantDetails(payer = payer, owner = owner, counterpart = counterpart)

        db_obj = db(self.domain_record)

        self.assertIsNotNone(db_obj.participant_details)
        self.assertEqual(db_obj.participant_details["payer"]["user_id"], str(uid1))
        self.assertEqual(db_obj.participant_details["payer"]["platform"], "Telegram")
        self.assertEqual(db_obj.participant_details["owner"]["user_id"], str(uid1))
        self.assertEqual(db_obj.participant_details["counterpart"]["user_id"], str(uid2))
        self.assertIsNone(db_obj.participant_details["counterpart"]["platform"])

    def test_participant_details_round_trip(self):
        uid1 = uuid.uuid4()
        uid2 = uuid.uuid4()
        payer = ParticipantInfo(user_id = uid1, full_name = "Payer", platform = "Telegram", handle = "ph")
        owner = ParticipantInfo(user_id = uid1, full_name = "Payer", platform = "Telegram", handle = "ph")
        counterpart = ParticipantInfo(user_id = uid2, full_name = "CP", platform = None, handle = None)
        self.domain_record.participant_details = ParticipantDetails(payer = payer, owner = owner, counterpart = counterpart)

        db_obj = db(self.domain_record)
        restored = domain(db_obj)

        self.assertEqual(restored.participant_details.payer.user_id, uid1)
        self.assertEqual(restored.participant_details.payer.full_name, "Payer")
        self.assertEqual(restored.participant_details.owner.user_id, uid1)
        self.assertEqual(restored.participant_details.counterpart.user_id, uid2)
        self.assertIsNone(restored.participant_details.counterpart.platform)
