# core/api.py
import aiohttp
import logging
import math
import asyncio
from typing import Dict, Any, Optional, List
from .cache import DLMCache, DLMAPIError

log = logging.getLogger("red.dlm.api")

class BaseGameAPI:
    def __init__(self, base_url: str):
        self.BASE_URL = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache = DLMCache()
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

    async def initialize(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    async def get_card_amount(self) -> int:
        url = f"{self.BASE_URL}/cards?collectionCount=true"
        async with self.session.get(url) as resp:
            if resp.status == 200:
                return int(await resp.text())
            raise DLMAPIError(f"Failed to get card amount: {resp.status}")

    async def get_all_cards_raw(self) -> List[Dict[str, Any]]:
        cards_per_page = 3000
        total_cards = await self.get_card_amount()
        pages = math.ceil(total_cards / cards_per_page)

        tasks = []
        for page in range(1, pages + 1):
            url = f"{self.BASE_URL}/cards?limit={cards_per_page}&page={page}"
            tasks.append(self.session.get(url))

        responses = await asyncio.gather(*tasks)
        all_cards = []
        for resp in responses:
            cards = await resp.json()
            filtered_cards = [
                card for card in cards
                if not card.get("alternateArt") and card.get("konamiID")
            ]
            all_cards.extend(filtered_cards)

        return all_cards

    async def get_sets_amount(self) -> int:
        url = f"{self.BASE_URL}/sets?collectionCount=true"
        async with self.session.get(url) as resp:
            if resp.status == 200:
                return int(await resp.text())
            raise DLMAPIError(f"Failed to get sets amount: {resp.status}")

    async def get_all_sets(self) -> List[Dict[str, Any]]:
        sets_per_page = 3000
        total_sets = await self.get_sets_amount()
        pages = math.ceil(total_sets / sets_per_page)

        all_sets = []
        for page in range(1, pages + 1):
            url = f"{self.BASE_URL}/sets?limit={sets_per_page}&page={page}"
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    sets = await resp.json()
                    all_sets.extend(sets)
                else:
                    raise DLMAPIError(f"Failed to get sets: {resp.status}")

        return [self._cast_set(set_data) for set_data in all_sets]

    def _cast_set(self, resp: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": resp["_id"],
            "name": resp["name"],
            "type": resp["type"],
            "url": self._get_set_link(resp.get("linkedArticle", {}).get("url")),
            "image_url": f"https://s3.duellinksmeta.com{resp['bannerImage']}"
        }

    def _get_set_link(self, url_path: Optional[str]) -> Optional[str]:
        if not url_path:
            return None
        base = "https://www.duellinksmeta.com/articles"
        return f"{base}{url_path}"

class DLMApi(BaseGameAPI):
    def __init__(self):
        super().__init__("https://www.duellinksmeta.com/api/v1")

class MDMApi(BaseGameAPI):
    def __init__(self):
        super().__init__("https://www.masterduelmeta.com/api/v1")
        
    def _get_set_link(self, url_path: Optional[str]) -> Optional[str]:
        if not url_path:
            return None
        base = "https://www.masterduelmeta.com/articles"
        return f"{base}{url_path}"
