from dataclasses import replace
from datetime import date
from unittest import TestCase
from uuid import UUID

import stubs
from pydantic import SecretStr
from util.di_utils import di_for_tests

from db.model.user import UserDB
from di.di import DI
from features.connect.profile_connect_service import ProfileConnectService
from features.users.user import User, generate_connect_key


class ProfileConnectServiceTest(TestCase):

    di: DI
    service: ProfileConnectService
    requester: User
    target: User

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.service = self.di.profile_connect_service
        self.requester = self.di.user_repo.save(stubs.domain.user(
            whatsapp_user_id = None,
            whatsapp_phone_number = None,
            created_at = date(2023, 1, 1),
        ))
        self.target = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            connect_key = "TARGET-KEY-1234",
            created_at = date(2024, 1, 1),
        ))

    def test_generate_connect_key(self):
        key = generate_connect_key()

        self.assertIsNotNone(key)
        self.assertEqual(len(key), 14)  # XXXX-XXXX-XXXX format
        self.assertEqual(key[4], "-")
        self.assertEqual(key[9], "-")
        self.assertTrue(key.replace("-", "").isupper())
        self.assertTrue(key.replace("-", "").isalnum())

    def test_connect_profiles_same_user(self):
        result, message = self.service.connect_profiles(self.requester, self.requester.connect_key)

        self.assertEqual(result, ProfileConnectService.Result.failure)
        self.assertIn("Cannot connect a profile to itself", message)
        self.assertEqual(self.di.user_repo.get(self.requester.id), self.requester)

    def test_connect_profiles_both_telegram_only(self):
        target = self.di.user_repo.save(replace(
            self.target,
            telegram_user_id = 456,
            telegram_username = "target_user",
            telegram_chat_id = "456",
            whatsapp_user_id = None,
            whatsapp_phone_number = None,
        ))

        result, message = self.service.connect_profiles(self.requester, target.connect_key)

        self.assertEqual(result, ProfileConnectService.Result.failure)
        self.assertIn("Telegram only", message)
        self.assertEqual(self.di.user_repo.get(self.requester.id), self.requester)
        self.assertEqual(self.di.user_repo.get(target.id), target)

    def test_connect_profiles_both_whatsapp_only(self):
        requester = self.di.user_repo.save(replace(
            self.requester,
            telegram_user_id = None,
            telegram_username = None,
            telegram_chat_id = None,
            whatsapp_user_id = "wa-requester",
            whatsapp_phone_number = SecretStr("+15559876543"),
        ))

        result, message = self.service.connect_profiles(requester, self.target.connect_key)

        self.assertEqual(result, ProfileConnectService.Result.failure)
        self.assertIn("WhatsApp only", message)
        self.assertEqual(self.di.user_repo.get(requester.id), requester)
        self.assertEqual(self.di.user_repo.get(self.target.id), self.target)

    def test_connect_profiles_preserves_older_target(self):
        result, _ = self.service.connect_profiles(self.target, self.requester.connect_key)

        self.assertEqual(result, ProfileConnectService.Result.success)
        survivor = self.di.user_repo.get(self.requester.id)
        self.assertIsNotNone(survivor)
        assert survivor is not None
        self.assertEqual(survivor.created_at, self.requester.created_at)
        self.assertEqual(survivor.telegram_user_id, self.requester.telegram_user_id)
        self.assertEqual(survivor.whatsapp_user_id, self.target.whatsapp_user_id)
        self.assertIsNone(self.di.user_repo.get(self.target.id))

    def test_connect_profiles_merges_user_data(self):
        survivor = self.di.user_repo.save(replace(
            self.requester,
            full_name = "Survivor",
            is_invited_to_start = False,
            open_ai_key = SecretStr("survivor-key"),
            anthropic_key = None,
            twelve_data_api_key = None,
            x_key = None,
            x_ai_key = None,
            tool_choice_api_stock_quote = None,
            tool_choice_images_gen = None,
            tool_choice_videos_gen = None,
        ))
        casualty = self.di.user_repo.save(replace(
            self.target,
            full_name = "Casualty",
            are_policies_accepted = False,
            anthropic_key = SecretStr("deleted-key"),
            twelve_data_api_key = SecretStr("deleted-twelve-data-key"),
            x_key = SecretStr("deleted-x-key"),
            x_ai_key = SecretStr("deleted-x-ai-key"),
            credit_balance = 50.0,
            group = UserDB.Group.developer,
        ))

        result, _ = self.service.connect_profiles(survivor, casualty.connect_key)

        self.assertEqual(result, ProfileConnectService.Result.success)
        merged = self.di.user_repo.get(survivor.id)
        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertEqual(merged.full_name, survivor.full_name)
        self.assertEqual(merged.telegram_user_id, survivor.telegram_user_id)
        self.assertEqual(merged.whatsapp_user_id, casualty.whatsapp_user_id)
        self.assertEqual(merged.open_ai_key, survivor.open_ai_key)
        self.assertEqual(merged.anthropic_key, casualty.anthropic_key)
        self.assertEqual(merged.twelve_data_api_key, casualty.twelve_data_api_key)
        self.assertEqual(merged.x_key, casualty.x_key)
        self.assertEqual(merged.x_ai_key, casualty.x_ai_key)
        self.assertEqual(merged.tool_choice_api_stock_quote, casualty.tool_choice_api_stock_quote)
        self.assertEqual(merged.tool_choice_images_gen, casualty.tool_choice_images_gen)
        self.assertEqual(merged.tool_choice_videos_gen, casualty.tool_choice_videos_gen)
        self.assertEqual(merged.credit_balance, 150.0)
        self.assertEqual(merged.group, UserDB.Group.developer)
        self.assertTrue(merged.are_policies_accepted)
        self.assertFalse(merged.is_on_waitlist)
        self.assertFalse(merged.is_invited_to_start)

    def test_connect_profiles_resets_invite_when_merged_user_is_active(self):
        requester = self.di.user_repo.save(replace(self.requester, is_invited_to_start = False))
        target = self.di.user_repo.save(replace(self.target, is_on_waitlist = True, are_policies_accepted = False))

        result, _ = self.service.connect_profiles(requester, target.connect_key)

        self.assertEqual(result, ProfileConnectService.Result.success)
        merged = self.di.user_repo.get(requester.id)
        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertFalse(merged.is_on_waitlist)
        self.assertFalse(merged.is_invited_to_start)
        self.assertTrue(merged.are_policies_accepted)

    def test_connect_profiles_moves_related_records(self):
        other_user = self.di.user_repo.save(stubs.domain.user(
            id = UUID("33333333-3333-4333-8333-c33333333333"),
            telegram_user_id = 789,
            telegram_chat_id = "789",
            whatsapp_user_id = None,
            whatsapp_phone_number = None,
            connect_key = "OTHER-KEY-1234",
        ))
        chat = self.di.chat_config_repo.save(stubs.domain.chat_config())
        membership = self.di.chat_membership_repo.save(stubs.domain.chat_membership(
            user_id = self.target.id,
            chat_id = chat.chat_id,
        ))
        attachment = self.di.chat_attachment_repo.save(stubs.domain.chat_attachment(
            chat_id = chat.chat_id,
            uploader_user_id = self.target.id,
        ))
        message = self.di.chat_message_repo.save(stubs.domain.chat_message(
            chat_id = chat.chat_id,
            author_id = self.target.id,
        ))
        alert = self.di.price_alert_repo.save(stubs.domain.price_alert(
            chat_id = chat.chat_id,
            owner_id = self.target.id,
        ))
        purchase = self.di.purchase_record_repo.save(stubs.domain.purchase_record(
            user_id = self.target.id,
        ))
        usage = self.di.usage_record_repo.create(stubs.domain.usage_record(
            user_id = self.target.id,
            payer_id = self.target.id,
            counterpart_id = self.target.id,
            chat_id = chat.chat_id,
        ))
        outgoing = self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.target.id,
            receiver_id = other_user.id,
        ))
        incoming = self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = other_user.id,
            receiver_id = self.target.id,
        ))
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.requester.id,
            receiver_id = self.target.id,
        ))
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.target.id,
            receiver_id = self.requester.id,
        ))

        result, _ = self.service.connect_profiles(self.requester, self.target.connect_key)

        self.assertEqual(result, ProfileConnectService.Result.success)
        self.assertEqual(
            self.di.chat_membership_repo.get(self.requester.id, chat.chat_id),
            replace(membership, user_id = self.requester.id),
        )
        self.assertEqual(
            self.di.chat_attachment_repo.get(attachment.id),
            replace(attachment, uploader_user_id = self.requester.id),
        )
        self.assertEqual(
            self.di.chat_message_repo.get(chat.chat_id, message.message_id),
            replace(message, author_id = self.requester.id),
        )
        self.assertEqual(
            self.di.price_alert_repo.get(chat.chat_id, alert.asset_type, alert.asset_id, alert.currency),
            replace(alert, owner_id = self.requester.id),
        )
        self.assertEqual(
            self.di.purchase_record_repo.get_by_user(self.requester.id),
            [replace(purchase, user_id = self.requester.id)],
        )
        self.assertEqual(
            self.di.usage_record_repo.get_by_user(self.requester.id),
            [replace(usage, user_id = self.requester.id, payer_id = self.requester.id, counterpart_id = self.requester.id)],
        )
        self.assertCountEqual(self.di.sponsorship_repo.get_all(), [
            replace(outgoing, sponsor_id = self.requester.id),
            replace(incoming, receiver_id = self.requester.id),
        ])

    def test_connect_profiles_invalid_key(self):
        result, message = self.service.connect_profiles(self.requester, "INVALID-KEY-HERE")

        self.assertEqual(result, ProfileConnectService.Result.failure)
        self.assertIn("Invalid connect key", message)
        self.assertEqual(self.di.user_repo.get(self.requester.id), self.requester)
        self.assertEqual(self.di.user_repo.get(self.target.id), self.target)

    def test_connect_profiles_success(self):
        result, message = self.service.connect_profiles(self.requester, self.target.connect_key)

        self.assertEqual(result, ProfileConnectService.Result.success)
        self.assertEqual(
            message,
            "Profiles connected successfully! Data was merged and you have a new connect key on the new joint profile.",
        )
        survivor = self.di.user_repo.get(self.requester.id)
        self.assertIsNotNone(survivor)
        assert survivor is not None
        self.assertEqual(survivor.telegram_user_id, self.requester.telegram_user_id)
        self.assertEqual(survivor.whatsapp_user_id, self.target.whatsapp_user_id)
        self.assertIsNone(self.di.user_repo.get(self.target.id))
        self.assertNotIn(survivor.connect_key, (self.requester.connect_key, self.target.connect_key))
        self.assertEqual(self.di.user_repo.get_by_connect_key(survivor.connect_key), survivor)
        self.assertIsNone(self.di.user_repo.get_by_connect_key(self.requester.connect_key))
        self.assertIsNone(self.di.user_repo.get_by_connect_key(self.target.connect_key))

    def test_regenerate_connect_key(self):
        new_key = self.service.regenerate_connect_key(self.requester)

        self.assertNotEqual(new_key, self.requester.connect_key)
        self.assertRegex(new_key, r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")
        self.assertEqual(self.di.user_repo.get(self.requester.id), replace(self.requester, connect_key = new_key))
        self.assertIsNone(self.di.user_repo.get_by_connect_key(self.requester.connect_key))
