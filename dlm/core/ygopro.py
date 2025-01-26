import aiohttp
import logging
from typing import Dict, List, Optional, Any
from .models import Card

log = logging.getLogger("red.dlm.ygopro")

class YGOProAPI:
    BASE_URL = "https://db.ygoprodeck.com/api/v7"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        self.session = aiohttp.ClientSession()
    
    async def close(self):
        if self.session:
            await self.session.close()

    async def get_card_info(self, card_id: str) -> Optional[Card]:
        """Get detailed card information from YGOPRODeck."""
        if not self.session:
            await self.initialize()
            
        url = f"{self.BASE_URL}/cardinfo.php"
        params = {"id": card_id}
        
        try:
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("data"):
                        return self._parse_card_data(data["data"][0])
        except Exception as e:
            log.error(f"Error fetching card info: {str(e)}")
        return None

    async def get_card_sets(self, card_name: str) -> List[Dict[str, str]]:
        """Get all sets a card appears in."""
        if not self.session:
            await self.initialize()
            
        url = f"{self.BASE_URL}/cardinfo.php"
        params = {"name": card_name}
        
        try:
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("data"):
                        return data["data"][0].get("card_sets", [])
        except Exception as e:
            log.error(f"Error fetching card sets: {str(e)}")
        return []

    async def search_cards(self, query: str, fuzzy: bool = True) -> List[Card]:
        """Search for cards by name."""
        if not self.session:
            await self.initialize()
            
        url = f"{self.BASE_URL}/cardinfo.php"
        params = {"fname" if fuzzy else "name": query}
        
        try:
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [self._parse_card_data(card) for card in data.get("data", [])]
        except Exception as e:
            log.error(f"Error searching cards: {str(e)}")
        return []

    def _parse_card_data(self, data: Dict[str, Any]) -> Card:
        """Parse YGOPRODeck card data into Card model."""
        monster_types = []
        if "type" in data:
            monster_types = [t.strip() for t in data["type"].split("/")]
            
        return Card(
            id=str(data["id"]),
            name=data["name"],
            description=data["desc"],
            type=data["type"],
            race=data.get("race"),
            attribute=data.get("attribute"),
            atk=data.get("atk"),
            def_=data.get("def"),
            level=data.get("level"),
            scale=data.get("scale"),
            link_value=data.get("linkval"),
            link_markers=data.get("linkmarkers", []),
            monster_types=monster_types,
            tcg_date=data.get("tcg_date"),
            ocg_date=data.get("ocg_date"),
            has_ocg_art=False  # Will be updated by image check
        )
