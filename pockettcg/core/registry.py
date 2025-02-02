import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
import os
from .models import Pokemon, EXTRA_CARDS
from .cache import Cache

LOGGER_NAME_BASE = "red.pokemonmeta"
log = logging.getLogger(f"{LOGGER_NAME_BASE}.core.registry")


class CardRegistry:
    """
    Registry for Pokemon TCG cards. Handles loading and searching of card data from cache.
    """

    def __init__(self, *, cache_dir: str = "assets/cache/cards", api=None):
        """
        Initialize registry.
        Args:
            cache_dir: Path to cards cache directory
            api: API client instance for live data fetching
        """
        self.cache = Cache(cache_dir=cache_dir)
        self.api = api  # Store API reference
        self._cards: Dict[str, Pokemon] = {}  # id -> card
        self._name_index: Dict[str, str] = {}  # lowercase name -> id
        self._set_index: Dict[str, List[str]] = {}  # set name -> [card ids]
        self._rarity_index: Dict[str, List[str]] = {}  # rarity -> [card ids]
        self._type_index: Dict[str, List[str]] = {}  # type -> [card ids]
        for card in EXTRA_CARDS:
            self._add_card_to_indices(card)
        self._initialized = False

    def _add_card_to_indices(self, card: Pokemon) -> None:
        """Add a card to all search indices."""
        self._cards[card.id] = card

        name_key = card.name.lower().strip()
        self._name_index[name_key] = card.id

        set_name = card.set if hasattr(card, 'set') else 'Unknown Set'
        if set_name not in self._set_index:
            self._set_index[set_name] = []
        if card.id not in self._set_index[set_name]:
            self._set_index[set_name].append(card.id)

        if card.type:
            if card.type not in self._type_index:
                self._type_index[card.type] = []
            if card.id not in self._type_index[card.type]:
                self._type_index[card.type].append(card.id)

        if card.rarity:
            if card.rarity not in self._rarity_index:
                self._rarity_index[card.rarity] = []
            if card.id not in self._rarity_index[card.rarity]:
                self._rarity_index[card.rarity].append(card.id)

    async def initialize(self) -> None:
        if self._initialized:
            return
        try:
            log.info("Starting registry initialization from cache")
            cached_cards = self.cache.list_cached_cards()
            log.info(f"Found {len(cached_cards)} cards in cache")

            for card_filename in cached_cards:
                try:
                    base_name = os.path.splitext(card_filename)[0]
                    file_parts = base_name.split('_')
                    file_id = file_parts[-1] if len(file_parts) > 1 else base_name

                    card_data = self.cache.get(card_filename)
                    if not card_data:
                        continue

                    if isinstance(card_data, list):
                        cards_to_process = card_data
                    else:
                        cards_to_process = [card_data]

                    for single_card_data in cards_to_process:
                        try:
                            if not isinstance(single_card_data, dict):
                                continue

                            if '_id' not in single_card_data:
                                single_card_data['_id'] = file_id

                            card = Pokemon.from_api(single_card_data)
                            self._add_card_to_indices(card)

                        except Exception as e:
                            continue

                except Exception:
                    continue

            self._initialized = True
            log.info(f"Registry initialization complete - loaded {len(self._cards)} cards")
        except Exception as e:
            log.error(f"Failed to initialize registry: {e}", exc_info=True)
            raise

    async def get_card(self, card_id_or_name: str) -> Optional[Pokemon]:
        """Get a card by ID or name."""
        if not card_id_or_name:
            return None
        if not self._initialized:
            await self.initialize()
        if card_id_or_name in self._cards:
            return self._cards[card_id_or_name]
        name_key = card_id_or_name.lower().strip()
        if card_id := self._name_index.get(name_key):
            return self._cards.get(card_id)
        if cached_data := self.cache.get(card_id_or_name):
            try:
                if isinstance(cached_data, list):
                    if not cached_data:
                        return None
                    cached_data = cached_data[0]

                if not isinstance(cached_data, dict):
                    log.error(f"Invalid card data format: {type(cached_data)}")
                    return None

                card = Pokemon.from_api(cached_data)
                self._add_card_to_indices(card)
                return card
            except Exception as e:
                log.error(f"Failed to load card from cache: {e}")
        return None

    async def search_cards(self, query: str, **filters) -> List[Pokemon]:
        """Search for cards by name with optional filters."""
        if not self._initialized:
            await self.initialize()
        if not query:
            return []
        try:
            search_items = [
                {"id": card.id, "name": card.name, "card": card}
                for card in self._cards.values()
            ]
            fuzzy_results = self._fuzzy_search(query, search_items)
            results = []
            for match in fuzzy_results:
                card = match["card"]
                if self._matches_filters(card, filters):
                    results.append(card)
            return results[:25]
        except Exception as e:
            log.error(f"Search failed: {e}")
            return []

    def _fuzzy_search(
        self,
        query: str,
        items: List[Dict[str, Any]],
        threshold: float = 0.4
    ) -> List[Dict[str, Any]]:
        """Perform fuzzy search on items."""
        query = query.lower().strip()
        matches = []
        for item in items:
            target = str(item.get("name", "")).lower()
            if not target:
                continue
            ratio = SequenceMatcher(None, query, target).ratio()
            if query == target:
                ratio += 0.6  # Exact match
            elif query in target:
                ratio += 0.3  # Substring match
            elif target.startswith(query):
                ratio += 0.2  # Prefix match
            if ratio >= threshold:
                matches.append({**item, "_score": ratio})
        matches.sort(key=lambda x: x["_score"], reverse=True)
        return matches[:25]

    def _matches_filters(self, card: Pokemon, filters: Dict[str, str]) -> bool:
        """Check if a card matches all provided filters."""
        try:
            for key, value in filters.items():
                if not value:  # Skip empty filters
                    continue

                if key == "type":
                    if value.lower().strip() not in [t.lower() for t in card.energy_type]:
                        return False
                elif key == "set":
                    if not hasattr(card, 'set'):
                        return False
                    if value.lower().strip() != card.set.lower():
                        return False
                elif key == "rarity":
                    if value.lower().strip() != card.rarity.lower():
                        return False
            return True
        except Exception as e:
            log.error(f"Error checking filters: {e}")
            return False

    async def get_card_image(self, card_id: str) -> Optional[str]:
        """Get path to card's cached image."""
        return self.cache.get_image_path(card_id)

    async def get_card_decks(self, card_id: str) -> Optional[Dict]:
        """Get cached deck data for card."""
        return self.cache.get_deck_data(card_id)

    def get_cards_by_set(self, set_name: str) -> List[Pokemon]:
        """Get all cards from a specific set."""
        card_ids = self._set_index.get(set_name, [])
        return [self._cards[cid] for cid in card_ids if cid in self._cards]
