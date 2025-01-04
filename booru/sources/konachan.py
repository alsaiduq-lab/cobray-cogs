import logging
from typing import Optional, Dict, List, Any, Union
from urllib.parse import urlencode

from ..core.abc import BooruSource, PostResult
from ..core.exceptions import RequestError, PostParseError

log = logging.getLogger("red.booru.sources.konachan")

class KonachanSource(BooruSource):
    """Konachan API implementation."""
    
    def __init__(self, session, base_url: str = "https://konachan.com"):
        super().__init__(session)
        self.base_url = base_url
        
    async def get_posts(
        self,
        tags: List[str],
        limit: int = 1,
        credentials: Optional[Dict[str, str]] = None
    ) -> Union[List[Dict[str, Any]], None]:
        """Fetch posts from Konachan."""
        params = {
            "tags": " ".join(tags),
            "limit": limit,
            "json": "1"
        }
        
        url = f"{self.base_url}/post.json?{urlencode(params)}"
        log.debug("Requesting URL: %s", url)
        
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                raise RequestError(f"HTTP {resp.status} from Konachan")
        except Exception as e:
            log.error("Error fetching from Konachan: %s", e)
            raise RequestError(str(e))
            
    def parse_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Konachan post data into standardized format."""
        try:
            return PostResult(
                id=str(post["id"]),
                url=post["file_url"],
                source="konachan",
                rating=post.get("rating", "unknown"),
                tags=str(post.get("tags", "")).split(),
                score=post.get("score")
            ).to_dict()
        except KeyError as e:
            log.error("Error parsing Konachan post: %s", e)
            raise PostParseError(f"Missing required field: {e}")
