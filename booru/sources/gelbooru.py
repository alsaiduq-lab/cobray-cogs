import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

from ..core.abc import BooruSource, PostResult
from ..core.exceptions import CredentialsRequired, PostParseError, RequestError

log = logging.getLogger("red.booru.sources.gelbooru")


class GelbooruSource(BooruSource):
    """Gelbooru API implementation."""

    def __init__(self, session, base_url: str = "https://gelbooru.com/index.php"):
        super().__init__(session)
        self.base_url = base_url

    async def get_posts(
        self,
        tags: List[str],
        limit: int = 1,
        credentials: Optional[Dict[str, str]] = None,
    ) -> Union[List[Dict[str, Any]], None]:
        """Fetch posts from Gelbooru."""
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": 1,
            "limit": limit,
            "tags": " ".join(tags),
        }

        # Add API credentials if provided
        if credentials:
            api_key = credentials.get("api_key")
            user_id = credentials.get("user_id")
            if api_key and user_id:
                params.update({"api_key": api_key, "user_id": user_id})
            else:
                log.warning("Incomplete credentials provided for Gelbooru")

        url = f"{self.base_url}?{urlencode(params)}"
        log.debug("Requesting URL: %s", url)

        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, dict):
                        return data.get("post", [])
                    return data
                raise RequestError(f"HTTP {resp.status} from Gelbooru")
        except Exception as e:
            log.error("Error fetching from Gelbooru: %s", e)
            raise RequestError(str(e))

    def parse_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Gelbooru post data into standardized format."""
        try:
            return PostResult(
                id=str(post["id"]),
                url=post["file_url"],
                source="gelbooru",
                rating=post.get("rating", "unknown"),
                tags=str(post.get("tags", "")).split(),
                score=post.get("score"),
            ).to_dict()
        except KeyError as e:
            log.error("Error parsing Gelbooru post: %s", e)
            raise PostParseError(f"Missing required field: {e}")
