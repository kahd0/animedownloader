from __future__ import annotations
from app.models.release import Release
from app.providers.base import RSSProvider
from app.providers.rss.subsplease import _parse_rss_url


class GenericRSSProvider(RSSProvider):
    """User-configured RSS feed with optional {show} placeholder in URL."""

    name = "generic"

    def __init__(self, feed_name: str, feed_url: str, priority: int = 50):
        self.name = feed_name
        self._url = feed_url
        self.priority = priority

    async def fetch_releases(self, show_name: str) -> list[Release]:
        url = self._url
        if "{show}" in url:
            url = url.replace("{show}", show_name.replace(" ", "+"))
        return await _parse_rss_url(url, self.name)
