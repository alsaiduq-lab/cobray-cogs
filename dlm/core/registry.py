import logging
import asyncio
from typing import Dict, List, Optional, Set as SetType
from collections import defaultdict
import re
from datetime import datetime, timedelta

from .models import Card, CardSet, EXTRA_CARDS, EXTRA_SETS, ALTERNATE_SEARCH_NAMES
from .api import DLMApi, MDMApi, YGOProApi

log = logging.getLogger("red.dlm.registry")

class CardRegistry:
    """Card registry for managing card data and searches."""
    def __init__(self):
        self.dlm_api = DLMApi()
        self.mdm_api = MDMApi()
        self.ygopro_api = YGOProAPI()
        self._cards: Dict[str, Card] = {}  # id -> Card
        self._sets: Dict[str, CardSet] = {}  # id -> Set
        self._index: Dict[str, SetType[str]] = {}  # token(not monster tokens lmao) -> set(card_ids)
        self._last_update: Optional[datetime] = None
        self._update_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Initialize the registry and APIs."""
        if self._initialized:
            return

        await asyncio.gather(
            self.dlm_api.initialize(),
            self.mdm_api.initialize(),
            self.ygopro_api.initialize()
        )
        self._initialized = True
        await self.update_registry()

    async def close(self):
        """Clean up resources."""
        await asyncio.gather(
            self.dlm_api.close(),
            self.mdm_api.close(),
            self.ygopro_api.close()
        )

    def get_card_by_id(self, card_id: str) -> Optional[Card]:
        """Get a card by its ID."""
        return self._cards.get(card_id)

    def get_set_by_id(self, set_id: str) -> Optional[CardSet]:
        """Get a set by its ID."""
        return self._sets.get(set_id)

    def get_sets(self) -> List[CardSet]:
        """Get all sets."""
        return list(self._sets.values())

    def get_cards(self) -> List[Card]:
        """Get all cards."""
        return list(self._cards.values())

    def search_cards(self, query: str) -> List[Card]:
        """Search for cards using normalized tokens."""
        if not query:
            return []

        normalized = self._normalize_string(query)
        tokens = [normalized] + self._tokenize_string(normalized)
        card_ids_with_freq = defaultdict(int)
        for token in tokens:
            if token in self._index:
                for card_id in self._index[token]:
                    card_ids_with_freq[card_id] += 1

        sorted_ids = sorted(
            card_ids_with_freq.items(), 
            key=lambda x: x[1], 
            reverse=True
        )

        return [
            self._cards[card_id] 
            for card_id, _ in sorted_ids 
            if card_id in self._cards
        ]

    async def update_registry(self):
        """Update card and set data."""
        async with self._update_lock:
            try:
                await self._update_sets()
                await self._update_cards()
                await self._generate_index()
                self._last_update = datetime.now()
                log.info("Registry updated successfully")
            except Exception as e:
                log.error(f"Error updating registry: {str(e)}", exc_info=True)
                raise

    async def _update_sets(self):
        """Update set data."""
        dl_sets = await self.dlm_api.get_all_sets()
        md_sets = await self.mdm_api.get_all_sets()
        self._sets.clear()
        for set_data in [*EXTRA_SETS, *dl_sets, *md_sets]:
            self._sets[set_data.id] = set_data
        log.info(f"Updated {len(self._sets)} sets")

    async def _update_cards(self):
        """Update card data."""
        ygopro_cards = await self.ygopro_api.get_all_cards()
        dl_cards_raw = await self.dlm_api.get_all_cards_raw()
        md_cards_raw = await self.mdm_api.get_all_cards_raw()
        updated_cards = []
        for card in ygopro_cards:
            if str(card.id) in md_cards_raw:
                md_data = md_cards_raw[str(card.id)]
                card.status_md = self.mdm_api.STATUS_MAPPING.get(md_data.get("banStatus"))
                card.rarity_md = self.mdm_api.RARITY_MAPPING.get(md_data.get("rarity"))
                card.sets_md = [src["source"]["_id"] for src in md_data.get("obtain", [])]
            if str(card.id) in dl_cards_raw:
                dl_data = dl_cards_raw[str(card.id)]
                card.status_dl = self.dlm_api.STATUS_MAPPING.get(dl_data.get("banStatus"))
                card.rarity_dl = self.dlm_api.RARITY_MAPPING.get(dl_data.get("rarity"))
                card.sets_dl = [src["source"]["_id"] for src in dl_data.get("obtain", [])]
            updated_cards.append(card)

        self._cards.clear()
        for card in [*EXTRA_CARDS, *updated_cards]:
            self._cards[card.id] = card
        log.info(f"Updated {len(self._cards)} cards")

    async def _generate_index(self):
        """Generate search index from cards."""
        self._index.clear()
        all_cards = [*self.get_cards(), *ALTERNATE_SEARCH_NAMES]
        for card in all_cards:
            name = self._normalize_string(card.name)
            tokens = [name] + self._tokenize_string(name)
            for token in tokens:
                if token not in self._index:
                    self._index[token] = set()
                self._index[token].add(card.id)
        log.info(f"Generated index with {len(self._index)} tokens")

    @staticmethod
    def _normalize_string(text: str) -> str:
        """Normalize string for searching."""
        return re.sub(r'[^a-z0-9.]', '', text.lower())

    @staticmethod
    def _tokenize_string(text: str) -> List[str]:
        """Create 3-character tokens from string."""
        if len(text) < 3:
            return []
        return [text[i:i+3] for i in range(len(text)-2)]
