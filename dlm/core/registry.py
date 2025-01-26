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
        self.ygopro_api = YGOProApi()
        self._cards: Dict[str, Card] = {}  # id -> Card
        self._sets: Dict[str, CardSet] = {}  # id -> Set
        self._index: Dict[str, SetType[str]] = {}  # token(not monster tokens lmao) -> set(card_ids)
        self._last_update: Optional[datetime] = None
        self._update_lock = asyncio.Lock()
        self._initialized = False
        for card in EXTRA_CARDS:
            self._cards[card.id] = card
        self._generate_index_for_cards(EXTRA_CARDS + ALTERNATE_SEARCH_NAMES)

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

    async def get_card(self, query: str) -> Optional[Card]:
        """Get card by ID or name."""
        if query in self._cards:
            return self._cards[query]
        try:
            card_data = await self.ygopro_api.search_cards(query, exact=True)
            if not card_data:
                return None

            card = await self._process_card_data(card_data[0])
            if card:
                self._cards[card.id] = card
                self._generate_index_for_cards([card])
                return card
        except Exception as e:
            log.error(f"Error getting card: {str(e)}")
        return None

    async def _process_card_data(self, card_data: Dict) -> Optional[Card]:
        """Process raw card data with format information."""
        try:
            card = Card(
                id=str(card_data["id"]),
                name=card_data["name"],
                type=card_data["type"].lower(),
                description=card_data.get("desc"),
                race=card_data.get("race"),
                attribute=card_data.get("attribute"),
                level=card_data.get("level"),
                atk=card_data.get("atk"),
                def_=card_data.get("def"),
                monster_type=card_data.get("frameType", "").lower() if "frameType" in card_data else None
            )

            card_id = str(card.id)
            try:
                md_data = await self.mdm_api.get_card_details(card_id)
                if md_data:
                    card.status_md = self.mdm_api.STATUS_MAPPING.get(md_data.get("banStatus"))
                    card.rarity_md = self.mdm_api.RARITY_MAPPING.get(md_data.get("rarity"))
                    card.sets_md = [src["source"]["_id"] for src in md_data.get("obtain", [])] if "obtain" in md_data else []
            except Exception as e:
                log.debug(f"Error getting MD data for {card_id}: {str(e)}")

            try:
                dl_data = await self.dlm_api.get_card_details(card_id)
                if dl_data:
                    card.status_dl = self.dlm_api.STATUS_MAPPING.get(dl_data.get("banStatus"))
                    card.rarity_dl = self.dlm_api.RARITY_MAPPING.get(dl_data.get("rarity"))
                    card.sets_dl = [src["source"]["_id"] for src in dl_data.get("obtain", [])] if "obtain" in dl_data else []
            except Exception as e:
                log.debug(f"Error getting DL data for {card_id}: {str(e)}")

            return card
        except Exception as e:
            log.error(f"Error processing card data: {str(e)}")
            return None

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
        """Update registry data."""
        async with self._update_lock:
            try:
                await self._update_sets()
                self._last_update = datetime.now()
                log.info("Registry updated successfully")
            except Exception as e:
                log.error(f"Error updating registry: {str(e)}")
                raise

    async def _update_sets(self):
        """Update set data."""
        try:
            self._sets.clear()
            for set_data in [*EXTRA_SETS, *dl_sets, *md_sets]:
                if isinstance(set_data, CardSet):
                    self._sets[set_data.id] = set_data
            log.info(f"Updated {len(self._sets)} sets")
        except Exception as e:
            log.error(f"Error updating sets: {str(e)}")
            raise

    def _generate_index_for_cards(self, cards: List[Card]):
        """Generate search index for specified cards."""
        for card in cards:
            name = self._normalize_string(card.name)
            tokens = [name] + self._tokenize_string(name)
            for token in tokens:
                if token not in self._index:
                    self._index[token] = set()
                self._index[token].add(card.id)

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
