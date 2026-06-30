import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

from api.model.gumroad_ping_payload import GumroadPingPayload
from di.di import DI
from features.accounting.purchases.purchase_record import PurchaseRecord
from features.accounting.purchases.purchase_record_repo import PurchaseRecordRepository
from features.accounting.purchases.purchase_service import PurchaseService
from util.config import ConfiguredProduct

KNOWN_PRODUCT_ID = "GUMROAD_ID_100"
KNOWN_PRODUCT_CREDITS = 100
DONATION_PRODUCT_ID = "GUMROAD_ID_DONATION"
UNKNOWN_PRODUCT_ID = "UNKNOWN_PRODUCT"


def _mock_config(known: bool = True, credits: int = KNOWN_PRODUCT_CREDITS):
    mock = Mock()
    products_mock = MagicMock()
    products_mock.__contains__ = Mock(return_value = known)
    if known:
        products_mock.get = Mock(return_value = ConfiguredProduct(id = "mock_id", credits = credits, name = "Mock Product", url = "https://example.com"))
    else:
        products_mock.get = Mock(return_value = None)
    mock.products = products_mock
    return mock


class PurchaseServiceTest(unittest.TestCase):

    mock_di: DI
    user_id: UUID
    service: PurchaseService

    def setUp(self):
        self.user_id = UUID(int = 1)

        self.mock_di = Mock(spec = DI)

        mock_user = Mock()
        mock_user.id = self.user_id
        mock_user_repo = Mock()
        mock_user_repo.get = MagicMock(return_value = mock_user)
        mock_user_repo.update_locked = MagicMock()
        self.mock_di.user_repo = mock_user_repo

        mock_repo = Mock(spec = PurchaseRecordRepository)
        mock_repo.save = MagicMock(side_effect = lambda x: x)
        mock_repo.get_by_user = MagicMock(return_value = [])
        mock_repo.get_aggregates_by_user = MagicMock(return_value = None)
        mock_repo.bind_license_key_to_user = MagicMock()
        self.mock_di.purchase_record_repo = mock_repo

        self.service = PurchaseService(self.mock_di)

    def _create_payload(
        self,
        sale_id = "sale-123",
        product_id = KNOWN_PRODUCT_ID,
        user_id_in_params = None,
        license_key = None,
        refunded = False,
        test = False,
        quantity = 1,
    ) -> GumroadPingPayload:
        url_params = {}
        if user_id_in_params:
            url_params["user_id"] = user_id_in_params

        return GumroadPingPayload(
            seller_id = "seller-123",
            sale_id = sale_id,
            sale_timestamp = "2024-01-01T00:00:00Z",
            price = 1000,
            product_id = product_id,
            product_name = "Test Product",
            product_permalink = "https://example.com/product",
            short_product_id = "short-123",
            license_key = license_key,
            quantity = quantity,
            gumroad_fee = 100,
            affiliate_credit_amount_cents = 50,
            discover_fee_charge = False,
            url_params = url_params if url_params else None,
            custom_fields = {},
            test = test,
            is_preorder_authorization = False,
            refunded = refunded,
        )

    def test_record_purchase_success(self):
        payload = self._create_payload(user_id_in_params = str(self.user_id))

        with patch("features.accounting.purchases.purchase_service.config", _mock_config()):
            record = self.service.record_purchase(payload)

        self.assertIsInstance(record, PurchaseRecord)
        self.assertEqual(record.sale_id, "sale-123")
        self.assertEqual(record.price, 1000)

    def test_record_purchase_ignores_unknown_product(self):
        payload = self._create_payload(product_id = UNKNOWN_PRODUCT_ID)

        with patch("features.accounting.purchases.purchase_service.config", _mock_config(known = False)):
            record = self.service.record_purchase(payload)

        self.assertIsNone(record)
        self.mock_di.purchase_record_repo.save.assert_not_called()

    def test_record_purchase_extracts_user_id_from_url_params(self):
        payload = self._create_payload(user_id_in_params = str(self.user_id))

        with patch("features.accounting.purchases.purchase_service.config", _mock_config()):
            record = self.service.record_purchase(payload)

        assert record is not None
        self.assertEqual(record.user_id, self.user_id)
        self.mock_di.user_repo.get.assert_called_once_with(self.user_id)

    def test_record_purchase_handles_missing_user_id(self):
        payload = self._create_payload(user_id_in_params = None)

        with patch("features.accounting.purchases.purchase_service.config", _mock_config()):
            record = self.service.record_purchase(payload)

        assert record is not None
        self.assertIsNone(record.user_id)

    def test_record_purchase_handles_invalid_user_id(self):
        payload = self._create_payload(user_id_in_params = "invalid-uuid")

        with patch("features.accounting.purchases.purchase_service.config", _mock_config()):
            record = self.service.record_purchase(payload)

        assert record is not None
        self.assertIsNone(record.user_id)

    def test_record_purchase_handles_nonexistent_user(self):
        self.mock_di.user_repo.get.return_value = None
        payload = self._create_payload(user_id_in_params = str(self.user_id))

        with patch("features.accounting.purchases.purchase_service.config", _mock_config()):
            record = self.service.record_purchase(payload)

        assert record is not None
        self.assertIsNone(record.user_id)

    def test_record_purchase_persists_to_repo(self):
        payload = self._create_payload(user_id_in_params = None)

        with patch("features.accounting.purchases.purchase_service.config", _mock_config()):
            self.service.record_purchase(payload)

        self.mock_di.purchase_record_repo.save.assert_called()

    def test_record_purchase_allocates_credits_on_new_purchase(self):
        payload = self._create_payload(user_id_in_params = str(self.user_id), quantity = 2)

        with patch("features.accounting.purchases.purchase_service.config", _mock_config()):
            self.service.record_purchase(payload)

        self.mock_di.user_repo.update_locked.assert_called_once()
        call_args = self.mock_di.user_repo.update_locked.call_args
        self.assertEqual(call_args.kwargs["user_id"], self.user_id)
        self.assertTrue(callable(call_args.kwargs["update_fn"]))

    def test_record_purchase_does_not_allocate_credits_for_donation(self):
        payload = self._create_payload(user_id_in_params = str(self.user_id), product_id = DONATION_PRODUCT_ID)

        with patch("features.accounting.purchases.purchase_service.config", _mock_config(credits = 0)):
            record = self.service.record_purchase(payload)

        self.mock_di.user_repo.update_locked.assert_not_called()
        assert record is not None

    def test_record_purchase_does_not_allocate_credits_for_test_purchase(self):
        payload = self._create_payload(user_id_in_params = str(self.user_id), test = True)

        with patch("features.accounting.purchases.purchase_service.config", _mock_config()):
            self.service.record_purchase(payload)

        self.mock_di.user_repo.update_locked.assert_not_called()

    def test_record_purchase_does_not_allocate_credits_without_user_id(self):
        payload = self._create_payload()

        with patch("features.accounting.purchases.purchase_service.config", _mock_config()):
            self.service.record_purchase(payload)

        self.mock_di.user_repo.update_locked.assert_not_called()

    def test_record_purchase_deducts_credits_on_refund(self):
        already_allocated = PurchaseRecord(
            id = UUID(int = 99),
            user_id = self.user_id,
            seller_id = "seller-123",
            sale_id = "sale-123",
            sale_timestamp = __import__("datetime").datetime(2024, 1, 1),
            price = 1000,
            product_id = KNOWN_PRODUCT_ID,
            product_name = "Test Product",
            product_permalink = "https://example.com/product",
            short_product_id = "short-123",
            quantity = 1,
            refunded = True,
        )
        self.mock_di.purchase_record_repo.save = MagicMock(return_value = already_allocated)

        payload = self._create_payload(user_id_in_params = str(self.user_id), refunded = True)

        with patch("features.accounting.purchases.purchase_service.config", _mock_config()):
            self.service.record_purchase(payload)

        self.mock_di.user_repo.update_locked.assert_called_once()
        call_args = self.mock_di.user_repo.update_locked.call_args
        self.assertEqual(call_args.kwargs["user_id"], self.user_id)
        self.assertTrue(callable(call_args.kwargs["update_fn"]))

    def test_bind_license_key_delegates_to_repo(self):
        mock_record = Mock(spec = PurchaseRecord)
        self.mock_di.purchase_record_repo.bind_license_key_to_user = MagicMock(return_value = mock_record)

        self.service.bind_license_key(self.user_id, "LICENSE-123")

        self.mock_di.purchase_record_repo.bind_license_key_to_user.assert_called_once_with(
            "LICENSE-123",
            self.user_id,
        )

    def test_bind_license_key_allocates_credits(self):
        mock_record = PurchaseRecord(
            id = UUID(int = 99),
            user_id = self.user_id,
            seller_id = "seller-123",
            sale_id = "sale-123",
            sale_timestamp = __import__("datetime").datetime(2024, 1, 1),
            price = 1000,
            product_id = KNOWN_PRODUCT_ID,
            product_name = "Test Product",
            product_permalink = "https://example.com/product",
            short_product_id = "short-123",
            quantity = 1,
            refunded = False,
            test = False,
            is_preorder_authorization = False,
        )
        self.mock_di.purchase_record_repo.bind_license_key_to_user = MagicMock(return_value = mock_record)
        self.mock_di.purchase_record_repo.save = MagicMock(side_effect = lambda x: x)

        with patch("features.accounting.purchases.purchase_service.config", _mock_config()):
            self.service.bind_license_key(self.user_id, "LICENSE-123")

        self.mock_di.user_repo.update_locked.assert_called_once()
        call_args = self.mock_di.user_repo.update_locked.call_args
        self.assertEqual(call_args.kwargs["user_id"], self.user_id)
        self.assertTrue(callable(call_args.kwargs["update_fn"]))

    def test_get_by_user_delegates_to_repo(self):
        self.service.get_by_user(self.user_id)

        self.mock_di.purchase_record_repo.get_by_user.assert_called_once_with(
            self.user_id,
            skip = 0,
            limit = 50,
            start_date = None,
            end_date = None,
            product_id = None,
        )

    def test_get_aggregates_by_user_delegates_to_repo(self):
        self.service.get_aggregates_by_user(self.user_id)

        self.mock_di.purchase_record_repo.get_aggregates_by_user.assert_called_once_with(
            self.user_id,
            start_date = None,
            end_date = None,
            product_id = None,
        )
