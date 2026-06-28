import unittest
import unittest.mock
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import Mock
from uuid import UUID

from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.sponsorships.sponsorship import Sponsorship
from features.sponsorships.sponsorship_repo import SponsorshipRepository
from features.sponsorships.sponsorship_service import SponsorshipService
from features.users.user import User
from features.users.user_repo import UserRepository
from util.config import config


class SponsorshipServiceTest(unittest.TestCase):

    user: User
    mock_user_repo: UserRepository
    mock_sponsorship_repo: SponsorshipRepository
    mock_di: DI
    service: SponsorshipService

    def setUp(self):
        self.user = User(
            id = UUID(int = 1),
            full_name = "Test User",
            telegram_username = "test_username",
            telegram_chat_id = "test_chat_id",
            telegram_user_id = 1,
            open_ai_key = SecretStr("test_api_key"),
            anthropic_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.mock_user_repo = Mock(spec = UserRepository)
        self.mock_sponsorship_repo = Mock(spec = SponsorshipRepository)
        self.mock_di = Mock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.user_repo = self.mock_user_repo
        # noinspection PyPropertyAccess
        self.mock_di.sponsorship_repo = self.mock_sponsorship_repo
        self.service = SponsorshipService(self.mock_di)

    def test_accept_sponsorship_success(self):
        # Create user without API keys for this test
        user_without_keys = replace(
            self.user,
            open_ai_key = None,
            anthropic_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
        )

        mock_sponsorship = Sponsorship(
            accepted_at = None,
            sponsor_id = self.user.id,
            receiver_id = user_without_keys.id,
            sponsored_at = datetime.now() - timedelta(days = 1),
        )
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [mock_sponsorship]
        self.mock_sponsorship_repo.save.return_value = Sponsorship(
            sponsor_id = mock_sponsorship.sponsor_id,
            receiver_id = mock_sponsorship.receiver_id,
            sponsored_at = mock_sponsorship.sponsored_at,
            accepted_at = datetime.now(),
        )

        result = self.service.accept_sponsorship(user_without_keys)

        self.assertTrue(result)
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.save.assert_called()
        saved_sponsorship = self.mock_sponsorship_repo.save.call_args.args[0]
        self.assertEqual(saved_sponsorship.sponsored_at, mock_sponsorship.sponsored_at)
        self.assertIsNotNone(saved_sponsorship.accepted_at)

    def test_sponsor_user_success(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"

        receiver_user = User(
            id = UUID(int = 2),
            full_name = "Receiver User",
            telegram_username = receiver_telegram_username,
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 2,
            open_ai_key = None,
            anthropic_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.mock_user_repo.get.return_value = self.user
        self.mock_sponsorship_repo.get_all_by_sponsor.return_value = []
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []  # Ensure sponsor has no received sponsorships
        self.mock_user_repo.get_by_telegram_username.return_value = None
        self.mock_user_repo.count.return_value = 0
        self.mock_user_repo.save.return_value = receiver_user
        self.mock_sponsorship_repo.save.return_value = Sponsorship(
            sponsor_id = self.user.id,
            receiver_id = receiver_user.id,
        )

        result, msg = self.service.sponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.success)
        self.assertIn("Sponsorship sent", msg)
        # noinspection PyUnresolvedReferences
        self.mock_user_repo.get.assert_called_once_with(UUID(hex = sponsor_user_id_hex))
        # noinspection PyUnresolvedReferences
        self.mock_user_repo.save.assert_called()

    def test_sponsor_user_failure_sponsor_not_found(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"

        self.mock_user_repo.get.return_value = None

        result, msg = self.service.sponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("Sponsor '", msg)

    def test_sponsor_user_failure_sponsoring_self(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "test_username"

        self.mock_user_repo.get.return_value = self.user

        result, msg = self.service.sponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("cannot sponsor themselves", msg)

    def test_sponsor_user_failure_max_sponsorships_exceeded(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"

        self.mock_user_repo.get.return_value = self.user
        self.mock_sponsorship_repo.get_all_by_sponsor.return_value = [Mock()] * (config.max_sponsorships_per_user + 1)
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        result, msg = self.service.sponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("exceeded the maximum number of sponsorships", msg)

    def test_sponsor_user_success_developer_no_limit(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"

        developer_user = replace(self.user, group = UserDB.Group.developer)
        self.mock_user_repo.get.return_value = developer_user
        self.mock_sponsorship_repo.get_all_by_sponsor.return_value = [Mock()] * (config.max_sponsorships_per_user + 1)
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []
        self.mock_user_repo.get_by_telegram_username.return_value = None
        self.mock_user_repo.count.return_value = 0

        # Create a real user for the new user
        new_user = User(
            id = UUID(int = 2),
            full_name = "New User",
            telegram_username = receiver_telegram_username,
            telegram_chat_id = "new_chat_id",
            telegram_user_id = 2,
            connect_key = "NEW-USER-KEY1",
            open_ai_key = developer_user.open_ai_key,
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
            credit_balance = 0.0,
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = False,
        )

        self.mock_user_repo.save.return_value = new_user

        self.mock_sponsorship_repo.save.return_value = Sponsorship(
            sponsor_id = developer_user.id,
            receiver_id = new_user.id,
        )

        result, msg = self.service.sponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.success)
        self.assertIn("Sponsorship sent", msg)

    def test_sponsor_user_at_capacity_creates_waitlisted_user(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"
        receiver_user = User(
            id = UUID(int = 2),
            full_name = "Receiver User",
            telegram_username = receiver_telegram_username,
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 2,
            connect_key = "NEW-USER-KEY2",
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
            credit_balance = 0.0,
            is_on_waitlist = True,
            is_invited_to_start = False,
            are_policies_accepted = False,
        )
        self.mock_user_repo.get.return_value = self.user
        self.mock_sponsorship_repo.get_all_by_sponsor.return_value = []
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []
        self.mock_user_repo.get_by_telegram_username.return_value = None
        self.mock_user_repo.count.return_value = config.max_users
        self.mock_user_repo.save.return_value = receiver_user
        self.mock_sponsorship_repo.save.return_value = Sponsorship(
            sponsor_id = self.user.id,
            receiver_id = receiver_user.id,
        )

        result, _ = self.service.sponsor_user(
            sponsor_user_id_hex,
            receiver_telegram_username,
            ChatConfigDB.ChatType.telegram,
        )

        self.assertEqual(result, SponsorshipService.Result.success)
        saved_user_payload = self.mock_user_repo.save.call_args.args[0]
        self.assertTrue(saved_user_payload.is_on_waitlist)
        self.assertFalse(saved_user_payload.is_invited_to_start)
        self.assertFalse(saved_user_payload.are_policies_accepted)

    def test_sponsor_user_failure_no_api_key(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"

        # Create sponsor without any API keys
        sponsor_without_keys = replace(
            self.user,
            open_ai_key = None,
            anthropic_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
        )

        self.mock_user_repo.get.return_value = sponsor_without_keys
        # Mock the sponsorship checks that come before API key validation
        self.mock_sponsorship_repo.get_all_by_sponsor.return_value = []
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        result, msg = self.service.sponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("has no API keys or credits configured", msg)

    def test_sponsor_user_failure_transitive_sponsorship(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"

        self.mock_user_repo.get.return_value = self.user
        self.mock_sponsorship_repo.get_all_by_sponsor.return_value = []
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [Mock()]

        result, msg = self.service.sponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("can't sponsor others while being sponsored themselves", msg)

    def test_sponsor_user_failure_receiver_has_sponsorship(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"

        receiver_user = Mock(
            spec = User,
            id = UUID(int = 2),
            open_ai_key = None,
            full_name = "Receiver User",
            telegram_username = receiver_telegram_username,
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 2,
        )
        self.mock_user_repo.get.return_value = self.user
        self.mock_user_repo.get_by_telegram_username.return_value = receiver_user
        self.mock_sponsorship_repo.get_all_by_receiver.side_effect = [[], [Mock(spec = Sponsorship)]]
        self.mock_sponsorship_repo.get_all_by_sponsor.return_value = []

        result, msg = self.service.sponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("Receiver '@receiver_username' already has a sponsorship", msg)

    def test_sponsor_user_failure_receiver_has_api_key(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"

        receiver_user = User(
            id = UUID(int = 2),
            full_name = "Receiver User",
            telegram_username = receiver_telegram_username,
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 2,
            open_ai_key = SecretStr("receiver_api_key"),
            anthropic_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        self.mock_user_repo.get.return_value = self.user
        self.mock_sponsorship_repo.get_all_by_sponsor.return_value = []
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []  # No transitive sponsoring
        self.mock_user_repo.get_by_telegram_username.return_value = receiver_user

        result, msg = self.service.sponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("already has API keys configured", msg)

    def test_unsponsor_user_success(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"

        receiver_user = User(
            id = UUID(int = 2),
            full_name = "Receiver User",
            telegram_username = receiver_telegram_username,
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 2,
            open_ai_key = SecretStr("test_api_key"),
            anthropic_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        # Create a mock sponsorship
        sponsorship = Sponsorship(
            sponsor_id = self.user.id,
            receiver_id = receiver_user.id,
            sponsored_at = datetime.now(),
            accepted_at = None,
        )

        self.mock_user_repo.get.return_value = self.user
        self.mock_user_repo.get_by_telegram_username.return_value = receiver_user
        self.mock_sponsorship_repo.get.return_value = sponsorship

        result, msg = self.service.unsponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.success)
        self.assertIn("Sponsorship revoked", msg)
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.delete.assert_called_once_with(self.user.id, receiver_user.id)
        # Token removal is no longer handled by SponsorshipService
        # noinspection PyUnresolvedReferences
        self.mock_user_repo.save.assert_not_called()

    def test_unsponsor_user_failure_sponsor_not_found(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"

        self.mock_user_repo.get.side_effect = [None, None]

        result, msg = self.service.unsponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("Sponsor '", msg)

    def test_unsponsor_user_failure_no_sponsorship(self):
        sponsor_user_id_hex = self.user.id.hex
        receiver_telegram_username = "receiver_username"

        receiver_user = User(
            id = UUID(int = 2),
            full_name = "Receiver User",
            telegram_username = receiver_telegram_username,
            telegram_chat_id = "receiver_chat_id",
            telegram_user_id = 2,
            open_ai_key = None,
            anthropic_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.mock_user_repo.get.return_value = self.user
        self.mock_user_repo.get_by_telegram_username.return_value = receiver_user
        self.mock_sponsorship_repo.get.return_value = None

        result, msg = self.service.unsponsor_user(sponsor_user_id_hex, receiver_telegram_username, ChatConfigDB.ChatType.telegram)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("No sponsorship", msg)

    def test_accept_sponsorship_failure_no_sponsorship(self):
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        result = self.service.accept_sponsorship(self.user)

        self.assertFalse(result)

    def test_accept_sponsorship_failure_has_api_key(self):
        # User with API keys cannot accept sponsorship
        user_with_keys = self.user  # This user already has open_ai_key set in setUp

        result = self.service.accept_sponsorship(user_with_keys)

        self.assertFalse(result)

    def test_accept_sponsorship_success_no_api_key(self):
        # User without API keys can accept sponsorship
        user_without_keys = replace(
            self.user,
            open_ai_key = None,
            anthropic_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
        )

        # Create a real pending sponsorship
        pending_sponsorship = Sponsorship(
            sponsor_id = UUID(int = 999),
            receiver_id = user_without_keys.id,
            sponsored_at = datetime.now(),
            accepted_at = None,
        )
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [pending_sponsorship]
        self.mock_sponsorship_repo.save.return_value = Sponsorship(
            sponsor_id = pending_sponsorship.sponsor_id,
            receiver_id = pending_sponsorship.receiver_id,
            sponsored_at = pending_sponsorship.sponsored_at,
            accepted_at = datetime.now(),
        )

        result = self.service.accept_sponsorship(user_without_keys)

        self.assertTrue(result)
        saved_sponsorship = self.mock_sponsorship_repo.save.call_args.args[0]
        self.assertEqual(saved_sponsorship.sponsored_at, pending_sponsorship.sponsored_at)
        self.assertIsNotNone(saved_sponsorship.accepted_at)

    # === unsponsor_by_user_id ===

    def test_unsponsor_by_user_id_success(self):
        sponsor_id = UUID(int = 2)
        sponsorship = Sponsorship(
            sponsor_id = sponsor_id,
            receiver_id = self.user.id,
            sponsored_at = datetime.now(),
            accepted_at = datetime.now(),
        )
        self.mock_sponsorship_repo.get.return_value = sponsorship

        result, msg = self.service.unsponsor_by_user_id(sponsor_id.hex, self.user.id.hex)

        self.assertEqual(result, SponsorshipService.Result.success)
        self.assertIn("Sponsorship revoked", msg)
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.delete.assert_called_once_with(sponsor_id, self.user.id)

    def test_unsponsor_by_user_id_failure_no_sponsorship(self):
        self.mock_sponsorship_repo.get.return_value = None

        result, msg = self.service.unsponsor_by_user_id(UUID(int = 2).hex, self.user.id.hex)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("No sponsorship", msg)
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.delete.assert_not_called()

    # === unsponsor_self ===

    def test_unsponsor_self_success(self):
        user_id_hex = self.user.id.hex
        sponsor_id = UUID(int = 2)
        sponsorship = Sponsorship(
            sponsor_id = sponsor_id,
            receiver_id = self.user.id,
            sponsored_at = datetime.now(),
            accepted_at = datetime.now(),
        )
        self.mock_user_repo.get.return_value = self.user
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [sponsorship]
        self.mock_sponsorship_repo.get.return_value = sponsorship

        result, msg = self.service.unsponsor_self(user_id_hex)

        self.assertEqual(result, SponsorshipService.Result.success)
        self.assertIn("Sponsorship revoked", msg)
        # noinspection PyUnresolvedReferences
        self.mock_sponsorship_repo.delete.assert_called_once_with(sponsor_id, self.user.id)

    def test_unsponsor_self_failure_user_not_found(self):
        self.mock_user_repo.get.return_value = None

        result, msg = self.service.unsponsor_self(self.user.id.hex)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("not found", msg)

    def test_unsponsor_self_failure_no_sponsorships(self):
        self.mock_user_repo.get.return_value = self.user
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = []

        result, msg = self.service.unsponsor_self(self.user.id.hex)

        self.assertEqual(result, SponsorshipService.Result.failure)
        self.assertIn("has no sponsorships to remove", msg)

    def test_unsponsor_self_delegates_to_unsponsor_by_user_id(self):
        sponsor_id = UUID(int = 2)
        sponsorship = Sponsorship(
            sponsor_id = sponsor_id,
            receiver_id = self.user.id,
            sponsored_at = datetime.now(),
            accepted_at = datetime.now(),
        )
        self.mock_user_repo.get.return_value = self.user
        self.mock_sponsorship_repo.get_all_by_receiver.return_value = [sponsorship]

        with unittest.mock.patch.object(self.service, "unsponsor_by_user_id") as mock_method:
            mock_method.return_value = (SponsorshipService.Result.success, "Revoked")
            result, _ = self.service.unsponsor_self(self.user.id.hex)
            mock_method.assert_called_once_with(sponsor_id.hex, self.user.id.hex)
            self.assertEqual(result, SponsorshipService.Result.success)

    def test_user_has_any_api_key(self):
        # Test user with API key
        user_with_key = self.user  # Has open_ai_key from setUp
        self.assertTrue(user_with_key.has_any_api_key())

        # Test user without any API keys
        user_without_keys = replace(
            self.user,
            open_ai_key = None,
            anthropic_key = None,
            perplexity_key = None,
            replicate_key = None,
            rapid_api_key = None,
            coinmarketcap_key = None,
        )
        self.assertFalse(user_without_keys.has_any_api_key())

        # Test user with only anthropic key
        user_with_anthropic = replace(user_without_keys, anthropic_key = SecretStr("test_anthropic_key"))
        self.assertTrue(user_with_anthropic.has_any_api_key())
