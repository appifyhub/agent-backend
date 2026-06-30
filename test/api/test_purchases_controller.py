import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, PropertyMock
from uuid import UUID

from pydantic import SecretStr

from api.authorization_service import AuthorizationService
from api.purchases_controller import PurchasesController
from db.model.user import UserDB
from di.di import DI
from features.accounting.purchases.purchase_aggregates import (
    ProductAggregateStats,
    ProductInfo,
    PurchaseAggregates,
)
from features.accounting.purchases.purchase_record import PurchaseRecord
from features.accounting.purchases.purchase_service import PurchaseService
from features.users.user import User
from util.error_codes import NOT_TARGET_USER
from util.errors import AuthorizationError, ValidationError


class PurchasesControllerTest(unittest.TestCase):

    invoker_user: User
    target_user: User
    mock_di: DI
    mock_authorization_service: AuthorizationService
    mock_purchase_service: PurchaseService

    def setUp(self):
        self.invoker_user = User(
            id = UUID("12345678-1234-5678-1234-567812345678"),
            full_name = "Invoker User",
            telegram_username = "invoker",
            telegram_chat_id = "123456789",
            telegram_user_id = 123456789,
            open_ai_key = SecretStr("test_openai_key"),
            group = UserDB.Group.developer,
            created_at = datetime.now().date(),
        )
        self.target_user = User(
            id = UUID("87654321-4321-8765-4321-876543218765"),
            full_name = "Target User",
            telegram_username = "target",
            telegram_chat_id = "987654321",
            telegram_user_id = 987654321,
            open_ai_key = SecretStr("test_openai_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )

        self.mock_di = MagicMock(spec = DI)
        type(self.mock_di).invoker = PropertyMock(return_value = self.invoker_user)

        self.mock_authorization_service = MagicMock(spec = AuthorizationService)
        self.mock_authorization_service.authorize_for_user.return_value = self.invoker_user
        self.mock_di.authorization_service = self.mock_authorization_service

        self.mock_purchase_service = MagicMock(spec = PurchaseService)
        self.mock_di.purchase_service = self.mock_purchase_service

    def _create_purchase_record(
        self,
        user_id: UUID,
        price: int = 1000,
        timestamp: datetime | None = None,
    ) -> PurchaseRecord:
        return PurchaseRecord(
            id = UUID(int = 1),
            user_id = user_id,
            seller_id = "seller-123",
            sale_id = "sale-456",
            sale_timestamp = timestamp or datetime.now(timezone.utc),
            price = price,
            product_id = "product-789",
            product_name = "Test Product",
            product_permalink = "https://example.com/product",
            short_product_id = "short-123",
            license_key = "LICENSE-KEY-ABC",
            quantity = 1,
            gumroad_fee = 100,
            affiliate_credit_amount_cents = 50,
            discover_fee_charge = False,
            url_params = {},
            custom_fields = {},
            test = False,
            is_preorder_authorization = False,
            refunded = False,
        )

    def test_fetch_purchase_records_success(self):
        records = [self._create_purchase_record(self.invoker_user.id)]
        self.mock_purchase_service.get_by_user.return_value = records

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_records(self.invoker_user.id.hex)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].user_id, self.invoker_user.id)
        self.mock_authorization_service.authorize_for_user.assert_called_once_with(
            self.invoker_user, self.invoker_user.id.hex,
        )
        self.mock_purchase_service.get_by_user.assert_called_once()

    def test_fetch_purchase_records_with_pagination(self):
        records = [self._create_purchase_record(self.invoker_user.id, price = i) for i in range(5)]
        self.mock_purchase_service.get_by_user.return_value = records[2:4]

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_records(
            self.invoker_user.id.hex,
            skip = 2,
            limit = 2,
        )

        self.assertEqual(len(result), 2)
        self.mock_purchase_service.get_by_user.assert_called_once_with(
            self.invoker_user.id,
            skip = 2,
            limit = 2,
            start_date = None,
            end_date = None,
            product_id = None,
        )

    def test_fetch_purchase_records_with_date_filters(self):
        start = datetime(2024, 1, 1, tzinfo = timezone.utc)
        end = datetime(2024, 12, 31, tzinfo = timezone.utc)
        records = [self._create_purchase_record(self.invoker_user.id)]
        self.mock_purchase_service.get_by_user.return_value = records

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_records(
            self.invoker_user.id.hex,
            start_date = start,
            end_date = end,
        )

        self.assertEqual(len(result), 1)
        self.mock_purchase_service.get_by_user.assert_called_once_with(
            self.invoker_user.id,
            skip = 0,
            limit = 50,
            start_date = start,
            end_date = end,
            product_id = None,
        )

    def test_fetch_purchase_records_with_product_filter(self):
        records = [self._create_purchase_record(self.invoker_user.id)]
        self.mock_purchase_service.get_by_user.return_value = records

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_records(
            self.invoker_user.id.hex,
            product_id = "product-123",
        )

        self.assertEqual(len(result), 1)
        self.mock_purchase_service.get_by_user.assert_called_once_with(
            self.invoker_user.id,
            skip = 0,
            limit = 50,
            start_date = None,
            end_date = None,
            product_id = "product-123",
        )

    def test_fetch_purchase_records_empty_result(self):
        self.mock_purchase_service.get_by_user.return_value = []

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_records(self.invoker_user.id.hex)

        self.assertEqual(len(result), 0)

    def test_fetch_purchase_records_limit_exceeds_maximum(self):
        controller = PurchasesController(self.mock_di)

        with self.assertRaises(ValidationError) as context:
            controller.fetch_purchase_records(self.invoker_user.id.hex, limit = 101)

        self.assertIn("limit cannot exceed 100", str(context.exception))
        self.mock_authorization_service.authorize_for_user.assert_not_called()
        self.mock_purchase_service.get_by_user.assert_not_called()

    def test_fetch_purchase_records_authorization_failure(self):
        self.mock_authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", NOT_TARGET_USER)

        controller = PurchasesController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.fetch_purchase_records(self.target_user.id.hex)

        self.assertIn("Unauthorized", str(context.exception))
        self.mock_purchase_service.get_by_user.assert_not_called()

    def test_fetch_purchase_aggregates_success(self):
        aggregates = PurchaseAggregates(
            total_purchase_count = 10,
            total_cost_cents = 10000,
            total_net_cost_cents = 9000,
            by_product = {"product-123": ProductAggregateStats(
                record_count = 10,
                total_cost_cents = 10000,
                total_net_cost_cents = 9000,
            )},
            all_products_used = [ProductInfo(id = "product-123", name = "Test Product")],
        )
        self.mock_purchase_service.get_aggregates_by_user.return_value = aggregates

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_aggregates(self.invoker_user.id.hex)

        self.assertEqual(result.total_purchase_count, 10)
        self.assertEqual(result.total_cost_cents, 10000)
        self.assertEqual(result.total_net_cost_cents, 9000)
        self.assertIn("product-123", result.by_product)
        self.mock_authorization_service.authorize_for_user.assert_called_once_with(
            self.invoker_user, self.invoker_user.id.hex,
        )

    def test_fetch_purchase_aggregates_with_date_filters(self):
        start = datetime(2024, 1, 1, tzinfo = timezone.utc)
        end = datetime(2024, 12, 31, tzinfo = timezone.utc)
        aggregates = PurchaseAggregates(
            total_purchase_count = 0,
            total_cost_cents = 0,
            total_net_cost_cents = 0,
            by_product = {},
            all_products_used = [],
        )
        self.mock_purchase_service.get_aggregates_by_user.return_value = aggregates

        controller = PurchasesController(self.mock_di)
        controller.fetch_purchase_aggregates(
            self.invoker_user.id.hex,
            start_date = start,
            end_date = end,
        )

        self.mock_purchase_service.get_aggregates_by_user.assert_called_once_with(
            self.invoker_user.id,
            start_date = start,
            end_date = end,
            product_id = None,
        )

    def test_fetch_purchase_aggregates_authorization_failure(self):
        self.mock_authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", NOT_TARGET_USER)

        controller = PurchasesController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.fetch_purchase_aggregates(self.target_user.id.hex)

        self.assertIn("Unauthorized", str(context.exception))
        self.mock_purchase_service.get_aggregates_by_user.assert_not_called()

    def test_fetch_purchase_aggregates_excludes_refunded(self):
        aggregates = PurchaseAggregates(
            total_purchase_count = 2,
            total_cost_cents = 3000,
            total_net_cost_cents = 2700,
            by_product = {"product-123": ProductAggregateStats(
                record_count = 2,
                total_cost_cents = 3000,
                total_net_cost_cents = 2700,
            )},
            all_products_used = [ProductInfo(id = "product-123", name = "Test Product")],
        )
        self.mock_purchase_service.get_aggregates_by_user.return_value = aggregates

        controller = PurchasesController(self.mock_di)
        result = controller.fetch_purchase_aggregates(self.invoker_user.id.hex)

        self.assertEqual(result.total_purchase_count, 2)
        self.assertEqual(result.total_cost_cents, 3000)
        self.assertEqual(result.total_net_cost_cents, 2700)

    def test_bind_license_key_success(self):
        bound_record = self._create_purchase_record(self.invoker_user.id)
        self.mock_purchase_service.bind_license_key.return_value = bound_record

        controller = PurchasesController(self.mock_di)
        result = controller.bind_license_key(self.invoker_user.id.hex, "LICENSE-123")

        self.assertEqual(result.user_id, self.invoker_user.id)
        self.assertEqual(result.license_key, "LICENSE-KEY-ABC")
        self.mock_purchase_service.bind_license_key.assert_called_once_with(
            self.invoker_user.id,
            "LICENSE-123",
        )

    def test_bind_license_key_authorization_failure(self):
        self.mock_authorization_service.authorize_for_user.side_effect = AuthorizationError("Unauthorized", NOT_TARGET_USER)

        controller = PurchasesController(self.mock_di)

        with self.assertRaises(AuthorizationError) as context:
            controller.bind_license_key(self.target_user.id.hex, "LICENSE-123")

        self.assertIn("Unauthorized", str(context.exception))
        self.mock_purchase_service.bind_license_key.assert_not_called()
