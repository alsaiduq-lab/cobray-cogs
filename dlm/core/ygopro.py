import logging
from typing import Dict, List, Optional, Any
from .models import Card
from .api import BaseGameAPI

log = logging.getLogger("red.dlm.ygopro")

class YGOProAPI(BaseGameAPI):
    def __init__(self):
        super().__init__("https://db.ygoprodeck.com/api/v7")

    async def get_card_info(self, card_id: str) -> Optional[Card]:
        """Get detailed card information from YGOPRODeck."""
        try:
            result = await self._make_request(
                f"{self.BASE_URL}/cardinfo.php",
                {"id": card_id}
            )
            if result and "data" in result:
                return self._parse_card_data(result["data"][0])
        except Exception as e:
            log.error(f"Error fetching card info: {str(e)}")
        return None

    async def get_card_sets(self, card_name: str) -> List[Dict[str, str]]:
        """Get all sets a card appears in."""
        try:
            result = await self._make_request(
                f"{self.BASE_URL}/cardinfo.php",
                {"name": card_name}
            )
            if result and "data" in result:
                return result["data"][0].get("card_sets", [])
        except Exception as e:
            log.error(f"Error fetching card sets: {str(e)}")
        return []

    async def search_cards(self, query: str, fuzzy: bool = True) -> List[Card]:
        """Search for cards by name."""
        try:
            param_name = "fname" if fuzzy else "name"
            result = await self._make_request(
                f"{self.BASE_URL}/cardinfo.php",
                {param_name: query}
            )
            if result and "data" in result:
                return [self._parse_card_data(card) for card in result["data"]]
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
