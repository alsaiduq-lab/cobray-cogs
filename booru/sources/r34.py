import logging
from typing import Optional, Dict, List, Any, Union
from urllib.parse import urlencode

from ..core.abc import BooruSource, PostResult
from ..core.exceptions import RequestError, PostParseError

log = logging.getLogger("red.booru.sources.rule34")


class Rule34Source(BooruSource):
    """Rule34 API implementation."""

    def __init__(self, session, base_url: str = "https://api.rule34.xxx"):
        super().__init__(session)
        self.base_url = base_url

    async def get_posts(
        self,
        tags: List[str],
        limit: int = 1,
        credentials: Optional[Dict[str, str]] = None
    ) -> Union[List[Dict[str, Any]], None]:
        """
        Fetch posts from Rule34.xxx. This site uses the basic Gelbooru-like API.
        The 'limit' param can be up to 100 at once, no random param.
        """
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": 1,
            "tags": " ".join(tags),
            "limit": limit,
        }
        url = f"{self.base_url}/index.php?{urlencode(params)}"

        log.debug("Requesting URL: %s", url)
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                raise RequestError(f"HTTP {resp.status} from Rule34")
        except Exception as e:
            log.error("Error fetching from Rule34: %s", e)
            raise RequestError(str(e))

    def parse_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Rule34 post data into standardized format."""
        try:
            # 'file_url' or 'sample_url' might exist
            file_url = post.get("file_url")
            return PostResult(
                id=str(post["id"]),
                url=file_url,
                source="rule34",
                rating=post.get("rating", "unknown"),
                tags=post.get("tags", "").split(),
                score=int(post.get("score", 0))
            ).to_dict()
        except KeyError as e:
            log.error("Error parsing Rule34 post: %s", e)
            raise PostParseError(f"Missing required field: {e}")
