import unittest

from util.di_utils import di_for_tests

from di.di import DI
from util.config import config


class TranslationsCacheTest(unittest.TestCase):

    di: DI

    def setUp(self):
        self.di = self.enterContext(di_for_tests())

    def test_save_and_get_with_language_name(self):
        cache = self.di.translations_cache

        self.assertEqual(cache.save("Hello", "English"), "Hello")
        self.assertEqual(cache.get("English"), "Hello")
        self.assertEqual(cache.get("ENGLISH"), "Hello")

    def test_save_and_get_with_iso_code(self):
        cache = self.di.translations_cache

        self.assertEqual(cache.save("Bonjour", language_iso_code = "FR"), "Bonjour")
        self.assertEqual(cache.get(language_iso_code = "FR"), "Bonjour")
        self.assertEqual(cache.get(language_iso_code = "fr"), "Bonjour")

    def test_save_and_get_with_both(self):
        cache = self.di.translations_cache

        self.assertEqual(cache.save("Hola", "Spanish", "ES"), "Hola")
        self.assertEqual(cache.get("Spanish", "ES"), "Hola")
        self.assertEqual(cache.get("SPANISH", "es"), "Hola")

    def test_save_and_get_default(self):
        cache = self.di.translations_cache

        self.assertEqual(cache.save("Hi"), "Hi")
        self.assertEqual(cache.get(), "Hi")
        self.assertEqual(cache.get(language_name = config.main_language_name), "Hi")
        self.assertEqual(cache.get(language_iso_code = config.main_language_iso_code), "Hi")

    def test_get_nonexistent(self):
        cache = self.di.translations_cache

        self.assertIsNone(cache.get(language_name = "German"))
        self.assertIsNone(cache.get(language_iso_code = "DE"))

    def test_get_priority(self):
        cache = self.di.translations_cache

        cache.save("Hello", "English", "EN")
        cache.save("Hi", "English")
        cache.save("Howdy", language_iso_code = "EN")
        self.assertEqual(cache.get("English", "EN"), "Hello")
        self.assertEqual(cache.get(language_name = "English"), "Hi")
        self.assertEqual(cache.get(language_iso_code = "EN"), "Howdy")

    def test_multiple_instances(self):
        cache1 = self.di.translations_cache
        cache2 = self.di.translations_cache
        cache1.save("Hello", "English")
        self.assertIsNone(cache2.get("English"))

    def test_case_insensitivity(self):
        cache = self.di.translations_cache

        cache.save("Hello", "English", "EN")
        self.assertEqual(cache.get("ENGLISH", "en"), "Hello")
        self.assertEqual(cache.get("english", "EN"), "Hello")

    def test_overwrite(self):
        cache = self.di.translations_cache

        cache.save("Hello", "English")
        cache.save("Hi", "English")
        self.assertEqual(cache.get("English"), "Hi")

    def test_get_with_partial_match(self):
        cache = self.di.translations_cache

        cache.save("Hola", "Spanish", "ES")
        self.assertEqual(cache.get(language_name = "Spanish"), "Hola")
        self.assertEqual(cache.get(language_iso_code = "ES"), "Hola")

    def test_get_default_priority(self):
        cache = self.di.translations_cache

        cache.save("Hello")
        cache.save("Hi", language_name = config.main_language_name)
        cache.save("Hey", language_iso_code = config.main_language_iso_code)
        self.assertEqual(cache.get(), "Hello")
