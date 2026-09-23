import unittest

from util.config import config
from util.translations_cache import TranslationsCache


class TranslationsCacheTest(unittest.TestCase):

    def test_save_and_get_with_language_name(self):
        cache = TranslationsCache()

        self.assertEqual(cache.save("Hello", "English"), "Hello")
        self.assertEqual(cache.get("English"), "Hello")
        self.assertEqual(cache.get("ENGLISH"), "Hello")

    def test_save_and_get_with_iso_code(self):
        cache = TranslationsCache()

        self.assertEqual(cache.save("Bonjour", language_iso_code = "FR"), "Bonjour")
        self.assertEqual(cache.get(language_iso_code = "FR"), "Bonjour")
        self.assertEqual(cache.get(language_iso_code = "fr"), "Bonjour")

    def test_save_and_get_with_both(self):
        cache = TranslationsCache()

        self.assertEqual(cache.save("Hola", "Spanish", "ES"), "Hola")
        self.assertEqual(cache.get("Spanish", "ES"), "Hola")
        self.assertEqual(cache.get("SPANISH", "es"), "Hola")

    def test_save_and_get_default(self):
        cache = TranslationsCache()

        self.assertEqual(cache.save("Hi"), "Hi")
        self.assertEqual(cache.get(), "Hi")
        self.assertEqual(cache.get(language_name = config.main_language_name), "Hi")
        self.assertEqual(cache.get(language_iso_code = config.main_language_iso_code), "Hi")

    def test_get_nonexistent(self):
        cache = TranslationsCache()

        self.assertIsNone(cache.get(language_name = "German"))
        self.assertIsNone(cache.get(language_iso_code = "DE"))

    def test_get_priority(self):
        cache = TranslationsCache()

        cache.save("Hello", "English", "EN")
        cache.save("Hi", "English")
        cache.save("Howdy", language_iso_code = "EN")
        self.assertEqual(cache.get("English", "EN"), "Hello")
        self.assertEqual(cache.get(language_name = "English"), "Hi")
        self.assertEqual(cache.get(language_iso_code = "EN"), "Howdy")

    def test_multiple_instances(self):
        cache1 = TranslationsCache()
        cache2 = TranslationsCache()
        cache1.save("Hello", "English")
        self.assertIsNone(cache2.get("English"))

    def test_case_insensitivity(self):
        cache = TranslationsCache()

        cache.save("Hello", "English", "EN")
        self.assertEqual(cache.get("ENGLISH", "en"), "Hello")
        self.assertEqual(cache.get("english", "EN"), "Hello")

    def test_overwrite(self):
        cache = TranslationsCache()

        cache.save("Hello", "English")
        cache.save("Hi", "English")
        self.assertEqual(cache.get("English"), "Hi")

    def test_get_with_partial_match(self):
        cache = TranslationsCache()

        cache.save("Hola", "Spanish", "ES")
        self.assertEqual(cache.get(language_name = "Spanish"), "Hola")
        self.assertEqual(cache.get(language_iso_code = "ES"), "Hola")

    def test_get_default_priority(self):
        cache = TranslationsCache()

        cache.save("Hello")
        cache.save("Hi", language_name = config.main_language_name)
        cache.save("Hey", language_iso_code = config.main_language_iso_code)
        self.assertEqual(cache.get(), "Hello")
