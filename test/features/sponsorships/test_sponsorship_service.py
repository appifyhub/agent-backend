from dataclasses import replace
from unittest import TestCase
from uuid import UUID

import stubs
from pydantic import SecretStr
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.sponsorships.sponsorship_service import SponsorshipService
from features.users.user import User
from util.config import config


class SponsorshipServiceTest(TestCase):

    di: DI
    service: SponsorshipService
    sponsor: User
    receiver: User

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.service = self.di.sponsorship_service
        self.sponsor = stubs.domain.user(telegram_username = "sponsor_username")
        self.receiver = stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_username = "receiver_username",
            telegram_user_id = None,
            telegram_chat_id = None,
            whatsapp_user_id = None,
            connect_key = "RECEIVER-KEY",
            open_ai_key = None,
            anthropic_key = None,
            google_ai_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            twelve_data_api_key = None,
            x_key = None,
            x_ai_key = None,
            credit_balance = 0.0,
        )

    def test_accept_sponsorship_success(self):
        self.di.user_repo.save(self.sponsor)
        self.di.user_repo.save(self.receiver)
        pending = self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.sponsor.id,
            receiver_id = self.receiver.id,
            accepted_at = None,
        ))

        result = self.service.accept_sponsorship(self.receiver)

        self.assertTrue(result)
        saved = self.di.sponsorship_repo.get(self.sponsor.id, self.receiver.id)
        self.assertEqual(saved.sponsored_at, pending.sponsored_at)
        self.assertIsNotNone(saved.accepted_at)

    def test_sponsor_user_success_with_twelve_data_key(self):
        sponsor = self.di.user_repo.save(stubs.domain.user(
            open_ai_key = None,
            anthropic_key = None,
            google_ai_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            twelve_data_api_key = SecretStr("twelve-data-key"),
            x_key = None,
            x_ai_key = None,
            credit_balance = 0.0,
        ))

        result, message = self.service.sponsor_user(
            sponsor.id.hex, self.receiver.telegram_username, ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.success)
        self.assertIn("Sponsorship sent", message)
        receiver = self.di.user_repo.get_by_telegram_username(self.receiver.telegram_username)
        self.assertIsNotNone(receiver)
        self.assertFalse(receiver.is_invited_to_start)
        self.assertFalse(receiver.are_policies_accepted)
        saved = self.di.sponsorship_repo.get(sponsor.id, receiver.id)
        self.assertIsNotNone(saved)
        self.assertIsNone(saved.accepted_at)

    def test_sponsor_user_failure_sponsor_not_found(self):
        result, message = self.service.sponsor_user(
            self.sponsor.id.hex, self.receiver.telegram_username, ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("Sponsor '", message)
        self.assertEqual(self.di.sponsorship_repo.get_all(), [])

    def test_sponsor_user_failure_sponsoring_self(self):
        self.di.user_repo.save(self.sponsor)

        result, message = self.service.sponsor_user(
            self.sponsor.id.hex, self.sponsor.telegram_username, ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("cannot sponsor themselves", message)
        self.assertEqual(self.di.sponsorship_repo.get_all(), [])

    def test_sponsor_user_failure_max_sponsorships_exceeded(self):
        self.addCleanup(setattr, config, "max_sponsorships_per_user", config.max_sponsorships_per_user)
        config.max_sponsorships_per_user = 1
        self.di.user_repo.save(self.sponsor)
        self.di.user_repo.save(self.receiver)
        existing = self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.sponsor.id, receiver_id = self.receiver.id,
        ))

        result, message = self.service.sponsor_user(
            self.sponsor.id.hex, "another_receiver", ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("exceeded the maximum number of sponsorships", message)
        self.assertEqual(self.di.sponsorship_repo.get_all_by_sponsor(self.sponsor.id), [existing])
        self.assertIsNone(self.di.user_repo.get_by_telegram_username("another_receiver"))

    def test_sponsor_user_success_developer_no_limit(self):
        self.addCleanup(setattr, config, "max_sponsorships_per_user", config.max_sponsorships_per_user)
        config.max_sponsorships_per_user = 1
        self.di.user_repo.save(replace(self.sponsor, group = UserDB.Group.developer))
        self.di.user_repo.save(self.receiver)
        existing = self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.sponsor.id, receiver_id = self.receiver.id,
        ))

        result, message = self.service.sponsor_user(
            self.sponsor.id.hex, "another_receiver", ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.success)
        self.assertIn("Sponsorship sent", message)
        receiver = self.di.user_repo.get_by_telegram_username("another_receiver")
        self.assertIsNotNone(receiver)
        self.assertIsNotNone(self.di.sponsorship_repo.get(self.sponsor.id, receiver.id))
        self.assertEqual(self.di.sponsorship_repo.get(self.sponsor.id, self.receiver.id), existing)

    def test_sponsor_user_at_capacity_creates_waitlisted_user(self):
        self.addCleanup(setattr, config, "max_users", config.max_users)
        config.max_users = 1
        self.di.user_repo.save(self.sponsor)

        result, _ = self.service.sponsor_user(
            self.sponsor.id.hex, self.receiver.telegram_username, ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.success)
        receiver = self.di.user_repo.get_by_telegram_username(self.receiver.telegram_username)
        self.assertIsNotNone(receiver)
        self.assertTrue(receiver.is_on_waitlist)
        self.assertFalse(receiver.is_invited_to_start)
        self.assertFalse(receiver.are_policies_accepted)
        self.assertIsNotNone(self.di.sponsorship_repo.get(self.sponsor.id, receiver.id))

    def test_sponsor_user_failure_no_api_key(self):
        sponsor = self.di.user_repo.save(self.receiver)

        result, message = self.service.sponsor_user(
            sponsor.id.hex, "another_receiver", ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("has no API keys or credits configured", message)
        self.assertEqual(self.di.sponsorship_repo.get_all(), [])
        self.assertIsNone(self.di.user_repo.get_by_telegram_username("another_receiver"))

    def test_sponsor_user_failure_transitive_sponsorship(self):
        self.di.user_repo.save(self.sponsor)
        self.di.user_repo.save(self.receiver)
        existing = self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.receiver.id, receiver_id = self.sponsor.id,
        ))

        result, message = self.service.sponsor_user(
            self.sponsor.id.hex, "another_receiver", ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("can't sponsor others while being sponsored themselves", message)
        self.assertEqual(self.di.sponsorship_repo.get_all(), [existing])

    def test_sponsor_user_failure_receiver_has_sponsorship(self):
        self.di.user_repo.save(self.sponsor)
        self.di.user_repo.save(self.receiver)
        existing = self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.sponsor.id, receiver_id = self.receiver.id,
        ))

        result, message = self.service.sponsor_user(
            self.sponsor.id.hex, self.receiver.telegram_username, ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("Receiver '@receiver_username' already has a sponsorship", message)
        self.assertEqual(self.di.sponsorship_repo.get_all(), [existing])

    def test_sponsor_user_failure_receiver_has_api_key(self):
        self.di.user_repo.save(self.sponsor)
        receiver = self.di.user_repo.save(replace(self.receiver, anthropic_key = SecretStr("receiver-anthropic-key")))

        result, message = self.service.sponsor_user(
            self.sponsor.id.hex, receiver.telegram_username, ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("already has API keys configured", message)
        self.assertEqual(self.di.sponsorship_repo.get_all(), [])
        self.assertEqual(self.di.user_repo.get(receiver.id), receiver)

    def test_unsponsor_user_success(self):
        self.di.user_repo.save(self.sponsor)
        receiver = self.di.user_repo.save(replace(self.receiver, anthropic_key = SecretStr("receiver-anthropic-key")))
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.sponsor.id, receiver_id = receiver.id,
        ))

        result, message = self.service.unsponsor_user(
            self.sponsor.id.hex, receiver.telegram_username, ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.success)
        self.assertIn("Sponsorship revoked", message)
        self.assertIsNone(self.di.sponsorship_repo.get(self.sponsor.id, receiver.id))
        # revoking sponsorship preserves the receiver's own credentials and profile
        self.assertEqual(self.di.user_repo.get(receiver.id), receiver)

    def test_unsponsor_user_failure_sponsor_not_found(self):
        result, message = self.service.unsponsor_user(
            self.sponsor.id.hex, self.receiver.telegram_username, ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("Sponsor '", message)

    def test_unsponsor_user_failure_no_sponsorship(self):
        self.di.user_repo.save(self.sponsor)
        self.di.user_repo.save(self.receiver)

        result, message = self.service.unsponsor_user(
            self.sponsor.id.hex, self.receiver.telegram_username, ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("No sponsorship", message)

    def test_accept_sponsorship_failure_no_sponsorship(self):
        self.di.user_repo.save(self.receiver)

        result = self.service.accept_sponsorship(self.receiver)

        self.assertFalse(result)
        self.assertEqual(self.di.sponsorship_repo.get_all_by_receiver(self.receiver.id), [])

    def test_accept_sponsorship_failure_has_api_key(self):
        self.di.user_repo.save(self.sponsor)
        receiver = self.di.user_repo.save(replace(self.receiver, anthropic_key = SecretStr("receiver-anthropic-key")))
        pending = self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.sponsor.id, receiver_id = receiver.id, accepted_at = None,
        ))

        result = self.service.accept_sponsorship(receiver)

        self.assertFalse(result)
        self.assertEqual(self.di.sponsorship_repo.get(self.sponsor.id, receiver.id), pending)

    # === unsponsor_by_user_id ===

    def test_unsponsor_by_user_id_success(self):
        self.di.user_repo.save(self.sponsor)
        self.di.user_repo.save(self.receiver)
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.sponsor.id, receiver_id = self.receiver.id,
        ))

        result, message = self.service.unsponsor_by_user_id(self.sponsor.id.hex, self.receiver.id.hex)

        self.assertEqual(result, SponsorshipService.Result.success)
        self.assertIn("Sponsorship revoked", message)
        self.assertIsNone(self.di.sponsorship_repo.get(self.sponsor.id, self.receiver.id))

    def test_unsponsor_by_user_id_failure_no_sponsorship(self):
        self.di.user_repo.save(self.sponsor)
        self.di.user_repo.save(self.receiver)

        result, message = self.service.unsponsor_by_user_id(self.sponsor.id.hex, self.receiver.id.hex)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("No sponsorship", message)

    # === unsponsor_self ===

    def test_unsponsor_self_success(self):
        self.di.user_repo.save(self.sponsor)
        self.di.user_repo.save(self.receiver)
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            sponsor_id = self.sponsor.id, receiver_id = self.receiver.id,
        ))

        result, message = self.service.unsponsor_self(self.receiver.id.hex)

        self.assertEqual(result, SponsorshipService.Result.success)
        self.assertIn("Sponsorship revoked", message)
        self.assertIsNone(self.di.sponsorship_repo.get(self.sponsor.id, self.receiver.id))

    def test_unsponsor_self_failure_user_not_found(self):
        result, message = self.service.unsponsor_self(self.receiver.id.hex)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("not found", message)

    def test_unsponsor_self_failure_no_sponsorships(self):
        self.di.user_repo.save(self.receiver)

        result, message = self.service.unsponsor_self(self.receiver.id.hex)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("has no sponsorships to remove", message)

    def test_sponsor_user_success_with_anthropic_key(self):
        sponsor = self.di.user_repo.save(replace(self.receiver, anthropic_key = SecretStr("test_anthropic_key")))

        result, message = self.service.sponsor_user(
            sponsor.id.hex, "another_receiver", ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.success)
        self.assertIn("Sponsorship sent", message)
        receiver = self.di.user_repo.get_by_telegram_username("another_receiver")
        self.assertIsNotNone(receiver)
        self.assertIsNotNone(self.di.sponsorship_repo.get(sponsor.id, receiver.id))
