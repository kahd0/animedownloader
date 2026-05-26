from __future__ import annotations
from app.models.release import Release
from app.providers.base import RSSProvider
from app.providers.rss.subsplease import _parse_rss_url

_ERAI_RSS = "https://www.erai-raws.info/episodes/feed/?s={show}"


class EraiRawsProvider(RSSProvider):
    name = "Erai-raws"

    async def fetch_releases(self, show_name: str) -> list[Release]:
        url = _ERAI_RSS.replace("{show}", show_name.replace(" ", "+"))
        return await _parse_rss_url(url, self.name)
