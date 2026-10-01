from dataclasses import replace
from unittest import TestCase
from uuid import UUID

import stubs
from util.di_utils import di_for_tests

from api.sponsorships_controller import SponsorshipsController
from db.model.user import UserDB
from di.di import DI
from features.users.user import User
from util.config import config
from util.error_codes import NOT_TARGET_USER, SPONSORSHIP_OPERATION_FAILED, UNSPONSOR_SELF_FAILED
from util.errors import AuthorizationError, InternalError


class SponsorshipsControllerTest(TestCase):

    di: DI
    controller: SponsorshipsController
    sponsor: User
    receiver: User

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.sponsor = self.di.user_repo.save(stubs.domain.user())
        self.receiver = self.di.user_repo.save(stubs.domain.user(
            id = UUID("22222222-2222-4222-8222-b22222222222"),
            telegram_username = "receiver_handle",
            telegram_user_id = None,
            whatsapp_user_id = None,
            connect_key = "RECEIVER-KEY",
            is_invited_to_start = False,
        ))
        self.di.inject_invoker(self.sponsor)
        self.controller = self.di.sponsorships_controller

    def test_fetch_sponsorships_success_with_sponsorships(self):
        sponsorship = self.di.sponsorship_repo.save(stubs.domain.sponsorship())

        result = self.controller.fetch_sponsorships(self.sponsor.id.hex)

        self.assertEqual(result["max_sponsorships"], config.max_sponsorships_per_user)
        self.assertEqual(result["sponsorships"], [{
            "user_id_hex": self.receiver.id.hex,
            "full_name": self.receiver.full_name,
            "platform_handle": self.receiver.telegram_username,
            "platform": "telegram",
            "sponsored_at": sponsorship.sponsored_at.isoformat(),
            "accepted_at": sponsorship.accepted_at.isoformat(),
            "is_on_waitlist": self.receiver.is_on_waitlist,
            "is_invited_to_start": self.receiver.is_invited_to_start,
            "are_policies_accepted": self.receiver.are_policies_accepted,
        }])

    def test_fetch_sponsorships_success_no_sponsorships(self):
        result = self.controller.fetch_sponsorships(self.sponsor.id.hex)

        self.assertEqual(result["sponsorships"], [])
        self.assertEqual(result["max_sponsorships"], config.max_sponsorships_per_user)

    def test_fetch_sponsorships_success_with_missing_receiver(self):
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(
            receiver_id = UUID("33333333-3333-4333-8333-c33333333333"),
        ))

        result = self.controller.fetch_sponsorships(self.sponsor.id.hex)

        self.assertEqual(result["sponsorships"], [])

    def test_fetch_sponsorships_success_with_null_accepted_at(self):
        self.di.sponsorship_repo.save(stubs.domain.sponsorship(accepted_at = None))

        result = self.controller.fetch_sponsorships(self.sponsor.id.hex)

        self.assertEqual(len(result["sponsorships"]), 1)
        self.assertEqual(result["sponsorships"][0]["user_id_hex"], self.receiver.id.hex)
        self.assertIsNotNone(result["sponsorships"][0]["sponsored_at"])
        self.assertIsNone(result["sponsorships"][0]["accepted_at"])

    def test_fetch_sponsorships_success_with_developer_user(self):
        self.di.inject_invoker(self.di.user_repo.save(replace(self.sponsor, group = UserDB.Group.developer)))
        self.di.sponsorship_repo.save(stubs.domain.sponsorship())

        result = self.controller.fetch_sponsorships(self.sponsor.id.hex)

        self.assertEqual(len(result["sponsorships"]), 1)
        self.assertEqual(result["max_sponsorships"], config.max_users)

    def test_fetch_sponsorships_failure_unauthorized(self):
        with self.assertRaises(AuthorizationError) as context:
            self.controller.fetch_sponsorships(self.receiver.id.hex)

        self.assertEqual(context.exception.error_code, NOT_TARGET_USER)

    def test_sponsor_user_success(self):
        payload = stubs.api.sponsorship_payload(platform_handle = "new_receiver")

        result = self.controller.sponsor_user(self.sponsor.id.hex, payload)

        self.assertEqual(result["status"], "OK")
        self.assertIn("Sponsorship sent", result["message"])
        sponsorship = result["sponsorship"]
        self.assertEqual(sponsorship["platform_handle"], payload.platform_handle)
        self.assertEqual(sponsorship["platform"], payload.platform)
        self.assertIsNotNone(sponsorship["sponsored_at"])
        self.assertIsNone(sponsorship["accepted_at"])
        self.assertFalse(sponsorship["is_invited_to_start"])
        self.assertFalse(sponsorship["are_policies_accepted"])
        self.assertEqual(self.controller.fetch_sponsorships(self.sponsor.id.hex)["sponsorships"], [sponsorship])

    def test_sponsor_user_failure_already_sponsored(self):
        self.di.sponsorship_repo.save(stubs.domain.sponsorship())

        with self.assertRaises(InternalError) as context:
            self.controller.sponsor_user(self.sponsor.id.hex, stubs.api.sponsorship_payload())

        self.assertEqual(context.exception.error_code, SPONSORSHIP_OPERATION_FAILED)
        self.assertIn("already has a sponsorship", str(context.exception))

    def test_sponsor_user_failure_unauthorized(self):
        with self.assertRaises(AuthorizationError) as context:
            self.controller.sponsor_user(self.receiver.id.hex, stubs.api.sponsorship_payload())

        self.assertEqual(context.exception.error_code, NOT_TARGET_USER)
        self.assertEqual(self.controller.fetch_sponsorships(self.sponsor.id.hex)["sponsorships"], [])

    def test_unsponsor_user_success(self):
        self.di.sponsorship_repo.save(stubs.domain.sponsorship())

        self.controller.unsponsor_user(self.sponsor.id.hex, "telegram", self.receiver.telegram_username)

        self.assertEqual(self.controller.fetch_sponsorships(self.sponsor.id.hex)["sponsorships"], [])

    def test_unsponsor_user_failure_not_found(self):
        with self.assertRaises(InternalError) as context:
            self.controller.unsponsor_user(self.sponsor.id.hex, "telegram", self.receiver.telegram_username)

        self.assertEqual(context.exception.error_code, SPONSORSHIP_OPERATION_FAILED)
        self.assertIn("No sponsorship", str(context.exception))

    def test_unsponsor_user_failure_unauthorized(self):
        self.di.sponsorship_repo.save(stubs.domain.sponsorship())

        with self.assertRaises(AuthorizationError) as context:
            self.controller.unsponsor_user(self.receiver.id.hex, "telegram", self.receiver.telegram_username)

        self.assertEqual(context.exception.error_code, NOT_TARGET_USER)
        self.assertEqual(len(self.controller.fetch_sponsorships(self.sponsor.id.hex)["sponsorships"]), 1)

    def test_unsponsor_self_success(self):
        self.di.sponsorship_repo.save(stubs.domain.sponsorship())
        self.di.inject_invoker(self.receiver)

        self.controller.unsponsor_self(self.receiver.id.hex)

        self.assertEqual(self.di.sponsorship_repo.get_all_by_receiver(self.receiver.id), [])

    def test_unsponsor_self_failure_no_sponsorships(self):
        with self.assertRaises(InternalError) as context:
            self.controller.unsponsor_self(self.sponsor.id.hex)

        self.assertEqual(context.exception.error_code, UNSPONSOR_SELF_FAILED)
        self.assertIn("has no sponsorships to remove", str(context.exception))

    def test_unsponsor_self_failure_unauthorized(self):
        self.di.sponsorship_repo.save(stubs.domain.sponsorship())

        with self.assertRaises(AuthorizationError) as context:
            self.controller.unsponsor_self(self.receiver.id.hex)

        self.assertEqual(context.exception.error_code, NOT_TARGET_USER)
        self.assertEqual(len(self.controller.fetch_sponsorships(self.sponsor.id.hex)["sponsorships"]), 1)
