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

    async def _make_request(self, url: str) -> Any:
        """Make a request to the API and handle different response types."""
        async with self.rate_limit:
            try:
                async with self.session.get(url, timeout=30) as resp:
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
        url = f"{self.BASE_URL}/cards?collectionCount=true"
        result = await self._make_request(url)
        return int(result)

    async def get_all_cards_raw(self) -> List[Dict[str, Any]]:
        cards_per_page = 3000
        total_cards = await self.get_card_amount()
        pages = math.ceil(total_cards / cards_per_page)

        tasks = []
        for page in range(1, pages + 1):
            url = f"{self.BASE_URL}/cards?limit={cards_per_page}&page={page}"
            tasks.append(self._make_request(url))

        responses = await asyncio.gather(*tasks)
        all_cards = []
        for cards in responses:
            filtered_cards = [
                card for card in cards
                if not card.get("alternateArt") and card.get("konamiID")
            ]
            all_cards.extend(filtered_cards)

        return all_cards

    async def get_sets_amount(self) -> int:
        url = f"{self.BASE_URL}/sets?collectionCount=true"
        result = await self._make_request(url)
        return int(result)

    async def get_all_sets(self) -> List[Dict[str, Any]]:
        """Get all sets data."""
        try:
            sets_per_page = 3000
            total_sets = await self.get_sets_amount()
            pages = math.ceil(total_sets / sets_per_page)

            all_sets = []
            for page in range(1, pages + 1):
                url = f"{self.BASE_URL}/sets?limit={sets_per_page}&page={page}"
                sets = await self._make_request(url)
                if sets:
                    all_sets.extend(sets)

            return [
                set_data for set_data in (self._cast_set(set_data) for set_data in all_sets)
                if set_data is not None
            ]
        except Exception as e:
            log.error(f"Error getting all sets: {str(e)}")
            return []

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

    def _cast_set(self, resp: Dict[str, Any]) -> Dict[str, Any]:
        data = super()._cast_set(resp)
        if data and resp.get('bannerImage'):
            data['image_url'] = f"https://s3.duellinksmeta.com{resp['bannerImage']}"
        return data

    def _get_set_link(self, url_path: Optional[str]) -> Optional[str]:
        if not url_path:
            return None
        return f"https://www.duellinksmeta.com/articles{url_path}"

class MDMApi(BaseGameAPI):
    def __init__(self):
        super().__init__("https://www.masterduelmeta.com/api/v1")

    def _cast_set(self, resp: Dict[str, Any]) -> Dict[str, Any]:
        data = super()._cast_set(resp)
        if data and resp.get('bannerImage'):
            data['image_url'] = f"https://s3.masterduelmeta.com{resp['bannerImage']}"
        return data

    def _get_set_link(self, url_path: Optional[str]) -> Optional[str]:
        if not url_path:
            return None
        return f"https://www.masterduelmeta.com/articles{url_path}"

class YGOProApi(BaseGameAPI):
    def __init__(self):
        super().__init__("https://db.ygoprodeck.com/api/v7")
