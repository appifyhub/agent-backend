from unittest import TestCase

import stubs
from util.di_utils import di_for_tests

from api.gumroad_controller import GumroadController
from di.di import DI
from features.users.user import User
from util.config import config
from util.error_codes import UNAUTHORIZED_SELLER
from util.errors import AuthorizationError


class GumroadControllerTest(TestCase):

    di: DI
    user: User
    controller: GumroadController

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.user = self.di.user_repo.save(stubs.domain.user())
        self.controller = self.di.gumroad_controller
        product = stubs.domain.configured_product(id = "product-789")
        self.addCleanup(setattr, config, "products", config.products)
        config.products = {product.id: product}

    def test_handle_ping_success(self):
        self.addCleanup(setattr, config, "gumroad_seller_id_check", config.gumroad_seller_id_check)
        config.gumroad_seller_id_check = False
        payload = stubs.api.gumroad_ping_payload(url_params = {"user_id": self.user.id.hex})

        self.controller.handle_ping(payload)

        records = self.di.purchase_service.get_by_user(self.user.id)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].sale_id, payload.sale_id)
        self.assertEqual(records[0].seller_id, payload.seller_id)

    def test_handle_ping_with_seller_id_check_disabled(self):
        self.addCleanup(setattr, config, "gumroad_seller_id_check", config.gumroad_seller_id_check)
        config.gumroad_seller_id_check = False
        payload = stubs.api.gumroad_ping_payload(seller_id = "wrong-seller", url_params = {"user_id": self.user.id.hex})

        self.controller.handle_ping(payload)

        records = self.di.purchase_service.get_by_user(self.user.id)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].sale_id, payload.sale_id)
        self.assertEqual(records[0].seller_id, payload.seller_id)

    def test_handle_ping_with_seller_id_check_valid(self):
        self.addCleanup(setattr, config, "gumroad_seller_id_check", config.gumroad_seller_id_check)
        config.gumroad_seller_id_check = True
        self.addCleanup(setattr, config, "gumroad_seller_id", config.gumroad_seller_id)
        config.gumroad_seller_id = "seller-123"
        payload = stubs.api.gumroad_ping_payload(url_params = {"user_id": self.user.id.hex})

        self.controller.handle_ping(payload)

        records = self.di.purchase_service.get_by_user(self.user.id)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].sale_id, payload.sale_id)
        self.assertEqual(records[0].seller_id, payload.seller_id)

    def test_handle_ping_with_seller_id_check_invalid(self):
        self.addCleanup(setattr, config, "gumroad_seller_id_check", config.gumroad_seller_id_check)
        config.gumroad_seller_id_check = True
        self.addCleanup(setattr, config, "gumroad_seller_id", config.gumroad_seller_id)
        config.gumroad_seller_id = "seller-123"
        payload = stubs.api.gumroad_ping_payload(seller_id = "wrong-seller", url_params = {"user_id": self.user.id.hex})

        with self.assertRaises(AuthorizationError) as context:
            self.controller.handle_ping(payload)

        self.assertIn("Unauthorized seller ID", str(context.exception))
        self.assertIn("wrong-seller", str(context.exception))
        self.assertEqual(context.exception.error_code, UNAUTHORIZED_SELLER)
        self.assertEqual(self.di.purchase_service.get_by_user(self.user.id), [])
