import inspect
import unittest

from util import error_codes


class ErrorCodesTest(unittest.TestCase):

    __VALID_RANGES = [
        (1000, 1999),  # Validation
        (2000, 2999),  # Not Found
        (3000, 3999),  # Authorization
        (4000, 4999),  # Authentication
        (5000, 5999),  # External Service
        (6000, 6999),  # Rate Limit
        (7000, 7999),  # Configuration
        (8000, 8999),  # Internal
    ]

    @staticmethod
    def __active_error_codes() -> dict[str, int]:
        return {
            name: value
            for name, value in inspect.getmembers(error_codes)
            if not name.startswith("_") and isinstance(value, int)
        }

    def test_no_duplicate_error_codes(self):
        seen: dict[int, str] = {}
        duplicates: list[str] = []
        for name, value in self.__active_error_codes().items():
            if value in seen:
                duplicates.append(f"{name}={value} duplicates {seen[value]}")
            else:
                seen[value] = name
        self.assertEqual(duplicates, [], f"Duplicate error codes found: {duplicates}")

    def test_error_codes_in_valid_category_ranges(self):
        for name, value in self.__active_error_codes().items():
            in_range = any(low <= value <= high for low, high in self.__VALID_RANGES)
            self.assertTrue(in_range, f"{name}={value} is not in any valid category range")

    def test_reserved_error_codes_are_not_reused(self):
        active_codes = set(self.__active_error_codes().values())

        self.assertTrue(active_codes.isdisjoint(error_codes.RESERVED_ERROR_CODES))

    def test_new_error_codes_use_next_number_in_category(self):
        allocated_codes = set(self.__active_error_codes().values()) | error_codes.RESERVED_ERROR_CODES
        allocated_codes.remove(error_codes.UNEXPECTED_ERROR)

        for low, high in self.__VALID_RANGES:
            category_codes = sorted(code for code in allocated_codes if low <= code <= high)
            expected_codes = list(range(low + 1, category_codes[-1] + 1))
            self.assertEqual(category_codes, expected_codes)
