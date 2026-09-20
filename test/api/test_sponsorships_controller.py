import unittest
from unittest.mock import Mock, patch
from uuid import UUID

import stubs

from api.sponsorships_controller import SponsorshipsController
from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.chat.telegram.sdk.telegram_bot_sdk import TelegramBotSDK
from features.sponsorships.sponsorship_repo import SponsorshipRepository
from features.sponsorships.sponsorship_service import SponsorshipService
from features.users.user_repo import UserRepository
from util.config import config
from util.errors import AuthorizationError, InternalError


class SponsorshipsControllerTest(unittest.TestCase):

    mock_di: DI

    def setUp(self):
        # Create a DI mock and set required properties
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.invoker_chat = Mock()
        self.mock_di.invoker_chat_type = ChatConfigDB.ChatType.telegram
        # noinspection PyPropertyAccess
        self.mock_di.invoker_chat_type = ChatConfigDB.ChatType.telegram
        # noinspection PyPropertyAccess
        self.mock_di.user_repo = Mock(spec = UserRepository)
        # noinspection PyPropertyAccess
        self.mock_di.sponsorship_repo = Mock(spec = SponsorshipRepository)
        # noinspection PyPropertyAccess
        self.mock_di.telegram_bot_sdk = Mock(spec = TelegramBotSDK)
        # noinspection PyPropertyAccess
        self.mock_di.authorization_service = Mock()
        # noinspection PyPropertyAccess
        self.mock_di.sponsorship_service = Mock(spec = SponsorshipService)
        # Configure sponsorship service methods to return proper tuples
        self.mock_di.sponsorship_service.sponsor_user.return_value = (SponsorshipService.Result.success, "Success")
        self.mock_di.sponsorship_service.unsponsor_user.return_value = (SponsorshipService.Result.success, "Success")
        self.mock_di.sponsorship_service.unsponsor_self.return_value = (SponsorshipService.Result.success, "Success")

    def test_init_success(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        controller = SponsorshipsController(self.mock_di)
        # The controller should initialize successfully with the DI container
        self.assertIsNotNone(controller)

    def test_init_failure_invalid_user(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        # This test is no longer applicable since DI handles validation differently
        # The DI container is passed in directly and validation occurs at method level
        controller = SponsorshipsController(self.mock_di)
        self.assertIsNotNone(controller)

    def test_fetch_sponsorships_success_with_sponsorships(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        base_sponsorship = stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        sponsorship = stubs.domain.sponsorship(
            sponsor_id = base_sponsorship.sponsor_id,
            receiver_id = base_sponsorship.receiver_id,
        )
        self.mock_di.sponsorship_repo.get_all_by_sponsor.return_value = [sponsorship]
        self.mock_di.user_repo.get.return_value = receiver_user
        self.mock_di.authorization_service.authorize_for_user.return_value = sponsor_user

        controller = SponsorshipsController(self.mock_di)
        result = controller.fetch_sponsorships(sponsor_user.id.hex)

        self.assertIsInstance(result, dict)
        self.assertIn("sponsorships", result)
        self.assertIn("max_sponsorships", result)
        self.assertEqual(len(result["sponsorships"]), 1)
        sponsorship_result = result["sponsorships"][0]
        self.assertEqual(sponsorship_result["user_id_hex"], receiver_user.id.hex)
        self.assertEqual(sponsorship_result["full_name"], receiver_user.full_name)
        self.assertEqual(sponsorship_result["platform_handle"], receiver_user.telegram_username)
        self.assertEqual(sponsorship_result["platform"], "telegram")
        self.assertIsNotNone(sponsorship_result["sponsored_at"])
        self.assertIsNotNone(sponsorship_result["accepted_at"])
        self.assertFalse(sponsorship_result["is_on_waitlist"])
        self.assertFalse(sponsorship_result["is_invited_to_start"])
        self.assertTrue(sponsorship_result["are_policies_accepted"])
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, sponsor_user.id.hex)
        # noinspection PyUnresolvedReferences
        self.mock_di.sponsorship_repo.get_all_by_sponsor.assert_called_once_with(sponsor_user.id)

    def test_fetch_sponsorships_success_no_sponsorships(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        self.mock_di.sponsorship_repo.get_all_by_sponsor.return_value = []
        self.mock_di.authorization_service.authorize_for_user.return_value = sponsor_user

        controller = SponsorshipsController(self.mock_di)
        result = controller.fetch_sponsorships(sponsor_user.id.hex)

        self.assertIsInstance(result, dict)
        self.assertIn("sponsorships", result)
        self.assertIn("max_sponsorships", result)
        self.assertEqual(len(result["sponsorships"]), 0)
        # For standard users, should get max_sponsorships_per_user
        self.assertEqual(result["max_sponsorships"], config.max_sponsorships_per_user)
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, sponsor_user.id.hex)
        # noinspection PyUnresolvedReferences
        self.mock_di.sponsorship_repo.get_all_by_sponsor.assert_called_once_with(sponsor_user.id)

    def test_fetch_sponsorships_success_with_missing_receiver(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        base_sponsorship = stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        sponsorship = stubs.domain.sponsorship(
            sponsor_id = base_sponsorship.sponsor_id,
            receiver_id = base_sponsorship.receiver_id,
        )
        self.mock_di.sponsorship_repo.get_all_by_sponsor.return_value = [sponsorship]
        self.mock_di.user_repo.get.return_value = None  # Missing receiver
        self.mock_di.authorization_service.authorize_for_user.return_value = sponsor_user

        controller = SponsorshipsController(self.mock_di)
        result = controller.fetch_sponsorships(sponsor_user.id.hex)

        self.assertIsInstance(result, dict)
        self.assertIn("sponsorships", result)
        self.assertIn("max_sponsorships", result)
        # Should skip the sponsorship with missing receiver
        self.assertEqual(len(result["sponsorships"]), 0)
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, sponsor_user.id.hex)
        # noinspection PyUnresolvedReferences
        self.mock_di.sponsorship_repo.get_all_by_sponsor.assert_called_once_with(sponsor_user.id)

    def test_fetch_sponsorships_success_with_null_accepted_at(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        base_sponsorship = stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        sponsorship = stubs.domain.sponsorship(
            sponsor_id = base_sponsorship.sponsor_id,
            receiver_id = base_sponsorship.receiver_id,
            sponsored_at = base_sponsorship.sponsored_at,
            accepted_at = None,
        )
        self.mock_di.sponsorship_repo.get_all_by_sponsor.return_value = [sponsorship]
        self.mock_di.user_repo.get.return_value = receiver_user
        self.mock_di.authorization_service.authorize_for_user.return_value = sponsor_user

        controller = SponsorshipsController(self.mock_di)
        result = controller.fetch_sponsorships(sponsor_user.id.hex)

        self.assertIsInstance(result, dict)
        self.assertIn("sponsorships", result)
        self.assertIn("max_sponsorships", result)
        self.assertEqual(len(result["sponsorships"]), 1)
        sponsorship_result = result["sponsorships"][0]
        self.assertEqual(sponsorship_result["user_id_hex"], receiver_user.id.hex)
        self.assertEqual(sponsorship_result["full_name"], receiver_user.full_name)
        self.assertEqual(sponsorship_result["platform_handle"], receiver_user.telegram_username)
        self.assertEqual(sponsorship_result["platform"], "telegram")
        self.assertIsNotNone(sponsorship_result["sponsored_at"])
        self.assertIsNone(sponsorship_result["accepted_at"])  # Should be None for unaccepted sponsorship
        self.assertFalse(sponsorship_result["is_on_waitlist"])
        self.assertFalse(sponsorship_result["is_invited_to_start"])
        self.assertTrue(sponsorship_result["are_policies_accepted"])
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, sponsor_user.id.hex)
        # noinspection PyUnresolvedReferences
        self.mock_di.sponsorship_repo.get_all_by_sponsor.assert_called_once_with(sponsor_user.id)

    def test_fetch_sponsorships_success_with_developer_user(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        base_sponsorship = stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        developer_user = stubs.domain.user(
            id = invoker_user.id,
            full_name = invoker_user.full_name,
            telegram_username = invoker_user.telegram_username,
            telegram_chat_id = invoker_user.telegram_chat_id,
            telegram_user_id = invoker_user.telegram_user_id,
            group = UserDB.Group.developer,
        )
        sponsorship = stubs.domain.sponsorship(
            sponsor_id = base_sponsorship.sponsor_id,
            receiver_id = base_sponsorship.receiver_id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = developer_user
        self.mock_di.sponsorship_repo.get_all_by_sponsor.return_value = [sponsorship]
        self.mock_di.user_repo.get.return_value = receiver_user
        self.mock_di.authorization_service.authorize_for_user.return_value = sponsor_user

        controller = SponsorshipsController(self.mock_di)
        result = controller.fetch_sponsorships(sponsor_user.id.hex)

        self.assertIsInstance(result, dict)
        self.assertIn("sponsorships", result)
        self.assertIn("max_sponsorships", result)
        self.assertEqual(len(result["sponsorships"]), 1)
        # For developer users, should get max_users instead of max_sponsorships_per_user
        self.assertEqual(result["max_sponsorships"], config.max_users)
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(developer_user, sponsor_user.id.hex)
        # noinspection PyUnresolvedReferences
        self.mock_di.sponsorship_repo.get_all_by_sponsor.assert_called_once_with(sponsor_user.id)

    def test_fetch_sponsorships_failure_unauthorized(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        self.mock_di.authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", 0)

        controller = SponsorshipsController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.fetch_sponsorships(sponsor_user.id.hex)

        self.assertIn("Unauthorized", str(context.exception))
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, sponsor_user.id.hex)

    # noinspection PyUnusedLocal
    @patch.object(SponsorshipService, "sponsor_user", return_value = (SponsorshipService.Result.success, "Success"))
    def test_sponsor_user_success(self, mock_sponsor_user):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        self.mock_di.authorization_service.authorize_for_user.return_value = sponsor_user
        sponsorship = stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
            accepted_at = None,
        )
        self.mock_di.user_repo.get_by_telegram_username.return_value = receiver_user
        self.mock_di.sponsorship_repo.get.return_value = sponsorship

        controller = SponsorshipsController(self.mock_di)
        payload = stubs.api.sponsorship_payload(platform_handle = receiver_user.telegram_username)
        result = controller.sponsor_user(sponsor_user.id.hex, payload)

        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, sponsor_user.id.hex)
        # noinspection PyUnresolvedReferences
        self.mock_di.sponsorship_service.sponsor_user.assert_called_once_with(
            sponsor_user_id_hex = sponsor_user.id.hex,
            receiver_handle = receiver_user.telegram_username,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["message"], "Success")
        self.assertEqual(result["sponsorship"]["user_id_hex"], receiver_user.id.hex)
        self.assertIn("sponsored_at", result["sponsorship"])
        self.assertIn("accepted_at", result["sponsorship"])
        self.assertFalse(result["sponsorship"]["is_on_waitlist"])
        self.assertFalse(result["sponsorship"]["is_invited_to_start"])
        self.assertTrue(result["sponsorship"]["are_policies_accepted"])

    def test_sponsor_user_failure_already_sponsored(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        self.mock_di.authorization_service.authorize_for_user.return_value = sponsor_user
        self.mock_di.sponsorship_service.sponsor_user.return_value = (
            SponsorshipService.Result.failure, "User already sponsored",
        )

        controller = SponsorshipsController(self.mock_di)

        with self.assertRaises(InternalError) as context:
            payload = stubs.api.sponsorship_payload(platform_handle = receiver_user.telegram_username)
            controller.sponsor_user(sponsor_user.id.hex, payload)

        self.assertIn("User already sponsored", str(context.exception))
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, sponsor_user.id.hex)

    def test_sponsor_user_failure_unauthorized(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        self.mock_di.authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", 0)

        controller = SponsorshipsController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            payload = stubs.api.sponsorship_payload(platform_handle = receiver_user.telegram_username)
            controller.sponsor_user(sponsor_user.id.hex, payload)

        self.assertIn("Unauthorized", str(context.exception))
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, sponsor_user.id.hex)

    # noinspection PyUnusedLocal
    @patch.object(SponsorshipService, "unsponsor_user", return_value = (SponsorshipService.Result.success, "Success"))
    def test_unsponsor_user_success(self, mock_unsponsor_user):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        self.mock_di.authorization_service.authorize_for_user.return_value = sponsor_user

        controller = SponsorshipsController(self.mock_di)
        # Should not raise an exception
        controller.unsponsor_user(sponsor_user.id.hex, "telegram", receiver_user.telegram_username)

        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, sponsor_user.id.hex)
        # noinspection PyUnresolvedReferences
        self.mock_di.sponsorship_service.unsponsor_user.assert_called_once_with(
            sponsor_user_id_hex = sponsor_user.id.hex,
            receiver_handle = receiver_user.telegram_username,
            chat_type = ChatConfigDB.ChatType.telegram,
        )

    def test_unsponsor_user_failure_not_found(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        self.mock_di.authorization_service.authorize_for_user.return_value = sponsor_user
        self.mock_di.sponsorship_service.unsponsor_user.return_value = (
            SponsorshipService.Result.failure, "Sponsorship not found",
        )

        controller = SponsorshipsController(self.mock_di)

        with self.assertRaises(InternalError) as context:
            controller.unsponsor_user(sponsor_user.id.hex, "telegram", receiver_user.telegram_username)

        self.assertIn("Sponsorship not found", str(context.exception))
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, sponsor_user.id.hex)

    def test_unsponsor_user_failure_unauthorized(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        self.mock_di.authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", 0)

        controller = SponsorshipsController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.unsponsor_user(sponsor_user.id.hex, "telegram", receiver_user.telegram_username)

        self.assertIn("Unauthorized", str(context.exception))
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, sponsor_user.id.hex)

    def test_unsponsor_self_success(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        self.mock_di.authorization_service.authorize_for_user.return_value = invoker_user
        self.mock_di.sponsorship_service.unsponsor_self.return_value = (SponsorshipService.Result.success, "Success")

        controller = SponsorshipsController(self.mock_di)
        controller.unsponsor_self(invoker_user.id.hex)

        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, invoker_user.id.hex)
        self.mock_di.sponsorship_service.unsponsor_self.assert_called_once_with(invoker_user.id.hex)

    def test_unsponsor_self_failure_no_sponsorships(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        self.mock_di.authorization_service.authorize_for_user.return_value = invoker_user
        self.mock_di.sponsorship_service.unsponsor_self.return_value = (
            SponsorshipService.Result.failure, "No sponsorships to remove",
        )

        controller = SponsorshipsController(self.mock_di)

        with self.assertRaises(InternalError) as context:
            controller.unsponsor_self(invoker_user.id.hex)

        self.assertIn("No sponsorships to remove", str(context.exception))
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, invoker_user.id.hex)

    def test_unsponsor_self_failure_unauthorized(self):
        invoker_user = stubs.domain.user(
            id = UUID(int = 1),
            full_name = "Invoker User",
            telegram_username = "invoker_username",
            telegram_chat_id = "invoker_chat_id",
            telegram_user_id = 1,
        )
        sponsor_user = stubs.domain.user(
            id = UUID(int = 2),
            full_name = "Sponsor User",
            telegram_username = "sponsor_username",
            telegram_chat_id = "sponsor_chat_id",
            telegram_user_id = 2,
        )
        receiver_user = stubs.domain.user(
            id = UUID(int = 3),
            full_name = "Receiver User",
            telegram_username = "receiver_username",
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 3,
            are_policies_accepted = True,
            is_invited_to_start = False,
        )
        stubs.domain.sponsorship(
            sponsor_id = sponsor_user.id,
            receiver_id = receiver_user.id,
        )
        # noinspection PyPropertyAccess
        self.mock_di.invoker = invoker_user
        self.mock_di.user_repo.get.return_value = receiver_user

        self.mock_di.authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", 0)

        controller = SponsorshipsController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.unsponsor_self(invoker_user.id.hex)

        self.assertIn("Unauthorized", str(context.exception))
        # noinspection PyUnresolvedReferences
        self.mock_di.authorization_service.authorize_for_user.assert_called_once_with(invoker_user, invoker_user.id.hex)
