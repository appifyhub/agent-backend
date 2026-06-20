import re
from datetime import datetime, timedelta

from readabilipy import simple_json_from_html_string

from di.di import DI
from features.tools_cache.tools_cache import ToolsCache
from util import log
from util.functions import digest_md5

CACHE_PREFIX = "html-content-cleaner"
CACHE_TTL = timedelta(weeks = 52)


class HTMLContentCleaner:

    raw_html: str
    plain_text: str
    __di: DI

    def __init__(
        self,
        raw_html: str,
        di: DI,
    ):
        self.raw_html = raw_html
        self.plain_text = ""
        self.__di = di

    def clean_up(self) -> str:
        self.plain_text = ""  # reset value

        cache_key = ToolsCache.create_key(CACHE_PREFIX, digest_md5(self.raw_html))
        cache_entry = self.__di.tools_cache_repo.get(cache_key)
        if cache_entry:
            if not cache_entry.is_expired():
                log.t(f"Cache hit for '{cache_key}'")
                self.plain_text = cache_entry.value
                return self.plain_text
            log.t(f"Cache expired for '{cache_key}'")
        log.t(f"Cache miss for '{cache_key}'")

        # extract image URLs from raw HTML before readabilipy strips them
        image_markdowns = self.__extract_images(self.raw_html)

        content_json = simple_json_from_html_string(self.raw_html)
        log.t(f"Processed HTML, received {len(content_json)} content items")
        # replace HTML markers with Markdown markers
        self.plain_text = re.sub(r"<h1>(.*?)</h1>", r"\n# \1\n", str(content_json["plain_content"]))
        self.plain_text = re.sub(r"<h2>(.*?)</h2>", r"\n## \1\n", self.plain_text)
        self.plain_text = re.sub(r"<h3>(.*?)</h3>", r"\n### \1\n", self.plain_text)
        self.plain_text = re.sub(r"<h4>(.*?)</h4>", r"\n#### \1\n", self.plain_text)
        self.plain_text = re.sub(r"<h5>(.*?)</h5>", r"\n##### \1\n", self.plain_text)
        self.plain_text = re.sub(r"<h6>(.*?)</h6>", r"\n###### \1\n", self.plain_text)
        self.plain_text = re.sub(r"<a\s+(?:[^>]*?\s+)?href=\"([^\"]*)\"[^>]*>(.*?)</a>", r"[\2](\1)", self.plain_text)
        # clean other tags
        self.plain_text = self.__remove_menus(self.plain_text)  # navigation components
        self.plain_text = re.sub(r"<li>(.*?)</li>", r"\n- \1\n", self.plain_text)  # list items
        self.plain_text = re.sub(r"<[ou]l>\s*</[ou]l>", "", self.plain_text)  # empty lists
        self.plain_text = re.sub(r"<[^>]+>", " ", self.plain_text)  # remove remaining tags
        # remove extra whitespace
        self.plain_text = re.sub(r"\n\s*\n+", "\n", self.plain_text)  # empty newlines
        self.plain_text = re.sub(r"[ \t]+", " ", self.plain_text).strip()  # horizontal spaces
        # append image links extracted from raw HTML
        if image_markdowns:
            self.plain_text += "\n" + "\n".join(image_markdowns)
        # finally cache the cleaned content for future use
        self.__di.tools_cache_repo.save(
            ToolsCache(
                key = cache_key,
                value = self.plain_text,
                expires_at = datetime.now() + CACHE_TTL,
            ),
        )
        log.t(f"Cleaned up HTML contents, received {len(self.plain_text)} content items")
        return self.plain_text

    @staticmethod
    def __extract_images(html: str) -> list[str]:
        results: list[str] = []
        seen_base_urls: set[str] = set()
        for match in re.finditer(r"<img\s+[^>]*?src=[\"']([^\"']+)[\"'][^>]*?>", html, re.IGNORECASE):
            tag = match.group(0)
            src = match.group(1)
            if HTMLContentCleaner.__is_noise_image(tag, src):
                continue
            base_url = src.split("?")[0]
            if base_url in seen_base_urls:
                continue
            seen_base_urls.add(base_url)
            alt_match = re.search(r"alt=[\"']([^\"']*)[\"']", tag, re.IGNORECASE)
            alt = alt_match.group(1) if alt_match and alt_match.group(1) else "image"
            results.append(f"![{alt}]({src})")
        return results

    @staticmethod
    def __is_noise_image(tag: str, src: str) -> bool:
        # tracking pixels and tiny icons
        width_match = re.search(r"width=[\"']?(\d+)", tag, re.IGNORECASE)
        height_match = re.search(r"height=[\"']?(\d+)", tag, re.IGNORECASE)
        if width_match and height_match:
            w, h = int(width_match.group(1)), int(height_match.group(1))
            if w <= 3 or h <= 3:
                return True
        # decorative images
        if re.search(r"role=[\"']presentation[\"']", tag, re.IGNORECASE):
            return True
        # data URIs (inline base64 blobs)
        if src.startswith("data:"):
            return True
        # analytics and tracking domains
        noise_domains = [
            "google-analytics.com", "googletagmanager.com", "googlesyndication.com", "googleadservices.com",
            "doubleclick.net", "adservice.google",
            "facebook.com/tr", "facebook.net", "analytics.", "pixel.",
            "ads.linkedin.com", "cloudflareinsights.com", "bat.bing.com", "tr.snapchat.com",
            "quantserve.com", "scorecardresearch.com",
            "adnxs.com", "adsrvr.org", "openx.net", "demdex.net",
        ]
        src_lower = src.lower()
        if any(d in src_lower for d in noise_domains):
            return True
        # common noise filename patterns
        noise_patterns = ["spacer", "pixel", "tracking", "beacon", "blank.gif", "1x1"]
        return any(p in src_lower for p in noise_patterns)

    @staticmethod
    def __remove_menus(html):
        patterns = [
            r"<nav\b[^>]*>.*?</nav>",
            r"<header\b[^>]*>.*?</header>",
            r"<menu\b[^>]*>.*?</menu>",
            r'<div\b[^>]*class=["\'](?:[^"\']*)(?:menu|navigation|navbar|nav-bar|nav)(?:[^"\']*)["\'][^>]*>.*?</div>',
            r'<ul\b[^>]*class=["\'](?:[^"\']*)(?:menu|navigation|navbar|nav-bar|nav)(?:[^"\']*)["\'][^>]*>.*?</ul>',
            r'<div\b[^>]*id=["\'](?:menu|nav)(?:[^"\']*)["\'][^>]*>.*?</div>',
        ]
        result = html
        for pattern in patterns:
            result = re.sub(pattern, "", result, flags = re.DOTALL | re.IGNORECASE)
        return result
