import logging
import asyncio
from typing import Dict, List, Optional, Set
from .api import DLMApi, MDMApi
from .ygopro import YGOProAPI
from .models import Card, Set as CardSet
from ..utils.images import ImagePipeline

log = logging.getLogger("red.dlm.cardmanager")

class CardManager:
    """Manages card data from multiple sources and keeps it in sync."""
    def __init__(self):
        self.dlm_api = DLMApi()
        self.mdm_api = MDMApi()
        self.ygopro_api = YGOProAPI()
        self.image_pipeline = ImagePipeline()
        self.cards: Dict[str, Card] = {}
        self.sets_dl: Dict[str, CardSet] = {}
        self.sets_md: Dict[str, CardSet] = {}
        self._last_update = None
        self._updating = False

    async def initialize(self):
        """Initialize all APIs and load initial data."""
        await asyncio.gather(
            self.dlm_api.initialize(),
            self.mdm_api.initialize(),
            self.ygopro_api.initialize(),
            self.image_pipeline.initialize()
        )
        await self.update_data()

    async def close(self):
        """Clean up all API connections."""
        await asyncio.gather(
            self.dlm_api.close(),
            self.mdm_api.close(),
            self.ygopro_api.close(),
            self.image_pipeline.close()
        )

    async def update_data(self):
        """Update card data from all sources."""
        if self._updating:
            return
        self._updating = True
        try:
            dlm_cards = await self.dlm_api.get_all_cards_raw()
            mdm_cards = await self.mdm_api.get_all_cards_raw()
            dlm_by_id = {str(card["konamiID"]): card for card in dlm_cards}
            mdm_by_id = {str(card["konamiID"]): card for card in mdm_cards}
            card_ids = set(dlm_by_id.keys()) | set(mdm_by_id.keys())
            for card_id in card_ids:
                card = await self.ygopro_api.get_card_info(card_id)
                if card:
                    if card_id in dlm_by_id:
                        dlm_data = dlm_by_id[card_id]
                        card.status_dl = self.dlm_api.STATUS_MAPPING.get(dlm_data.get("banStatus"))
                        card.rarity_dl = self.dlm_api.RARITY_MAPPING.get(dlm_data.get("rarity"))
                        card.sets_dl = [src["source"]["_id"] for src in dlm_data.get("obtain", [])]
                    if card_id in mdm_by_id:
                        mdm_data = mdm_by_id[card_id]
                        card.status_md = self.mdm_api.STATUS_MAPPING.get(mdm_data.get("banStatus"))
                        card.rarity_md = self.mdm_api.RARITY_MAPPING.get(mdm_data.get("rarity"))
                        card.sets_md = [src["source"]["_id"] for src in mdm_data.get("obtain", [])]
                    card.has_ocg_art = await self.image_pipeline.is_ocg_available(card_id)
                    self.cards[card_id] = card
            self.sets_dl = {set_data.id: set_data for set_data in await self.dlm_api.get_all_sets()}
            self.sets_md = {set_data.id: set_data for set_data in await self.mdm_api.get_all_sets()}
        except Exception as e:
            log.error(f"Error updating card data: {str(e)}")
        finally:
            self._updating = False

    async def get_card(self, card_id: str) -> Optional[Card]:
        """Get card by ID."""
        return self.cards.get(card_id)

    async def search_cards(self, query: str, fuzzy: bool = True) -> List[Card]:
        """Search for cards by name."""
        if not query:
            return []
        cards = await self.ygopro_api.search_cards(query, fuzzy)
        for card in cards:
            if card.id in self.cards:
                stored_card = self.cards[card.id]
                card.status_dl = stored_card.status_dl
                card.rarity_dl = stored_card.rarity_dl
                card.sets_dl = stored_card.sets_dl
                card.status_md = stored_card.status_md
                card.rarity_md = stored_card.rarity_md
                card.sets_md = stored_card.sets_md
                card.has_ocg_art = stored_card.has_ocg_art
        return cards

    async def get_card_image(self, card_id: str, ocg: bool = False) -> Optional[str]:
        """Get card image URL."""
        card = await self.get_card(card_id)
        if not card:
            return None
        success, url = await self.image_pipeline.get_image_url(
            card_id,
            card.monster_types or [],
            ocg
        )
        return url if success else None
