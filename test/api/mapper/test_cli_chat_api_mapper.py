from unittest import TestCase

import stubs

from api.mapper.cli_chat_api_mapper import delivery_to_api, domain_to_api
from db.model.chat_config import ChatConfigDB


class CliChatApiMapperTest(TestCase):

    def test_domain_to_api_maps_every_field(self):
        chat = stubs.domain.chat_config(title = "Team Room", chat_type = ChatConfigDB.ChatType.whatsapp, is_private = False)

        result = domain_to_api(chat)

        self.assertEqual(result.chat_id, chat.chat_id.hex)
        self.assertEqual(result.platform, "whatsapp")
        self.assertEqual(result.title, "Team Room")
        self.assertFalse(result.is_private)

    def test_domain_to_api_keeps_a_missing_title(self):
        self.assertIsNone(domain_to_api(stubs.domain.chat_config(title = None)).title)

    def test_delivery_to_api_maps_the_chat_and_the_users_balance(self):
        chat = stubs.domain.chat_config(title = "Team Room", chat_type = ChatConfigDB.ChatType.telegram, is_private = True)
        user = stubs.domain.user(credit_balance = 42.5)

        result = delivery_to_api(chat, user)

        self.assertEqual(result.chat_id, chat.chat_id.hex)
        self.assertEqual(result.platform, "telegram")
        self.assertEqual(result.title, "Team Room")
        self.assertTrue(result.is_private)
        self.assertEqual(result.credit_balance, 42.5)
