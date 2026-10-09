from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from features.integrations.delivery.messaging_price_service import MessagingPriceService
from util.config import config


class MessagingPriceServiceTest(TestCase):

    service: MessagingPriceService

    def setUp(self):
        di = self.enterContext(di_for_tests())
        directory = self.enterContext(TemporaryDirectory())
        path = Path(directory) / "platform-pricing.yaml"
        path.write_text("""\
platforms:
  telegram:
    markets:
      global: {default: true, categories: {service: "0"}}
  whatsapp:
    markets:
      north_america: {prefixes: ["1"], categories: {service: "0.4"}}
      dominican_republic: {prefixes: ["1809"], categories: {service: "1.2"}}
      broader_region: {prefixes: ["18"], categories: {service: "0.8"}}
      serbia: {prefixes: ["381"], categories: {service: "1.01", utility: "1.20"}}
      other: {default: true, categories: {service: "2.0"}}
""")
        self.addCleanup(setattr, config, "integration_delivery_pricing_config_path", config.integration_delivery_pricing_config_path)  # ruff: ignore[line-too-long]
        config.integration_delivery_pricing_config_path = str(path)
        self.service = di.messaging_price_service

    def test_most_specific_prefix_wins_over_first_and_last_matches(self):
        cost = self.service.get(ChatConfigDB.ChatType.whatsapp, "+1 (809) 555-0100")

        self.assertEqual(cost, 1.2)

    def test_free_platform_price_is_not_replaced_by_a_matching_phone_prefix(self):
        cost = self.service.get(ChatConfigDB.ChatType.telegram, "18095550100")

        self.assertEqual(cost, 0)

    def test_unknown_recipient_prefix_uses_the_default_market(self):
        cost = self.service.get(ChatConfigDB.ChatType.whatsapp, "9995550100")

        self.assertEqual(cost, 2.0)

    def test_category_price_rounds_up_without_increasing_an_exact_tenth(self):
        for category, expected in (("service", 1.1), ("utility", 1.2)):
            with self.subTest(category = category):
                cost = self.service.get(ChatConfigDB.ChatType.whatsapp, "+38164123456", category)

                self.assertEqual(cost, expected)

    def test_missing_platform_or_category_does_not_become_a_free_price(self):
        with self.assertRaises(KeyError):
            self.service.get(ChatConfigDB.ChatType.github, "18095550100")
        with self.assertRaises(KeyError):
            self.service.get(ChatConfigDB.ChatType.whatsapp, "18095550100", "marketing")
