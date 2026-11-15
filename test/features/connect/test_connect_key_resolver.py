from unittest import TestCase

import stubs
from util.di_utils import di_for_tests

from di.di import DI
from features.connect.connect_key_resolver import require_user_by_connect_key
from features.users.user import User
from util.error_codes import CONNECT_KEY_NOT_FOUND
from util.errors import NotFoundError


class ConnectKeyResolverTest(TestCase):

    di: DI
    user: User

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user(connect_key = "RESOLVE-KEY-01"))

    def test_returns_the_owner_of_the_key_forgiving_its_formatting(self):
        for connect_key in ("RESOLVE-KEY-01", "resolve-key-01", "  resolve-key-01  "):
            with self.subTest(connect_key = connect_key):
                self.assertEqual(require_user_by_connect_key(connect_key, self.di.db), self.user)

    def test_unknown_key_is_rejected_without_echoing_it(self):
        with self.assertRaises(NotFoundError) as context:
            require_user_by_connect_key("UNKNOWN-KEY-0001", self.di.db)

        self.assertEqual(context.exception.error_code, CONNECT_KEY_NOT_FOUND)
        self.assertNotIn("UNKNOWN-KEY-0001", str(context.exception))
