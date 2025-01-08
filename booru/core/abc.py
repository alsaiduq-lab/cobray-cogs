from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

import aiohttp


class BooruSource(ABC):
    """Abstract base class for booru sources."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    @abstractmethod
    async def get_posts(
        self,
        tags: List[str],
        limit: int = 1,
        credentials: Optional[Dict[str, str]] = None,
    ) -> Union[List[Dict[str, Any]], None]:
        """Get posts from the booru source."""
        pass

    @abstractmethod
    def parse_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw post data into standardized format."""
        pass


class PostResult:
    """Standardized post result format."""

    def __init__(
        self,
        id: str,
        url: str,
        source: str,
        rating: str,
        tags: List[str],
        score: Optional[int] = None,
    ):
        self.id = id
        self.url = url
        self.source = source
        self.rating = rating
        self.tags = tags
        self.score = score

    def to_dict(self) -> Dict[str, Any]:
        """Convert post to dictionary format."""
        return {
            "id": self.id,
            "url": self.url,
            "source": self.source,
            "rating": self.rating,
            "tags": self.tags,
            "score": self.score,
        }
