import unittest
from datetime import date, datetime
from unittest.mock import Mock, patch
from uuid import UUID

from pydantic import SecretStr

from db.model.chat_message import ChatMessageDB
from db.model.price_alert import PriceAlertDB
from db.model.sponsorship import SponsorshipDB
from db.model.user import UserDB
from features.connect.profile_connect_service import ProfileConnectService
from features.users.user import User, generate_connect_key


class ProfileConnectServiceTest(unittest.TestCase):

    def setUp(self):
        self.mock_user_repo = Mock()
        self.mock_di = Mock()
        self.mock_di.user_repo = self.mock_user_repo
        self.mock_db = Mock()
        self.transaction_mock = Mock()
        self.transaction_mock.is_active = True

        def _commit_side_effect():
            self.transaction_mock.is_active = False

        def _rollback_side_effect():
            self.transaction_mock.is_active = False

        self.transaction_mock.commit.side_effect = _commit_side_effect
        self.transaction_mock.rollback.side_effect = _rollback_side_effect
        self.mock_db.begin.return_value = self.transaction_mock
        self.nested_transaction_mock = Mock()
        self.mock_db.begin_nested.return_value = self.nested_transaction_mock
        self.mock_db.in_transaction.return_value = False
        self.mock_db.rollback = Mock()
        self.query_calls = []

        def make_query(model):
            query = Mock(name = f"query_{getattr(model, '__name__', 'unknown')}")
            query.model = model
            query.filter_calls = []
            query.update_calls = []
            query.delete_calls = []

            def filter_side_effect(*conditions):
                query.filter_calls.append(conditions)
                return query

            def update_side_effect(values, **kwargs):
                query.update_calls.append((values, kwargs))
                return 1

            def delete_side_effect(**kwargs):
                query.delete_calls.append(kwargs)
                return 1

            query.filter.side_effect = filter_side_effect
            query.update.side_effect = update_side_effect
            query.delete.side_effect = delete_side_effect
            self.query_calls.append(query)
            return query

        self.mock_db.query.side_effect = make_query
        self.mock_di.db = self.mock_db
        self.service = ProfileConnectService(self.mock_di)

    def _assert_filter_conditions(self, query_mock: Mock, expected_conditions: list):
        self.assertEqual(len(query_mock.filter_calls), 1)
        actual_conditions = query_mock.filter_calls[0]
        self.assertEqual(len(actual_conditions), len(expected_conditions))
        for actual, expected in zip(actual_conditions, expected_conditions):
            self.assertTrue(actual.compare(expected))

    def _assert_single_update(self, query_mock: Mock, expected_values: dict):
        self.assertEqual(len(query_mock.update_calls), 1)
        values, kwargs = query_mock.update_calls[0]
        self.assertEqual(values, expected_values)
        self.assertEqual(kwargs, {"synchronize_session": False})

    def _assert_single_delete(self, query_mock: Mock):
        self.assertEqual(len(query_mock.delete_calls), 1)
        self.assertEqual(query_mock.delete_calls[0], {"synchronize_session": False})

    def _assert_migration_queries(self, survivor_id: UUID, casualty_id: UUID):
        chat_query = next(query for query in self.query_calls if query.model is ChatMessageDB)
        self._assert_filter_conditions(chat_query, [ChatMessageDB.author_id == casualty_id])
        self._assert_single_update(chat_query, {ChatMessageDB.author_id: survivor_id})

        price_query = next(query for query in self.query_calls if query.model is PriceAlertDB)
        self._assert_filter_conditions(price_query, [PriceAlertDB.owner_id == casualty_id])
        self._assert_single_update(price_query, {PriceAlertDB.owner_id: survivor_id})

        sponsorship_queries = [query for query in self.query_calls if query.model is SponsorshipDB]
        self.assertEqual(len(sponsorship_queries), 4)

        self._assert_filter_conditions(
            sponsorship_queries[0],
            [
                SponsorshipDB.sponsor_id == casualty_id,
                SponsorshipDB.receiver_id == survivor_id,
            ],
        )
        self._assert_single_delete(sponsorship_queries[0])

        self._assert_filter_conditions(
            sponsorship_queries[1],
            [SponsorshipDB.sponsor_id == casualty_id],
        )
        self._assert_single_update(
            sponsorship_queries[1],
            {SponsorshipDB.sponsor_id: survivor_id},
        )

        self._assert_filter_conditions(
            sponsorship_queries[2],
            [
                SponsorshipDB.sponsor_id == survivor_id,
                SponsorshipDB.receiver_id == casualty_id,
            ],
        )
        self._assert_single_delete(sponsorship_queries[2])

        self._assert_filter_conditions(
            sponsorship_queries[3],
            [SponsorshipDB.receiver_id == casualty_id],
        )
        self._assert_single_update(
            sponsorship_queries[3],
            {SponsorshipDB.receiver_id: survivor_id},
        )

    def _validate_connection(self, requester: User, target: User) -> str | None:
        validate_connection = getattr(
            self.service,
            "_ProfileConnectService__validate_connection",
        )
        return validate_connection(requester, target)

    def _classify_profiles(self, user1: User, user2: User) -> tuple[User, User]:
        classify_profiles = getattr(
            self.service,
            "_ProfileConnectService__classify_profiles",
        )
        return classify_profiles(user1, user2)

    def _merge_user_data(self, survivor: User, casualty: User) -> User:
        merge_user_data = getattr(
            self.service,
            "_ProfileConnectService__merge_user_data",
        )
        return merge_user_data(survivor, casualty)

    def _migrate_dependent_entities(self, survivor_id: UUID, casualty_id: UUID) -> None:
        migrate = getattr(
            self.service,
            "_ProfileConnectService__migrate_dependent_entities",
        )
        migrate(survivor_id, casualty_id)

    def test_generate_connect_key(self):
        key = generate_connect_key()

        self.assertIsNotNone(key)
        self.assertEqual(len(key), 14)  # XXXX-XXXX-XXXX format
        self.assertEqual(key[4], "-")
        self.assertEqual(key[9], "-")
        self.assertTrue(key.replace("-", "").isupper())
        self.assertTrue(key.replace("-", "").isalnum())

    def test_validate_connection_same_user(self):
        user1 = User(
            id = UUID(int = 1),
            full_name = "Test User",
            telegram_user_id = 123,
            connect_key = "KEY1-KEY1-KEY1",
            open_ai_key = SecretStr("key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        result = self._validate_connection(user1, user1)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("Cannot connect a profile to itself", result)

    def test_validate_connection_both_telegram_only(self):
        user1 = User(
            id = UUID(int = 1),
            full_name = "User 1",
            telegram_user_id = 123,
            whatsapp_user_id = None,
            connect_key = "KEY1-KEY1-KEY1",
            open_ai_key = SecretStr("key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        user2 = User(
            id = UUID(int = 2),
            full_name = "User 2",
            telegram_user_id = 456,
            whatsapp_user_id = None,
            connect_key = "KEY2-KEY2-KEY2",
            open_ai_key = SecretStr("key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        result = self._validate_connection(user1, user2)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("Telegram only", result)

    def test_validate_connection_both_whatsapp_only(self):
        user1 = User(
            id = UUID(int = 1),
            full_name = "User 1",
            telegram_user_id = None,
            whatsapp_user_id = "123",
            connect_key = "KEY1-KEY1-KEY1",
            open_ai_key = SecretStr("key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        user2 = User(
            id = UUID(int = 2),
            full_name = "User 2",
            telegram_user_id = None,
            whatsapp_user_id = "456",
            connect_key = "KEY2-KEY2-KEY2",
            open_ai_key = SecretStr("key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        result = self._validate_connection(user1, user2)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("WhatsApp only", result)

    def test_validate_connection_different_platforms_valid(self):
        user1 = User(
            id = UUID(int = 1),
            full_name = "User 1",
            telegram_user_id = 123,
            whatsapp_user_id = None,
            connect_key = "KEY1-KEY1-KEY1",
            open_ai_key = SecretStr("key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        user2 = User(
            id = UUID(int = 2),
            full_name = "User 2",
            telegram_user_id = None,
            whatsapp_user_id = "456",
            connect_key = "KEY2-KEY2-KEY2",
            open_ai_key = SecretStr("key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        result = self._validate_connection(user1, user2)

        self.assertIsNone(result)

    def test_classify_profiles_older_wins(self):
        older_date = datetime(2023, 1, 1).date()
        newer_date = datetime(2024, 1, 1).date()

        user1 = User(
            id = UUID(int = 1),
            full_name = "Older User",
            connect_key = "KEY1-KEY1-KEY1",
            open_ai_key = SecretStr("key"),
            group = UserDB.Group.standard,
            created_at = older_date,
        )
        user2 = User(
            id = UUID(int = 2),
            full_name = "Newer User",
            connect_key = "KEY2-KEY2-KEY2",
            open_ai_key = SecretStr("key"),
            group = UserDB.Group.standard,
            created_at = newer_date,
        )

        survivor, deleted = self._classify_profiles(user1, user2)

        self.assertEqual(survivor.id, user1.id)
        self.assertEqual(deleted.id, user2.id)

    def test_merge_user_data_prefer_non_null(self):
        survivor = User(
            id = UUID(int = 1),
            full_name = "Survivor",
            telegram_user_id = 123,
            whatsapp_user_id = None,
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = True,
            connect_key = "KEY1-KEY1-KEY1",
            open_ai_key = SecretStr("survivor-key"),
            anthropic_key = None,
            x_key = None,
            x_ai_key = None,
            credit_balance = 100.0,
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        deleted = User(
            id = UUID(int = 2),
            full_name = None,
            telegram_user_id = None,
            whatsapp_user_id = "456",
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = False,
            connect_key = "KEY2-KEY2-KEY2",
            open_ai_key = None,
            anthropic_key = SecretStr("deleted-key"),
            x_key = SecretStr("deleted-x-key"),
            x_ai_key = SecretStr("deleted-x-ai-key"),
            credit_balance = 50.0,
            group = UserDB.Group.developer,
            created_at = datetime.now().date(),
        )

        merged = self._merge_user_data(survivor, deleted)

        self.assertEqual(merged.full_name, "Survivor")  # Survivor has value
        self.assertEqual(merged.telegram_user_id, 123)  # Survivor has value
        self.assertEqual(merged.whatsapp_user_id, "456")  # Deleted has value, survivor doesn't
        self.assertEqual(merged.open_ai_key, survivor.open_ai_key)  # Survivor has value
        self.assertEqual(merged.anthropic_key, deleted.anthropic_key)  # Deleted has value, survivor doesn't
        self.assertEqual(merged.x_key, deleted.x_key)  # Deleted has value, survivor doesn't
        self.assertEqual(merged.x_ai_key, deleted.x_ai_key)  # Deleted has value, survivor doesn't
        self.assertEqual(merged.credit_balance, 150.0)  # Credit balances are summed
        self.assertEqual(merged.group, UserDB.Group.developer)  # Developer group takes precedence
        self.assertTrue(merged.are_policies_accepted)
        self.assertFalse(merged.is_on_waitlist)
        self.assertFalse(merged.is_invited_to_start)

    def test_merge_user_data_resets_invite_when_merged_user_is_active(self):
        survivor = User(
            id = UUID(int = 1),
            full_name = "Survivor",
            telegram_user_id = 123,
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = True,
            connect_key = "KEY1-KEY1-KEY1",
            open_ai_key = SecretStr("survivor-key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        casualty = User(
            id = UUID(int = 2),
            full_name = "Casualty",
            whatsapp_user_id = "456",
            is_on_waitlist = True,
            is_invited_to_start = True,
            are_policies_accepted = False,
            connect_key = "KEY2-KEY2-KEY2",
            open_ai_key = None,
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        merged = self._merge_user_data(survivor, casualty)
        self.assertFalse(merged.is_on_waitlist)
        self.assertFalse(merged.is_invited_to_start)
        self.assertTrue(merged.are_policies_accepted)

    def test_migrate_dependent_entities_moves_related_records(self):
        survivor_id = UUID(int = 1)
        casualty_id = UUID(int = 2)

        self._migrate_dependent_entities(survivor_id, casualty_id)

        self.assertEqual(len(self.query_calls), 6)
        self._assert_migration_queries(survivor_id, casualty_id)

    def test_connect_profiles_invalid_key(self):
        requester = User(
            id = UUID(int = 1),
            full_name = "Requester",
            telegram_user_id = 123,
            connect_key = "KEY1-KEY1-KEY1",
            open_ai_key = SecretStr("key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.mock_user_repo.get_by_connect_key.return_value = None

        result, message = self.service.connect_profiles(requester, "INVALID-KEY-HERE")

        self.assertEqual(result, ProfileConnectService.Result.failure)
        self.assertIn("Invalid connect key", message)

    @patch("features.connect.profile_connect_service.generate_connect_key", return_value = "ABCD-EFGH-IJKL")
    def test_connect_profiles_success(self, mock_generate: Mock):
        survivor_user = User(
            id = UUID(int = 1),
            full_name = "Survivor",
            telegram_user_id = 123,
            connect_key = "SURV-KEY-AAAA",
            group = UserDB.Group.standard,
            created_at = date(2023, 1, 1),
        )
        casualty_id = UUID(int = 2)
        target_connect_key = "CAST-KEY-BBBB"
        casualty = User(
            id = casualty_id,
            full_name = "Casualty",
            whatsapp_user_id = "wa-456",
            connect_key = target_connect_key,
            group = UserDB.Group.developer,
            created_at = date(2024, 1, 1),
            credit_balance = 0.0,
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = True,
        )

        self.mock_user_repo.get_by_connect_key.return_value = casualty
        self.mock_user_repo.save.side_effect = lambda user, commit = True: user
        self.mock_user_repo.delete.return_value = casualty

        result, message = self.service.connect_profiles(survivor_user, target_connect_key)

        self.assertEqual(result, ProfileConnectService.Result.success)
        self.assertEqual(
            message,
            "Profiles connected successfully! Data was merged and you have a new connect key on the new joint profile.",
        )
        self.assertEqual(self.mock_user_repo.delete.call_count, 1)
        self.assertEqual(self.mock_user_repo.save.call_count, 2)
        first_saved_user = self.mock_user_repo.save.call_args_list[0].args[0]
        self.assertIsInstance(first_saved_user, User)
        self.assertEqual(first_saved_user.id, survivor_user.id)
        self.assertEqual(first_saved_user.whatsapp_user_id, casualty.whatsapp_user_id)
        self.assertEqual(first_saved_user.connect_key, survivor_user.connect_key)
        second_saved_user = self.mock_user_repo.save.call_args_list[1].args[0]
        self.assertIsInstance(second_saved_user, User)
        self.assertEqual(second_saved_user.connect_key, "ABCD-EFGH-IJKL")
        self.mock_user_repo.delete.assert_called_once_with(casualty_id, commit = False)
        first_save_call = self.mock_user_repo.save.call_args_list[0]
        self.assertEqual(first_save_call.kwargs, {"commit": False})
        second_save_call = self.mock_user_repo.save.call_args_list[1]
        self.assertEqual(second_save_call.kwargs, {"commit": False})
        mock_generate.assert_called_once()
        self.assertGreaterEqual(len(self.query_calls), 6)
        self._assert_migration_queries(survivor_user.id, casualty_id)

    @patch("features.connect.profile_connect_service.generate_connect_key", return_value = "NEW-KEY-9999")
    def test_regenerate_connect_key(self, mock_generate: Mock):
        user = User(
            id = UUID(int = 1),
            full_name = "User",
            telegram_user_id = 123,
            connect_key = "OLD-KEY-1111",
            group = UserDB.Group.standard,
            created_at = date(2023, 1, 1),
        )
        updated_user = User(
            id = user.id,
            full_name = user.full_name,
            telegram_user_id = user.telegram_user_id,
            connect_key = "NEW-KEY-9999",
            group = UserDB.Group.standard,
            created_at = user.created_at,
            credit_balance = 0.0,
            is_on_waitlist = False,
            is_invited_to_start = False,
            are_policies_accepted = True,
        )
        self.mock_user_repo.save.return_value = updated_user

        new_key = self.service.regenerate_connect_key(user)

        self.assertEqual(new_key, "NEW-KEY-9999")
        self.mock_user_repo.save.assert_called_once()
        saved_payload = self.mock_user_repo.save.call_args.args[0]
        self.assertIsInstance(saved_payload, User)
        self.assertEqual(saved_payload.connect_key, "NEW-KEY-9999")
        mock_generate.assert_called_once()
