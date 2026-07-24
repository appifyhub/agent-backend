import unittest
from dataclasses import replace
from uuid import UUID, uuid4

from db.sql_util import SQLUtil
from pydantic import SecretStr

from db.model.user import UserDB
from features.users.user import User
from features.users.user_remote_data import UserRemoteData
from features.users.user_repo import UserRepository
from util.errors import NotFoundError


class UserRepositoryTest(unittest.TestCase):

    sql: SQLUtil
    repo: UserRepository

    def setUp(self):
        self.sql = SQLUtil()
        self.repo = self.sql.user_repo()

    def tearDown(self):
        self.sql.end_session()

    def test_save_creates_user_and_generates_id_created_at_and_connect_key(self):
        user = User(full_name = "Test User")

        result = self.repo.save(user)

        self.assertIsNotNone(result.id)
        self.assertIsNotNone(result.created_at)
        self.assertIsNotNone(result.connect_key)
        self.assertEqual(result.full_name, "Test User")
        self.assertEqual(result.credit_balance, 0.0)
        self.assertEqual(result.group, UserDB.Group.standard)

    def test_save_persists_secret_and_tool_choice_fields(self):
        user = self.__user(
            connect_key = "SECRET-KEY-0001",
            about_me = SecretStr("about"),
            custom_prompt = SecretStr("prompt"),
            whatsapp_phone_number = SecretStr("15550001111"),
            open_ai_key = SecretStr("open-ai"),
            anthropic_key = SecretStr("anthropic"),
            google_ai_key = SecretStr("google"),
            perplexity_key = SecretStr("perplexity"),
            replicate_key = SecretStr("replicate"),
            rapid_api_key = SecretStr("rapid"),
            coinmarketcap_key = SecretStr("coinmarketcap"),
            twelve_data_api_key = SecretStr("twelve-data"),
            x_key = SecretStr("x"),
            x_ai_key = SecretStr("x-ai"),
            tool_choice_api_stock_quote = "quote",
        )

        result = self.repo.save(user)
        fetched = self.repo.get(result.id)

        self.assertEqual(fetched.about_me.get_secret_value(), "about")
        self.assertEqual(fetched.custom_prompt.get_secret_value(), "prompt")
        self.assertEqual(fetched.whatsapp_phone_number.get_secret_value(), "15550001111")
        self.assertEqual(fetched.open_ai_key.get_secret_value(), "open-ai")
        self.assertEqual(fetched.anthropic_key.get_secret_value(), "anthropic")
        self.assertEqual(fetched.google_ai_key.get_secret_value(), "google")
        self.assertEqual(fetched.perplexity_key.get_secret_value(), "perplexity")
        self.assertEqual(fetched.replicate_key.get_secret_value(), "replicate")
        self.assertEqual(fetched.rapid_api_key.get_secret_value(), "rapid")
        self.assertEqual(fetched.coinmarketcap_key.get_secret_value(), "coinmarketcap")
        self.assertEqual(fetched.twelve_data_api_key.get_secret_value(), "twelve-data")
        self.assertEqual(fetched.x_key.get_secret_value(), "x")
        self.assertEqual(fetched.x_ai_key.get_secret_value(), "x-ai")
        self.assertEqual(fetched.tool_choice_api_stock_quote, "quote")

    def test_get_returns_saved_user(self):
        created = self.repo.save(self.__user(connect_key = "GET-USER-0001"))

        result = self.repo.get(created.id)

        self.assertIsNotNone(result)
        self.assertEqual(result.id, created.id)
        self.assertEqual(result.connect_key, created.connect_key)
        self.assertEqual(result.full_name, created.full_name)

    def test_get_returns_none_when_missing(self):
        result = self.repo.get(uuid4())

        self.assertIsNone(result)

    def test_get_all_and_count(self):
        first = self.repo.save(self.__user(connect_key = "GET-ALL-0001"))
        second = self.repo.save(self.__user(connect_key = "GET-ALL-0002"))

        results = self.repo.get_all()

        self.assertEqual(self.repo.count(), 2)
        self.assertEqual([result.id for result in results], [first.id, second.id])

    def test_platform_lookup_methods(self):
        user = self.repo.save(self.__user(
            connect_key = "LOOKUP-KEY-01",
            telegram_username = "lookup-telegram",
            telegram_user_id = 1001,
            whatsapp_user_id = "lookup-wa",
            whatsapp_phone_number = SecretStr("15550002222"),
        ))

        self.assertEqual(self.repo.get_by_telegram_user_id(1001).id, user.id)
        self.assertEqual(self.repo.get_by_telegram_username("lookup-telegram").id, user.id)
        self.assertEqual(self.repo.get_by_whatsapp_user_id("lookup-wa").id, user.id)
        self.assertEqual(self.repo.get_by_whatsapp_phone_number("15550002222").id, user.id)
        self.assertEqual(self.repo.get_by_connect_key("LOOKUP-KEY-01").id, user.id)

    def test_get_by_remote_data_prefers_telegram_user_id_then_username(self):
        by_id = self.repo.save(self.__user(
            connect_key = "REMOTE-TG-001",
            telegram_username = "old-username",
            telegram_user_id = 2001,
        ))
        self.repo.save(self.__user(
            connect_key = "REMOTE-TG-002",
            telegram_username = "remote-username",
            telegram_user_id = 2002,
        ))
        remote_data = UserRemoteData(
            telegram_user_id = 2001,
            telegram_username = "remote-username",
        )

        result = self.repo.get_by_remote_data(remote_data)

        self.assertEqual(result.id, by_id.id)

    def test_get_by_remote_data_falls_back_to_whatsapp_phone_number(self):
        user = self.repo.save(self.__user(
            connect_key = "REMOTE-WA-001",
            whatsapp_user_id = None,
            whatsapp_phone_number = SecretStr("15550003333"),
        ))
        remote_data = UserRemoteData(
            whatsapp_user_id = None,
            whatsapp_phone_number = SecretStr("15550003333"),
        )

        result = self.repo.get_by_remote_data(remote_data)

        self.assertEqual(result.id, user.id)

    def test_save_updates_existing_user_and_preserves_id_and_created_at(self):
        created = self.repo.save(self.__user(
            connect_key = "UPDATE-KEY-001",
            full_name = "Original",
            about_me = SecretStr("about"),
        ))
        replacement = replace(
            created,
            full_name = "Updated",
            about_me = None,
            telegram_username = "updated-telegram",
            credit_balance = 500.0,
            group = UserDB.Group.developer,
        )

        result = self.repo.save(replacement)

        self.assertEqual(result.id, created.id)
        self.assertEqual(result.created_at, created.created_at)
        self.assertEqual(result.connect_key, "UPDATE-KEY-001")
        self.assertEqual(result.full_name, "Updated")
        self.assertIsNone(result.about_me)
        self.assertEqual(result.telegram_username, "updated-telegram")
        self.assertEqual(result.credit_balance, 500.0)
        self.assertEqual(result.group, UserDB.Group.developer)

    def test_save_with_unknown_id_inserts_user_with_supplied_id(self):
        user_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        result = self.repo.save(self.__user(id = user_id, connect_key = "INSERT-ID-001"))

        self.assertEqual(result.id, user_id)
        self.assertIsNotNone(result.created_at)
        self.assertEqual(self.repo.get(user_id).connect_key, "INSERT-ID-001")

    def test_delete_user(self):
        created = self.repo.save(self.__user(connect_key = "DELETE-KEY-01"))

        result = self.repo.delete(created.id)

        self.assertIsNotNone(result)
        self.assertEqual(result.id, created.id)
        self.assertIsNone(self.repo.get(created.id))

    def test_delete_returns_none_when_missing(self):
        result = self.repo.delete(uuid4())

        self.assertIsNone(result)

    def test_update_locked_updates_user(self):
        created = self.repo.save(self.__user(connect_key = "LOCKED-KEY-01", credit_balance = 10.0))

        result = self.repo.update_locked(
            created.id,
            lambda user: replace(user, credit_balance = user.credit_balance + 15.0),
        )

        self.assertEqual(result.credit_balance, 25.0)
        self.assertEqual(self.repo.get(created.id).credit_balance, 25.0)

    def test_update_locked_raises_when_missing(self):
        with self.assertRaises(NotFoundError):
            self.repo.update_locked(uuid4(), lambda user: user)

    def test_update_locked_pair_updates_users_in_requested_order(self):
        first = self.repo.save(self.__user(connect_key = "PAIR-KEY-001", credit_balance = 100.0))
        second = self.repo.save(self.__user(connect_key = "PAIR-KEY-002", credit_balance = 25.0))
        seen_ids: list[UUID] = []

        def transfer(sender: User, receiver: User) -> tuple[User, User]:
            seen_ids.extend([sender.id, receiver.id])
            return (
                replace(sender, credit_balance = sender.credit_balance - 40.0),
                replace(receiver, credit_balance = receiver.credit_balance + 40.0),
            )

        updated_second, updated_first = self.repo.update_locked_pair(second.id, first.id, transfer)

        self.assertEqual(seen_ids, [second.id, first.id])
        self.assertEqual(updated_second.credit_balance, -15.0)
        self.assertEqual(updated_first.credit_balance, 140.0)
        self.assertEqual(self.repo.get(second.id).credit_balance, -15.0)
        self.assertEqual(self.repo.get(first.id).credit_balance, 140.0)

    def test_update_locked_pair_raises_when_missing(self):
        existing = self.repo.save(self.__user(connect_key = "PAIR-MISSING"))

        with self.assertRaises(NotFoundError):
            self.repo.update_locked_pair(existing.id, uuid4(), lambda first, second: (first, second))

    def __user(
        self,
        connect_key: str,
        id: UUID | None = None,
        full_name: str | None = "Test User",
        about_me: SecretStr | None = None,
        custom_prompt: SecretStr | None = None,
        telegram_username: str | None = None,
        telegram_chat_id: str | None = None,
        telegram_user_id: int | None = None,
        whatsapp_user_id: str | None = None,
        whatsapp_phone_number: SecretStr | None = None,
        open_ai_key: SecretStr | None = None,
        anthropic_key: SecretStr | None = None,
        google_ai_key: SecretStr | None = None,
        perplexity_key: SecretStr | None = None,
        replicate_key: SecretStr | None = None,
        rapid_api_key: SecretStr | None = None,
        coinmarketcap_key: SecretStr | None = None,
        twelve_data_api_key: SecretStr | None = None,
        x_key: SecretStr | None = None,
        x_ai_key: SecretStr | None = None,
        tool_choice_api_stock_quote: str | None = None,
        credit_balance: float = 0.0,
        group: UserDB.Group = UserDB.Group.standard,
    ) -> User:
        return User(
            id = id,
            full_name = full_name,
            about_me = about_me,
            custom_prompt = custom_prompt,
            telegram_username = telegram_username,
            telegram_chat_id = telegram_chat_id,
            telegram_user_id = telegram_user_id,
            whatsapp_user_id = whatsapp_user_id,
            whatsapp_phone_number = whatsapp_phone_number,
            open_ai_key = open_ai_key,
            anthropic_key = anthropic_key,
            google_ai_key = google_ai_key,
            perplexity_key = perplexity_key,
            replicate_key = replicate_key,
            rapid_api_key = rapid_api_key,
            coinmarketcap_key = coinmarketcap_key,
            twelve_data_api_key = twelve_data_api_key,
            x_key = x_key,
            x_ai_key = x_ai_key,
            tool_choice_api_stock_quote = tool_choice_api_stock_quote,
            credit_balance = credit_balance,
            connect_key = connect_key,
            group = group,
        )
