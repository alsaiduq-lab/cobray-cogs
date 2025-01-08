import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

from ..core.abc import BooruSource
from ..core.exceptions import PostParseError, RequestError

log = logging.getLogger("red.booru.sources.yandere")


class YandereSource(BooruSource):
    """Yande.re API implementation."""

    def __init__(self, session, base_url: str = "https://yande.re"):
        super().__init__(session)
        self.base_url = base_url

    async def get_posts(
        self,
        tags: List[str],
        limit: int = 1,
        credentials: Optional[Dict[str, str]] = None,
    ) -> Union[List[Dict[str, Any]], None]:
        """Fetch posts from Yande.re."""
        params = {"tags": " ".join(tags), "limit": limit, "json": "1"}

        url = f"{self.base_url}/post.json?{urlencode(params)}"
        log.debug("Requesting URL: %s", url)

        try:
            async with self.session.get(url, ssl=True) as resp:
                if resp.status != 200:
                    log.error("HTTP %s from Yande.re", resp.status)
                    return None

                return await resp.json()

        except Exception as e:
            log.error("Error fetching from Yande.re: %s", e)
            return None

    def parse_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Yande.re post data into standardized format."""
        try:
            return {
                "id": str(post["id"]),
                "url": post["file_url"],
                "source": "yandere",
                "rating": post.get("rating", "unknown"),
                "tags": str(post.get("tags", "")).split(),
                "score": post.get("score"),
            }
        except KeyError as e:
            log.error("Error parsing Yande.re post: %s", e)
            raise PostParseError(f"Missing required field: {e}")
