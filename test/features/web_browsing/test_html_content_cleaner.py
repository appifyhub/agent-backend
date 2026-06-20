import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from di.di import DI
from features.tools_cache.tools_cache import ToolsCache
from features.tools_cache.tools_cache_repo import ToolsCacheRepository
from features.web_browsing.html_content_cleaner import CACHE_TTL, HTMLContentCleaner


class HTMLContentCleanerTest(unittest.TestCase):

    mock_di: DI
    mock_cache_repo: ToolsCacheRepository
    sample_html: str
    cache_entry: ToolsCache

    def setUp(self):
        self.mock_cache_repo = MagicMock(spec = ToolsCacheRepository)
        self.sample_html = "<html><body><h1>Title</h1><p>Some content.</p></body></html>"
        self.cache_entry = ToolsCache(
            key = "test_cache_key",
            value = "Processed Content",
            expires_at = datetime.now() + CACHE_TTL,
        )
        self.mock_di = MagicMock(spec = DI)
        # noinspection PyPropertyAccess
        self.mock_di.tools_cache_repo = self.mock_cache_repo

    def test_clean_up_cache_miss(self):
        self.mock_cache_repo.get.return_value = None
        cleaner = HTMLContentCleaner(self.sample_html, self.mock_di)
        result = cleaner.clean_up()
        self.assertIn("# Title", result)
        self.assertIn("Some content", result)
        # noinspection PyUnresolvedReferences
        self.mock_cache_repo.save.assert_called_once()

    def test_clean_up_cache_hit(self):
        self.mock_cache_repo.get.return_value = self.cache_entry
        cleaner = HTMLContentCleaner(self.sample_html, self.mock_di)
        result = cleaner.clean_up()
        self.assertEqual(result, "Processed Content")
        # noinspection PyUnresolvedReferences
        self.mock_cache_repo.save.assert_not_called()

    def test_clean_up_expired_cache(self):
        expired_cache_entry = ToolsCache(
            key = "test_cache_key",
            value = "Processed Content",
            expires_at = datetime.now() - timedelta(days = 1),  # Expired cache
        )
        self.mock_cache_repo.get.return_value = expired_cache_entry
        cleaner = HTMLContentCleaner(self.sample_html, self.mock_di)
        result = cleaner.clean_up()
        self.assertIn("# Title", result)
        self.assertIn("Some content", result)
        # noinspection PyUnresolvedReferences
        self.mock_cache_repo.save.assert_called_once()

    def test_clean_up_markup_conversion(self):
        html = "<h1>Header1</h1><h2>Header2</h2><h3>Header3</h3><a href=\"https://example.com\">Link</a>"
        self.mock_cache_repo.get.return_value = None  # Simulate cache miss
        cleaner = HTMLContentCleaner(html, self.mock_di)
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
        self.mock_cache_repo.get.return_value = None
        cleaner = HTMLContentCleaner(html, self.mock_di)
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
        self.mock_cache_repo.get.return_value = None
        cleaner = HTMLContentCleaner(html, self.mock_di)
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
