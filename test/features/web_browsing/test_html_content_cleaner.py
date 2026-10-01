from datetime import datetime, timedelta
from unittest import TestCase

from stubs import domain
from util.di_utils import di_for_tests

from di.di import DI
from features.tools_cache.tools_cache import ToolsCache
from features.web_browsing.html_content_cleaner import CACHE_PREFIX, CACHE_TTL, HTMLContentCleaner
from util.functions import digest_md5


class HTMLContentCleanerTest(TestCase):

    di: DI

    def setUp(self):
        self.di = self.enterContext(di_for_tests())

    def test_clean_up_cache_miss(self):
        html = "<html><body><h1>Title</h1><p>Some content.</p></body></html>"
        cleaner = self.di.html_content_cleaner(html)
        started_at = datetime.now()

        result = cleaner.clean_up()

        self.assertIn("# Title", result)
        self.assertIn("Some content", result)
        cached = self.di.tools_cache_repo.get(ToolsCache.create_key(CACHE_PREFIX, digest_md5(html)))
        self.assertEqual(cached.value, result)
        self.assertGreaterEqual(cached.expires_at, started_at + CACHE_TTL)
        self.assertLessEqual(cached.expires_at, datetime.now() + CACHE_TTL)

    def test_clean_up_cache_hit(self):
        html = "<html><body><h1>Title</h1><p>Some content.</p></body></html>"
        cached = self.di.tools_cache_repo.save(domain.tools_cache(
            key = ToolsCache.create_key(CACHE_PREFIX, digest_md5(html)),
            value = "Processed Content",
            expires_at = datetime.now() + timedelta(days = 1),
        ))
        cleaner = self.di.html_content_cleaner(html)

        result = cleaner.clean_up()

        self.assertEqual(result, "Processed Content")
        self.assertEqual(self.di.tools_cache_repo.get(cached.key), cached)

    def test_clean_up_expired_cache(self):
        html = "<html><body><h1>Title</h1><p>Some content.</p></body></html>"
        cached = self.di.tools_cache_repo.save(domain.tools_cache(
            key = ToolsCache.create_key(CACHE_PREFIX, digest_md5(html)),
            expires_at = datetime.now() - timedelta(days = 1),
        ))
        cleaner = self.di.html_content_cleaner(html)

        result = cleaner.clean_up()

        self.assertIn("# Title", result)
        self.assertIn("Some content", result)
        refreshed = self.di.tools_cache_repo.get(cached.key)
        self.assertEqual(refreshed.value, result)
        self.assertFalse(refreshed.is_expired())

    def test_clean_up_markup_conversion(self):
        html = "<h1>Header1</h1><h2>Header2</h2><h3>Header3</h3><a href=\"https://example.com\">Link</a>"
        cleaner = self.di.html_content_cleaner(html)
        result = cleaner.clean_up()
        self.assertIn("# Header1", result)
        self.assertIn("## Header2", result)
        self.assertIn("### Header3", result)
        self.assertIn("Link", result)  # Links get removed by the Readability lib

    def test_clean_up_preserves_image_urls(self):
        html = (
            "<html><body><p>Text before</p>"
            '<img src="https://example.com/photo.png" alt="A photo"/>'
            '<img src="https://example.com/logo.png"/>'
            "<p>Text after</p></body></html>"
        )
        cleaner = self.di.html_content_cleaner(html)
        result = cleaner.clean_up()
        self.assertIn("![A photo](https://example.com/photo.png)", result)
        self.assertIn("![image](https://example.com/logo.png)", result)

    def test_clean_up_filters_noise_images(self):
        html = (
            "<html><body><p>Content</p>"
            '<img src="https://example.com/real.jpg" alt="Real photo"/>'
            '<img src="https://example.com/pixel.gif" width="1" height="1"/>'
            '<img src="https://example.com/spacer.png"/>'
            '<img src="data:image/gif;base64,R0lGODlh" alt="inline"/>'
            '<img src="https://example.com/decorative.png" role="presentation"/>'
            '<img src="https://example.com/tracking-beacon.png"/>'
            '<img src="https://cloudflareinsights.com/cdn-cgi/rum"/>'
            "<p>End</p></body></html>"
        )
        cleaner = self.di.html_content_cleaner(html)
        result = cleaner.clean_up()
        self.assertIn("![Real photo](https://example.com/real.jpg)", result)
        self.assertNotIn("pixel.gif", result)
        self.assertNotIn("spacer", result)
        self.assertNotIn("data:image", result)
        self.assertNotIn("decorative", result)
        self.assertNotIn("beacon", result)
        self.assertNotIn("cloudflareinsights", result)

    def test_remove_navigational_elements(self):
        html = "<nav>Navigation</nav><header>Header</header><menu>Menu</menu><div class=\"menu\">Menu div</div>"
        # noinspection PyUnresolvedReferences
        content = HTMLContentCleaner._HTMLContentCleaner__remove_menus(html)
        self.assertNotIn("Navigation", content)
        self.assertNotIn("Header", content)
        self.assertNotIn("Menu", content)
        self.assertNotIn("Menu div", content)
