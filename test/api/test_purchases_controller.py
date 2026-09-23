import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, PropertyMock
from uuid import UUID

import stubs

from api.authorization_service import AuthorizationService
from api.purchases_controller import PurchasesController
from di.di import DI
from features.accounting.purchases.purchase_service import PurchaseService
from util.error_codes import NOT_TARGET_USER
from util.errors import AuthorizationError, ValidationError


class PurchasesControllerTest(unittest.TestCase):

    mock_di: DI
    mock_authorization_service: AuthorizationService
    mock_purchase_service: PurchaseService

    def setUp(self):
        self.mock_di = MagicMock(spec = DI)

        self.mock_authorization_service = MagicMock(spec = AuthorizationService)
        self.mock_di.authorization_service = self.mock_authorization_service

        self.mock_purchase_service = MagicMock(spec = PurchaseService)
        self.mock_di.purchase_service = self.mock_purchase_service

    def test_fetch_purchase_records_success(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        records = [stubs.domain.purchase_record(user_id = invoker_user.id)]
        self.mock_purchase_service.get_by_user.return_value = records

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_records(invoker_user.id.hex)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user_id, invoker_user.id)
        self.mock_authorization_service.authorize_for_user.assert_called_once_with(
            invoker_user, invoker_user.id.hex,
        )
        self.mock_purchase_service.get_by_user.assert_called_once()

    def test_fetch_purchase_records_with_pagination(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        records = [
            stubs.domain.purchase_record(user_id = invoker_user.id, price = i)
            for i in range(5)
        ]
        self.mock_purchase_service.get_by_user.return_value = records[2:4]

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_records(
            invoker_user.id.hex,
            skip = 2,
            limit = 2,
        )

        self.assertEqual(len(result), 2)
        self.mock_purchase_service.get_by_user.assert_called_once_with(
            invoker_user.id,
            skip = 2,
            limit = 2,
            start_date = None,
            end_date = None,
            product_id = None,
        )

    def test_fetch_purchase_records_with_date_filters(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        start = datetime(2024, 1, 1, tzinfo = timezone.utc)
        end = datetime(2024, 12, 31, tzinfo = timezone.utc)
        records = [stubs.domain.purchase_record(user_id = invoker_user.id)]
        self.mock_purchase_service.get_by_user.return_value = records

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_records(
            invoker_user.id.hex,
            start_date = start,
            end_date = end,
        )

        self.assertEqual(len(result), 1)
        self.mock_purchase_service.get_by_user.assert_called_once_with(
            invoker_user.id,
            skip = 0,
            limit = 50,
            start_date = start,
            end_date = end,
            product_id = None,
        )

    def test_fetch_purchase_records_with_product_filter(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        records = [stubs.domain.purchase_record(user_id = invoker_user.id)]
        self.mock_purchase_service.get_by_user.return_value = records

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_records(
            invoker_user.id.hex,
            product_id = "product-123",
        )

        self.assertEqual(len(result), 1)
        self.mock_purchase_service.get_by_user.assert_called_once_with(
            invoker_user.id,
            skip = 0,
            limit = 50,
            start_date = None,
            end_date = None,
            product_id = "product-123",
        )

    def test_fetch_purchase_records_empty_result(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        self.mock_purchase_service.get_by_user.return_value = []

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_records(invoker_user.id.hex)

        self.assertEqual(len(result), 0)

    def test_fetch_purchase_records_limit_exceeds_maximum(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        controller = PurchasesController(self.mock_di)

        with self.assertRaises(ValidationError) as context:
            controller.fetch_purchase_records(invoker_user.id.hex, limit = 101)

        self.assertIn("limit cannot exceed 100", str(context.exception))
        self.mock_authorization_service.authorize_for_user.assert_not_called()
        self.mock_purchase_service.get_by_user.assert_not_called()

    def test_fetch_purchase_records_authorization_failure(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        target_user = stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)

        self.mock_authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", NOT_TARGET_USER)

        controller = PurchasesController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.fetch_purchase_records(target_user.id.hex)

        self.assertIn("Unauthorized", str(context.exception))
        self.mock_purchase_service.get_by_user.assert_not_called()

    def test_fetch_purchase_aggregates_success(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        product_stats = stubs.domain.product_aggregate_stats(
            record_count = 3,
            total_cost_cents = 12_345,
            total_net_cost_cents = 11_111,
        )
        product_info = stubs.domain.product_info(
            id = "scenario-product",
            name = "Scenario Product",
        )
        aggregates = stubs.domain.purchase_aggregates(
            total_purchase_count = 3,
            total_cost_cents = 12_345,
            total_net_cost_cents = 11_111,
            by_product = {"scenario-product": product_stats},
            all_products_used = [product_info],
        )
        self.mock_purchase_service.get_aggregates_by_user.return_value = aggregates

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_aggregates(invoker_user.id.hex)

        self.assertEqual(result.total_purchase_count, aggregates.total_purchase_count)
        self.assertEqual(result.total_cost_cents, aggregates.total_cost_cents)
        self.assertEqual(result.total_net_cost_cents, aggregates.total_net_cost_cents)
        self.assertIs(result.by_product["scenario-product"], product_stats)
        self.assertIs(result.all_products_used[0], product_info)
        self.mock_authorization_service.authorize_for_user.assert_called_once_with(
            invoker_user, invoker_user.id.hex,
        )

    def test_fetch_purchase_aggregates_with_date_filters(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        start = datetime(2024, 1, 1, tzinfo = timezone.utc)
        end = datetime(2024, 12, 31, tzinfo = timezone.utc)
        aggregates = stubs.domain.purchase_aggregates(
            total_purchase_count = 0,
            total_cost_cents = 0,
            total_net_cost_cents = 0,
            by_product = {},
            all_products_used = [],
        )
        self.mock_purchase_service.get_aggregates_by_user.return_value = aggregates

        controller = PurchasesController(self.mock_di)
        controller.fetch_purchase_aggregates(
            invoker_user.id.hex,
            start_date = start,
            end_date = end,
        )

        self.mock_purchase_service.get_aggregates_by_user.assert_called_once_with(
            invoker_user.id,
            start_date = start,
            end_date = end,
            product_id = None,
        )

    def test_fetch_purchase_aggregates_authorization_failure(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        target_user = stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)

        self.mock_authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", NOT_TARGET_USER)

        controller = PurchasesController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.fetch_purchase_aggregates(target_user.id.hex)

        self.assertIn("Unauthorized", str(context.exception))
        self.mock_purchase_service.get_aggregates_by_user.assert_not_called()

    def test_fetch_purchase_aggregates_excludes_refunded(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        aggregates = stubs.domain.purchase_aggregates(
            total_purchase_count = 2,
            total_cost_cents = 3000,
            total_net_cost_cents = 2700,
            by_product = {"product-123": stubs.domain.product_aggregate_stats(
                record_count = 2,
                total_cost_cents = 3000,
                total_net_cost_cents = 2700,
            )},
        )
        self.mock_purchase_service.get_aggregates_by_user.return_value = aggregates

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_aggregates(invoker_user.id.hex)

        self.assertEqual(result.total_purchase_count, 2)
        self.assertEqual(result.total_cost_cents, 3000)
        self.assertEqual(result.total_net_cost_cents, 2700)

    def test_bind_license_key_success(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)
        self.mock_authorization_service.authorize_for_user.return_value = invoker_user

        bound_record = stubs.domain.purchase_record(user_id = invoker_user.id, license_key = "BOUND-LICENSE-123")
        self.mock_purchase_service.bind_license_key.return_value = bound_record

        controller = PurchasesController(self.mock_di)
        result = controller.bind_license_key(invoker_user.id.hex, "LICENSE-123")

        self.assertEqual(result.user_id, invoker_user.id)
        self.assertEqual(result.license_key, "BOUND-LICENSE-123")
        self.mock_purchase_service.bind_license_key.assert_called_once_with(
            invoker_user.id,
            "LICENSE-123",
        )

    def test_bind_license_key_authorization_failure(self):
        invoker_user = stubs.domain.user(
            id = UUID("12345678-1234-5678-1234-567812345678"),
        )

        target_user = stubs.domain.user(
            id = UUID("87654321-4321-8765-4321-876543218765"),
        )

        type(self.mock_di).invoker = PropertyMock(return_value = invoker_user)

        self.mock_authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", NOT_TARGET_USER)

        controller = PurchasesController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.bind_license_key(target_user.id.hex, "LICENSE-123")

        self.assertIn("Unauthorized", str(context.exception))
        self.mock_purchase_service.bind_license_key.assert_not_called()
