import aiohttp
from aiohttp import ContentTypeError
import logging
import math
import asyncio
import json
from typing import Dict, Any, Optional, List
from .models import Card, CardSet

log = logging.getLogger("red.dlm.api")

class DLMAPIError(Exception):
    """Base exception for DLM API errors"""
    pass

class DLMNotFoundError(DLMAPIError):
    """Raised when a requested resource is not found"""
    pass

class DLMTimeoutError(DLMAPIError):
    """Raised when API request times out"""
    pass

class DLMConnectionError(DLMAPIError):
    """Raised when connection to API fails"""
    pass

class BaseGameAPI:
    def __init__(self, base_url: str):
        self.BASE_URL = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {
            'User-Agent': 'IP:Masquerena',
            'Accept': 'application/json'
        }
        self.RARITY_MAPPING = {
            "N": "normal",
            "R": "rare",
            "SR": "super",
            "UR": "ultra"
        }
        self.STATUS_MAPPING = {
            "Limited 2": "semilimited",
            "Limited 1": "limited",
            "Forbidden": "forbidden"
        }
        self.rate_limit = asyncio.Semaphore(5)

    async def initialize(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    async def _make_request(self, url: str, params: Optional[Dict] = None) -> Any:
        """Make a request to the API and handle different response types."""
        async with self.rate_limit:
            try:
                async with self.session.get(url, params=params, timeout=30) as resp:
                    if resp.status == 404:
                        raise DLMNotFoundError(f"Resource not found: {url}")
                    if resp.status != 200:
                        raise DLMAPIError(f"API request failed with status {resp.status}: {url}")
                    try:
                        return await resp.json()
                    except ContentTypeError:
                        text = await resp.text()
                        if text.isdigit():
                            return text
                        try:
                            import json
                            return json.loads(text)
                        except json.JSONDecodeError:
                            raise DLMAPIError(f"Invalid response format: {text[:100]}")

            except asyncio.TimeoutError:
                raise DLMTimeoutError(f"Request timed out: {url}")
            except aiohttp.ClientError as e:
                raise DLMConnectionError(f"Connection error: {str(e)}")

    async def get_card_amount(self) -> int:
        url = f"{self.BASE_URL}/cards"
        result = await self._make_request(url, {"collectionCount": "true"})
        return int(result)

    async def get_sets_amount(self) -> int:
        url = f"{self.BASE_URL}/sets"
        result = await self._make_request(url, {"collectionCount": "true"})
        return int(result)

    def _cast_set(self, resp: Dict[str, Any]) -> Dict[str, Any]:
        """Convert API response to set format with safe access."""
        if not resp:
            return None
        try:
            return {
                "id": resp.get("_id", "unknown"),
                "name": resp.get("name", "Unknown Set"),
                "type": resp.get("type", "unknown"),
                "url": self._get_set_link(
                    resp.get("linkedArticle", {}).get("url") if resp.get("linkedArticle") else None
                ),
                "image_url": None
            }
        except Exception as e:
            log.error(f"Error casting set data: {str(e)}")
            return None

    def _get_set_link(self, url_path: Optional[str]) -> Optional[str]:
        """Override in subclasses"""
        return None

class DLMApi(BaseGameAPI):
    def __init__(self):
        super().__init__("https://www.duellinksmeta.com/api/v1")

    async def get_card_details(self, card_id: str) -> Optional[Dict]:
        """Get card details from DLM."""
        try:
            url = f"{self.BASE_URL}/cards/detail"
            result = await self._make_request(url, {"id": card_id})
            return result
        except Exception as e:
            log.debug(f"Error getting DL card details: {str(e)}")
            return None

    async def get_latest_articles(self, limit: int = 3) -> List[Dict]:
        """Get latest articles from DLM."""
        try:
            url = f"{self.BASE_URL}/articles"
            result = await self._make_request(url, {"limit": limit, "sort": "-date"})
            return result if isinstance(result, list) else []
        except Exception as e:
            log.error(f"Error getting latest articles: {str(e)}")
            return []

    async def search_articles(self, query: str) -> List[Dict]:
        """Search articles by query."""
        try:
            url = f"{self.BASE_URL}/articles"
            result = await self._make_request(url, {"search": query})
            return result if isinstance(result, list) else []
        except Exception as e:
            log.error(f"Error searching articles: {str(e)}")
            return []

    async def search_decks(self, query: str) -> List[Dict]:
        """Search decks by name or archetype."""
        try:
            url = f"{self.BASE_URL}/decks"
            result = await self._make_request(url, {"search": query})
            return result if isinstance(result, list) else []
        except Exception as e:
            log.error(f"Error searching decks: {str(e)}")
            return []

    async def search_tournaments(self, query: str) -> List[Dict]:
        """Search tournaments by name."""
        try:
            url = f"{self.BASE_URL}/tournaments"
            result = await self._make_request(url, {"search": query})
            return result if isinstance(result, list) else []
        except Exception as e:
            log.error(f"Error searching tournaments: {str(e)}")
            return []

    async def get_meta_report(self, format_: str) -> Optional[Dict]:
        """Get meta report for a specific format."""
        try:
            url = f"{self.BASE_URL}/meta-reports"
            result = await self._make_request(url, {"format": format_})
            if isinstance(result, list) and result:
                return result[0]  # Return the most recent report
            return None
        except Exception as e:
            log.error(f"Error getting meta report: {str(e)}")
            return None

    async def get_latest_articles(self, limit: int = 3) -> List[Dict]:
        """Get latest articles from DLM."""
        try:
            url = f"{self.BASE_URL}/articles"
            result = await self._make_request(url, {"limit": limit, "sort": "-date"})
            return result if isinstance(result, list) else []
        except Exception as e:
            log.error(f"Error getting latest articles: {str(e)}")
            return []

    async def search_articles(self, query: str) -> List[Dict]:
        """Search articles by query."""
        try:
            url = f"{self.BASE_URL}/articles"
            result = await self._make_request(url, {"search": query})
            return result if isinstance(result, list) else []
        except Exception as e:
            log.error(f"Error searching articles: {str(e)}")
            return []

    async def search_decks(self, query: str) -> List[Dict]:
        """Search decks by name or archetype."""
        try:
            url = f"{self.BASE_URL}/decks"
            result = await self._make_request(url, {"search": query})
            return result if isinstance(result, list) else []
        except Exception as e:
            log.error(f"Error searching decks: {str(e)}")
            return []

    async def search_tournaments(self, query: str) -> List[Dict]:
        """Search tournaments by name."""
        try:
            url = f"{self.BASE_URL}/tournaments"
            result = await self._make_request(url, {"search": query})
            return result if isinstance(result, list) else []
        except Exception as e:
            log.error(f"Error searching tournaments: {str(e)}")
            return []

    async def get_meta_report(self, format_: str) -> Optional[Dict]:
        """Get meta report for a specific format."""
        try:
            url = f"{self.BASE_URL}/meta-reports"
            result = await self._make_request(url, {"format": format_})
            if isinstance(result, list) and result:
                return result[0]  # Return the most recent report
            return None
        except Exception as e:
            log.error(f"Error getting meta report: {str(e)}")
            return None

class MDMApi(BaseGameAPI):
    def __init__(self):
        super().__init__("https://www.masterduelmeta.com/api/v1")

    async def get_card_details(self, card_id: str) -> Optional[Dict]:
        """Get card details from MDM."""
        try:
            url = f"{self.BASE_URL}/cards/detail"
            result = await self._make_request(url, {"id": card_id})
            return result
        except Exception as e:
            log.debug(f"Error getting MD card details: {str(e)}")
            return None

class YGOProApi(BaseGameAPI):
    def __init__(self):
        super().__init__("https://db.ygoprodeck.com/api/v7")

    async def search_cards(self, name: str, exact: bool = False) -> List[Dict[str, Any]]:
        """Search for cards by name."""
        try:
            param_name = "name" if exact else "fname"
            url = f"{self.BASE_URL}/cardinfo.php"
            result = await self._make_request(url, {param_name: name})
            if result and isinstance(result, dict) and "data" in result:
                return result["data"]
            return []
        except Exception as e:
            log.error(f"Error searching cards: {str(e)}")
            return []
