import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

from ..core.abc import BooruSource, PostResult
from ..core.exceptions import PostParseError, RequestError

log = logging.getLogger("red.booru")


class DanbooruSource(BooruSource):
    """Danbooru API implementation."""

    def __init__(self, session, base_url: str = "https://danbooru.donmai.us"):
        super().__init__(session)
        self.base_url = base_url

    async def get_posts(
        self,
        tags: List[str],
        limit: int = 1,
        credentials: Optional[Dict[str, str]] = None,
    ) -> Union[List[Dict[str, Any]], None]:
        """Fetch posts from Danbooru."""
        params = {"tags": " ".join(tags), "limit": limit, "random": "true"}
        url = f"{self.base_url}/posts.json?{urlencode(params)}"
        log.debug("Danbooru API tags: %r", tags)
        log.debug("Requesting URL: %s", url)

        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                raise RequestError(f"HTTP {resp.status} from Danbooru")
        except Exception as e:
            log.error("Error fetching from Danbooru: %s", e)
            raise RequestError(str(e))

    def parse_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Danbooru post data into standardized format."""
        try:
            file_url = post.get("file_url") or post.get("large_file_url")
            if file_url and not isinstance(file_url, str):
                file_url = str(file_url)
            if file_url and not file_url.startswith("http"):
                file_url = f"{self.base_url}{file_url}"
            if file_url is None:
                file_url = ""
            return PostResult(
                id=str(post["id"]),
                url=file_url,
                source="danbooru",
                rating=post.get("rating", "unknown"),
                tags=post.get("tag_string", "").split(),
                score=post.get("score", 0),
            ).to_dict()
        except KeyError as e:
            log.error("Error parsing Danbooru post: %s", e)
            raise PostParseError(f"Missing required field: {e}")
