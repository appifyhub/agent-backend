import unittest
from unittest.mock import MagicMock, patch

import stubs

from api.gumroad_controller import GumroadController
from di.di import DI
from features.accounting.purchases.purchase_service import PurchaseService
from util.errors import AuthorizationError


class GumroadControllerTest(unittest.TestCase):

    mock_purchase_service: PurchaseService
    controller: GumroadController

    def setUp(self):
        mock_di = MagicMock(spec = DI)
        self.mock_purchase_service = MagicMock(spec = PurchaseService)
        mock_di.purchase_service = self.mock_purchase_service
        self.controller = GumroadController(mock_di)

    @patch("api.gumroad_controller.config")
    def test_handle_ping_success(self, mock_config):
        mock_config.gumroad_seller_id_check = False
        payload = stubs.api.gumroad_ping_payload()

        self.controller.handle_ping(payload)

        self.mock_purchase_service.record_purchase.assert_called_once_with(payload)

    @patch("api.gumroad_controller.config")
    def test_handle_ping_with_seller_id_check_disabled(self, mock_config):
        mock_config.gumroad_seller_id_check = False
        payload = stubs.api.gumroad_ping_payload(seller_id = "wrong-seller")

        self.controller.handle_ping(payload)

        self.mock_purchase_service.record_purchase.assert_called_once_with(payload)

    @patch("api.gumroad_controller.config")
    def test_handle_ping_with_seller_id_check_valid(self, mock_config):
        mock_config.gumroad_seller_id_check = True
        mock_config.gumroad_seller_id = "seller-123"
        payload = stubs.api.gumroad_ping_payload()

        self.controller.handle_ping(payload)

        self.mock_purchase_service.record_purchase.assert_called_once_with(payload)

    @patch("api.gumroad_controller.config")
    def test_handle_ping_with_seller_id_check_invalid(self, mock_config):
        mock_config.gumroad_seller_id_check = True
        mock_config.gumroad_seller_id = "seller-123"
        payload = stubs.api.gumroad_ping_payload(seller_id = "wrong-seller")

        with self.assertRaises(AuthorizationError) as context:
            self.controller.handle_ping(payload)

        self.assertIn("Unauthorized seller ID", str(context.exception))
        self.assertIn("wrong-seller", str(context.exception))
        self.mock_purchase_service.record_purchase.assert_not_called()
