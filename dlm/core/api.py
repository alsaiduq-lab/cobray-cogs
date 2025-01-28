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
        # Regular timeout
        self.timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_read=7)
        # Shorter timeout for autocomplete
        self.autocomplete_timeout = aiohttp.ClientTimeout(total=1.5, connect=0.5, sock_read=1.0)
        # Rate limits
        self.rate_limit = asyncio.Semaphore(10)
        self.autocomplete_rate_limit = asyncio.Semaphore(15)

    async def initialize(self):
        """Initialize with proper timeout settings"""
        self.session = aiohttp.ClientSession(headers=self.headers)

    async def close(self):
        if self.session:
            await self.session.close()

    async def _make_request(self, url: str, params: Optional[Dict] = None, request_headers: Optional[Dict] = None) -> Any:
        """Make a request to the API with better error handling."""
        async with self.rate_limit:
            try:
                # Merge default headers with request-specific headers
                headers = self.headers.copy()
                if request_headers:
                    headers.update(request_headers)
                    
                # Reduce sleep time for autocomplete responsiveness
                await asyncio.sleep(0.5)  # Reduced from 2
                async with self.session.get(url, params=params, headers=headers) as resp:
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
                            return json.loads(text)
                        except json.JSONDecodeError:
                            raise DLMAPIError(f"Invalid response format: {text[:100]}")

            except asyncio.TimeoutError:
                log.warning(f"Request timed out: {url}")
                raise DLMTimeoutError(f"Request timed out: {url}")
            except aiohttp.ClientError as e:
                log.error(f"Connection error: {str(e)}")
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
            url = f"{self.BASE_URL}/top-decks"
            result = await self._make_request(url, {"search": query})
            return result if isinstance(result, list) else []
        except Exception as e:
            log.error(f"Error searching decks: {str(e)}")
            return []

    async def search_tournaments(self, query: str) -> List[Dict]:
        """Search tournaments by name."""
        try:
            url = f"{self.BASE_URL}/tournaments"
            result = await self._make_request(url, {"search": query, "sort": "-date"})
            return result if isinstance(result, list) else []
        except Exception as e:
            log.error(f"Error searching tournaments: {str(e)}")
            return []

    async def get_recent_tournaments(self, limit: int = 5) -> List[Dict]:
        """Get recent tournaments."""
        try:
            url = f"{self.BASE_URL}/tournaments"
            result = await self._make_request(url, {"limit": limit, "sort": "-date"})
            return result if isinstance(result, list) else []
        except Exception as e:
            log.error(f"Error getting recent tournaments: {str(e)}")
            return []

    async def get_meta_report(self, format_: str) -> Optional[Dict]:
        """Get meta report for a specific format."""
        try:
            url = f"{self.BASE_URL}/meta-reports"
            result = await self._make_request(url, {"format": format_})
            if isinstance(result, list) and result:
                return result[0]
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
        # Separate rate limit for autocomplete
        self.autocomplete_rate_limit = asyncio.Semaphore(15)

    async def search_cards(self, name: str, exact: bool = False, is_autocomplete: bool = False) -> List[Dict[str, Any]]:
        """Search for cards by name with autocomplete optimization."""
        try:
            param_name = "name" if exact else "fname"
            url = f"{self.BASE_URL}/cardinfo.php"
            
            # Use different rate limiting for autocomplete
            rate_limiter = self.autocomplete_rate_limit if is_autocomplete else self.rate_limit
            
            async with rate_limiter:
                # Skip sleep for autocomplete requests
                if not is_autocomplete:
                    await asyncio.sleep(0.5)
                    
                async with self.session.get(url, params={param_name: name}) as resp:
                    if resp.status != 200:
                        if resp.status == 400 and is_autocomplete:
                            # Silently fail for autocomplete requests
                            return []
                        raise DLMAPIError(f"API request failed with status {resp.status}: {url}")
                    
                    result = await resp.json()
                    if result and isinstance(result, dict) and "data" in result:
                        return result["data"]
                    return []
                    
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            if is_autocomplete:
                # Silently fail for autocomplete
                return []
            log.error(f"Error searching cards: {str(e)}")
            return []
