import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

from ..core.abc import BooruSource, PostResult
from ..core.exceptions import PostParseError, RequestError

log = logging.getLogger("red.booru.sources.safebooru")


class SafebooruSource(BooruSource):
    """Safebooru API implementation."""

    def __init__(self, session, base_url: str = "https://safebooru.org"):
        super().__init__(session)
        self.base_url = base_url

    async def get_posts(
        self,
        tags: List[str],
        limit: int = 1,
        credentials: Optional[Dict[str, str]] = None,
    ) -> Union[List[Dict[str, Any]], None]:
        """Fetch posts from Safebooru."""
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": 1,
            "limit": limit,
            "tags": " ".join(tags),
        }

        url = f"{self.base_url}/index.php?{urlencode(params)}"
        log.debug("Requesting URL: %s", url)

        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, dict):
                        return data.get("post", [])
                    return data
                raise RequestError(f"HTTP {resp.status} from Safebooru")
        except Exception as e:
            log.error("Error fetching from Safebooru: %s", e)
            raise RequestError(str(e))

    def parse_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Safebooru post data into standardized format."""
        try:
            # Safebooru URLs need to be constructed
            file_url = post.get("file_url")
            if file_url and not file_url.startswith("http"):
                file_url = f"https:{file_url}"

            return PostResult(
                id=str(post["id"]),
                url=file_url,
                source="safebooru",
                rating="safe",  # Safebooru is always safe
                tags=str(post.get("tags", "")).split(),
                score=post.get("score"),
            ).to_dict()
        except KeyError as e:
            log.error("Error parsing Safebooru post: %s", e)
            raise PostParseError(f"Missing required field: {e}")
