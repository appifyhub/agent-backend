import unittest
from io import BytesIO

from langchain_core.messages import AIMessage, HumanMessage
from PIL import Image

from util.errors import ExternalServiceError
from util.functions import (
    detect_image_format,
    extract_url_from_replicate_result,
    generate_short_uuid,
    mask_secret,
    obfuscate_url,
    parse_ai_message_content,
    parse_gumroad_form,
    silent,
)


class MockPrediction:

    def __init__(
        self,
        output = None,
        status = "succeeded",
        error = None,
        logs = None,
    ):
        self.output = output
        self.status = status
        self.error = error
        self.logs = logs


class FunctionsTest(unittest.TestCase):

    def test_silent_function_no_exception(self):
        @silent
        def no_exception() -> int:
            return 42

        result = no_exception()
        self.assertEqual(result, 42)

    def test_silent_function_with_exception(self):
        @silent
        def raise_exception() -> None:
            raise ValueError("This is an error")

        result = raise_exception()
        self.assertIsNone(result)

    def test_silent_lambda_no_exception(self):
        result = silent(lambda: 100)()
        self.assertEqual(result, 100)

    def test_silent_lambda_with_exception(self):
        result = silent(lambda: 10 / 0)()
        self.assertIsNone(result)

    def test_detect_image_format(self):
        pattern = [
            "bbbbwwww",
            "bbbbwwww",
            "bbbbwwww",
            "bbbbwwww",
            "wwwwbbbb",
            "wwwwbbbb",
            "wwwwbbbb",
            "wwwwbbbb",
        ]
        image = Image.new("RGB", (8, 8))
        for y, row in enumerate(pattern):
            for x, pixel in enumerate(row):
                color = (0, 0, 0) if pixel == "b" else (255, 255, 255)
                image.putpixel((x, y), color)

        formats = {
            "PNG": "png",
            "JPEG": "jpeg",
            "GIF": "gif",
            "BMP": "bmp",
            "WEBP": "webp",
            "TIFF": "tiff",
        }
        for encoded_format, expected in formats.items():
            with self.subTest(encoded_format = encoded_format):
                output = BytesIO()
                image.save(output, format = encoded_format)
                self.assertEqual(detect_image_format(output.getvalue()), expected)

    def test_detect_image_format_returns_none_for_unknown_content(self):
        self.assertIsNone(detect_image_format(b"unknown content"))

    def test_mask_secret_none(self):
        # noinspection HardcodedPassword
        secret = None
        result = mask_secret(secret)
        self.assertEqual(result, None)

    def test_mask_secret_empty_string(self):
        # noinspection HardcodedPassword
        secret = ""
        result = mask_secret(secret)
        self.assertEqual(result, "")

    def test_mask_secret_single_char(self):
        # noinspection HardcodedPassword
        secret = "a"
        result = mask_secret(secret)
        self.assertEqual(result, "*")

    def test_mask_secret_two_chars(self):
        # noinspection HardcodedPassword
        secret = "ab"
        result = mask_secret(secret)
        self.assertEqual(result, "**")

    def test_mask_secret_three_chars(self):
        # noinspection HardcodedPassword
        secret = "abc"
        result = mask_secret(secret)
        self.assertEqual(result, "***")

    def test_mask_secret_four_chars(self):
        # noinspection HardcodedPassword
        secret = "abcd"
        result = mask_secret(secret)
        self.assertEqual(result, "****")

    def test_mask_secret_medium_length_short(self):
        # noinspection HardcodedPassword
        secret = "abcde"
        result = mask_secret(secret)
        self.assertEqual(result, "a***e")

    def test_mask_secret_medium_length_long(self):
        # noinspection HardcodedPassword
        secret = "abcdefgh"
        result = mask_secret(secret)
        self.assertEqual(result, "a******h")

    def test_mask_secret_large_length_short(self):
        # noinspection HardcodedPassword
        secret = "abcdefghi"
        result = mask_secret(secret)
        self.assertEqual(result, "abc*****ghi")

    def test_mask_secret_large_length_long(self):
        # noinspection HardcodedPassword
        secret = "abcdefghijklmnopqrstuvwxyz"
        result = mask_secret(secret)
        self.assertEqual(result, "abc*****xyz")

    def test_mask_secret_custom_mask(self):
        # noinspection HardcodedPassword
        secret = "abcdefghijklmnopqrstuvwxyz"
        result = mask_secret(secret, mask = "#")
        self.assertEqual(result, "abc#####xyz")

    def test_obfuscate_url_removes_https_scheme_and_keeps_edges(self):
        result = obfuscate_url("https://test.example.com/settings/key123")

        self.assertEqual(result, "test...123")

    def test_obfuscate_url_removes_http_scheme_and_keeps_edges(self):
        result = obfuscate_url("http://test.example.com/settings/key123")

        self.assertEqual(result, "test...123")

    def test_obfuscate_url_keeps_short_url_without_scheme(self):
        result = obfuscate_url("https://abc1234")

        self.assertEqual(result, "abc1234")

    def test_obfuscate_url_keeps_url_without_scheme(self):
        result = obfuscate_url("example.com/settings/key123")

        self.assertEqual(result, "exam...123")

    def test_generate_short_uuid_length(self):
        result = generate_short_uuid()
        self.assertEqual(len(result), 8)

    def test_generate_short_uuid_format(self):
        result = generate_short_uuid()
        # Should only contain hexadecimal characters
        self.assertRegex(result, r"^[0-9a-f]{8}$")

    def test_generate_deterministic_short_uuid_consistency(self):
        from util.functions import generate_deterministic_short_uuid
        seed = "test_file_id_123"
        result1 = generate_deterministic_short_uuid(seed)
        result2 = generate_deterministic_short_uuid(seed)
        self.assertEqual(result1, result2)

    def test_generate_deterministic_short_uuid_format(self):
        from util.functions import generate_deterministic_short_uuid
        result = generate_deterministic_short_uuid("test_seed")
        self.assertEqual(len(result), 8)
        # Should only contain hexadecimal characters
        self.assertRegex(result, r"^[0-9a-f]{8}$")

    def test_generate_deterministic_short_uuid_different_seeds(self):
        from util.functions import generate_deterministic_short_uuid
        result1 = generate_deterministic_short_uuid("seed1")
        result2 = generate_deterministic_short_uuid("seed2")
        self.assertNotEqual(result1, result2)

    def test_generate_deterministic_short_uuid_realistic_telegram_ids(self):
        from util.functions import generate_deterministic_short_uuid
        # Test with realistic Telegram file IDs
        telegram_file_id = "BAADBQADBgADmEjNSW5XPx5aVTaiAg"
        result1 = generate_deterministic_short_uuid(telegram_file_id)
        result2 = generate_deterministic_short_uuid(telegram_file_id)

        # Should be consistent
        self.assertEqual(result1, result2)
        # Should be valid format
        self.assertEqual(len(result1), 8)
        self.assertRegex(result1, r"^[0-9a-f]{8}$")

    def test_extract_url_from_replicate_result_list_with_file_output(self):
        class MockFileOutput:

            url = "https://example.com/image.png"

        prediction = MockPrediction(output = [MockFileOutput()])
        result = extract_url_from_replicate_result(prediction)
        self.assertEqual(result, "https://example.com/image.png")

    def test_extract_url_from_replicate_result_list_with_string(self):
        prediction = MockPrediction(output = ["https://example.com/image.png"])
        result = extract_url_from_replicate_result(prediction)
        self.assertEqual(result, "https://example.com/image.png")

    def test_extract_url_from_replicate_result_single_file_output(self):
        class MockFileOutput:

            url = "https://example.com/image.png"

        prediction = MockPrediction(output = MockFileOutput())
        result = extract_url_from_replicate_result(prediction)
        self.assertEqual(result, "https://example.com/image.png")

    def test_extract_url_from_replicate_result_single_string(self):
        prediction = MockPrediction(output = "https://example.com/image.png")
        result = extract_url_from_replicate_result(prediction)
        self.assertEqual(result, "https://example.com/image.png")

    def test_extract_url_from_replicate_result_empty_list(self):
        prediction = MockPrediction(output = [])
        with self.assertRaises(ExternalServiceError) as context:
            extract_url_from_replicate_result(prediction)
        self.assertIn("empty result", str(context.exception).lower())

    def test_extract_url_from_replicate_result_unexpected_type_in_list(self):
        prediction = MockPrediction(output = [12345])
        with self.assertRaises(ExternalServiceError) as context:
            extract_url_from_replicate_result(prediction)
        self.assertIn("Unexpected result type in list", str(context.exception))

    def test_extract_url_from_replicate_result_unexpected_type(self):
        prediction = MockPrediction(output = 12345)
        with self.assertRaises(ExternalServiceError) as context:
            extract_url_from_replicate_result(prediction)
        self.assertIn("Unexpected result type from Replicate", str(context.exception))

    def test_extract_url_from_replicate_result_none_output_with_error(self):
        prediction = MockPrediction(output = None, status = "failed", error = "NSFW content detected")
        with self.assertRaises(ExternalServiceError) as context:
            extract_url_from_replicate_result(prediction)
        self.assertIn("NSFW content detected", str(context.exception))
        self.assertIn("failed", str(context.exception))

    def test_extract_url_from_replicate_result_none_output_falls_back_to_logs(self):
        prediction = MockPrediction(output = None, status = "failed", error = None, logs = "OOM killed")
        with self.assertRaises(ExternalServiceError) as context:
            extract_url_from_replicate_result(prediction)
        self.assertIn("OOM killed", str(context.exception))

    def test_extract_url_from_replicate_result_none_output_no_diagnostics(self):
        prediction = MockPrediction(output = None)
        with self.assertRaises(ExternalServiceError) as context:
            extract_url_from_replicate_result(prediction)
        self.assertIn("unknown", str(context.exception))

    def test_normalize_phone_number_none(self):
        from util.functions import normalize_phone_number
        self.assertIsNone(normalize_phone_number(None))

    def test_normalize_phone_number_empty(self):
        from util.functions import normalize_phone_number
        self.assertEqual(normalize_phone_number(""), "")

    def test_normalize_phone_number_plus_and_dashes(self):
        from util.functions import normalize_phone_number
        self.assertEqual(normalize_phone_number("+1-234-567-8900"), "12345678900")

    def test_normalize_phone_number_spaces_parentheses(self):
        from util.functions import normalize_phone_number
        self.assertEqual(normalize_phone_number("(123) 456 7890"), "1234567890")

    def test_normalize_phone_number_mixed_chars(self):
        from util.functions import normalize_phone_number
        self.assertEqual(normalize_phone_number("wa:+38 044-123-45-67 ext.89"), "38044123456789")

    def test_normalize_phone_number_strips_leading_double_zero(self):
        from util.functions import normalize_phone_number
        self.assertEqual(normalize_phone_number("0049123456789"), "49123456789")

    def test_normalize_username_none(self):
        from util.functions import normalize_username
        self.assertIsNone(normalize_username(None))

    def test_normalize_username_empty(self):
        from util.functions import normalize_username
        self.assertEqual(normalize_username(""), "")

    def test_normalize_username_with_at(self):
        from util.functions import normalize_username
        self.assertEqual(normalize_username("@username"), "username")

    def test_normalize_username_with_plus(self):
        from util.functions import normalize_username
        self.assertEqual(normalize_username("+username"), "username")

    def test_normalize_username_with_spaces(self):
        from util.functions import normalize_username
        self.assertEqual(normalize_username("user name"), "username")

    def test_normalize_username_mixed_chars(self):
        from util.functions import normalize_username
        self.assertEqual(normalize_username("@ +user name+"), "username")

    def test_parse_ai_message_content_string(self):
        result = parse_ai_message_content(AIMessage("Hello world"))
        self.assertEqual(result, "Hello world")

    def test_parse_ai_message_content_strips_outer_whitespace(self):
        result = parse_ai_message_content(AIMessage("  Hello world \n"))
        self.assertEqual(result, "Hello world")

    def test_parse_ai_message_content_list_with_text_blocks(self):
        content = [
            {"type": "text", "text": "Part 1."},
            {"type": "text", "text": "Part 2."},
            {"type": "image_url", "image_url": "http://example.com"},
        ]
        result = parse_ai_message_content(AIMessage(content = content))
        self.assertEqual(result, "Part 1.\nPart 2.")

    def test_parse_ai_message_content_list_with_strings(self):
        content = ["Part 1.", "Part 2."]
        result = parse_ai_message_content(AIMessage(content = content))
        self.assertEqual(result, "Part 1.\nPart 2.")

    def test_parse_ai_message_content_list_mixed(self):
        content = [
            "Part 1.",
            {"type": "text", "text": "Part 2."},
        ]
        result = parse_ai_message_content(AIMessage(content = content))
        self.assertEqual(result, "Part 1.\nPart 2.")

    def test_parse_ai_message_content_empty_result(self):
        with self.assertRaises(ExternalServiceError) as context:
            parse_ai_message_content(AIMessage(content = []))
        self.assertIn("Received empty content", str(context.exception))

    def test_parse_ai_message_content_non_ai_message(self):
        with self.assertRaises(ExternalServiceError) as context:
            parse_ai_message_content(HumanMessage("Hello world"))
        self.assertIn("Received a non-AI message", str(context.exception))

    def test_parse_gumroad_form_no_params(self):
        form_dict = {
            "seller_id": "abc123",
            "sale_id": "sale456",
            "price": "1299",
        }
        result = parse_gumroad_form(form_dict)
        self.assertEqual(result, {
            "seller_id": "abc123",
            "sale_id": "sale456",
            "price": "1299",
        })

    def test_parse_gumroad_form_with_url_params(self):
        form_dict = {
            "seller_id": "abc123",
            "url_params[user_id]": "user123",
            "url_params[campaign]": "spring2024",
            "price": "1299",
        }
        result = parse_gumroad_form(form_dict)
        self.assertEqual(result, {
            "seller_id": "abc123",
            "price": "1299",
            "url_params": {
                "user_id": "user123",
                "campaign": "spring2024",
            },
        })

    def test_parse_gumroad_form_with_custom_fields(self):
        form_dict = {
            "seller_id": "abc123",
            "custom_fields[referral]": "twitter",
            "custom_fields[notes]": "test purchase",
            "price": "1299",
        }
        result = parse_gumroad_form(form_dict)
        self.assertEqual(result, {
            "seller_id": "abc123",
            "price": "1299",
            "custom_fields": {
                "referral": "twitter",
                "notes": "test purchase",
            },
        })

    def test_parse_gumroad_form_with_both(self):
        form_dict = {
            "seller_id": "abc123",
            "url_params[user_id]": "user123",
            "custom_fields[referral]": "twitter",
            "price": "1299",
        }
        result = parse_gumroad_form(form_dict)
        self.assertEqual(result, {
            "seller_id": "abc123",
            "price": "1299",
            "url_params": {
                "user_id": "user123",
            },
            "custom_fields": {
                "referral": "twitter",
            },
        })

    def test_parse_gumroad_form_empty_dict(self):
        form_dict = {}
        result = parse_gumroad_form(form_dict)
        self.assertEqual(result, {})
