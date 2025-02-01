import logging
import asyncio
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from difflib import SequenceMatcher

from .models import Pokemon, EXTRA_CARDS
from .api import PokemonMetaAPI
from .cache import Cache

class CardRegistry:
    """Registry for Pokemon TCG cards, supporting lookups and updates."""

    def __init__(self, api: PokemonMetaAPI, *, log=None, cache_dir: str = "assets/cached/cards") -> None:
        self.logger = log or logging.getLogger("red.pokemonmeta.registry")
        self.api = api
        self.cache = Cache(log=self.logger, cache_dir=cache_dir)
        self._cards: Dict[str, Pokemon] = {}
        self._sets: Dict[str, 'CardRegistry.Set'] = {}
        self._name_index: Dict[str, str] = {}  # name -> id mapping
        self._set_index: Dict[str, List[str]] = {}  # set -> [card_ids]
        self._type_index: Dict[str, List[str]] = {}  # type -> [card_ids]
        self._rarity_index: Dict[str, List[str]] = {}  # rarity -> [card_ids]

        self._last_update: Optional[datetime] = None
        self._update_lock = asyncio.Lock()
        self._initialized = False

        # Add extra cards
        for card in EXTRA_CARDS:
            self._cards[card.id] = card
            self._generate_index_for_cards([card])

    async def initialize(self) -> None:
        """Initialize the registry if not already initialized."""
        if self._initialized:
            return

        try:
            cached_cards = self.cache.list_cached_cards()
            for card_name, card_id in cached_cards.items():
                # Try loading by ID first, then by name if that fails
                card_data = self.cache.get(card_id) or self.cache.get(card_name)
                if card_data:
                    card = Pokemon.from_api(card_data)
                    self._cards[card.id] = card
                    self._generate_index_for_cards([card])
            await self.api.initialize()
            self._initialized = True
            await self.update_registry()
        except Exception as e:
            self.logger.error(f"Failed to initialize registry: {str(e)}", exc_info=True)
            raise

    async def close(self) -> None:
        """Close the registry and cleanup resources."""
        try:
            await self.api.close()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {str(e)}", exc_info=True)

    async def get_card(self, card_id_or_name: str) -> Optional[Pokemon]:
        """Get a card by ID or exact name."""
        if card_id_or_name in self._cards:
            return self._cards[card_id_or_name]

        name_lower = card_id_or_name.lower()
        if card_id := self._name_index.get(name_lower):
            return self._cards.get(card_id)

        if cached_data := self.cache.get(card_id_or_name):
            card = Pokemon.from_api(cached_data)
            self._cards[card.id] = card
            self._generate_index_for_cards([card])
            return card

        try:
            if card_data := await self.api.get_card(card_id_or_name):
                card = Pokemon.from_api(card_data)
                self._cards[card.id] = card
                self._generate_index_for_cards([card])
                self.cache.set(card.id, card_data)  # Cache the API response
                return card
        except Exception as e:
            self.logger.error(f"Error getting card: {str(e)}", exc_info=True)

        return None

    async def get_card_image(self, card_id: str) -> Optional[str]:
        """Get the path to a card's image."""
        return self.cache.get_image_path(card_id)

    async def get_card_decks(self, card_id: str) -> Optional[Dict]:
        """Get deck data for a card."""
        return self.cache.get_deck_data(card_id)

    def get_cards_by_set(self, set_name: str) -> List[Pokemon]:
        """Get all cards from a specific set."""
        card_ids = self._set_index.get(set_name, [])
        return [self._cards[cid] for cid in card_ids if cid in self._cards]

    def _fuzzy_search(self, query: str, items: List[Dict[str, Any]], threshold: float = 0.4) -> List[Dict[str, Any]]:
        """Perform fuzzy search on items."""
        query = query.lower()
        matches = []
        for item in items:
            target = str(item.get("name", "")).lower()
            if not target:
                continue
            ratio = SequenceMatcher(None, query, target).ratio()
            if query == target:
                ratio += 0.6
            elif query in target:
                ratio += 0.3
            elif target.startswith(query):
                ratio += 0.2
            if ratio >= threshold:
                matches.append({**item, "_score": ratio})
        matches.sort(key=lambda x: x["_score"], reverse=True)
        return matches[:25]

    async def search_cards(self, query: str, **filters) -> List[Pokemon]:
        """Search for cards using fuzzy matching and filters."""
        try:
            if not self._initialized:
                await self.initialize()

            results = []
            query = query.strip()

            search_items = [
                {"id": card.id, "name": card.name, "card": card}
                for card in self._cards.values()
            ]

            fuzzy_matches = self._fuzzy_search(query, search_items)
            for match in fuzzy_matches:
                card = match["card"]
                if self._matches_filters(card, filters):
                    results.append(card)

            if len(results) < 25:  # Only if we need more results
                api_cards = await self.api.search_cards(query)
                if api_cards:
                    for card_data in api_cards:
                        try:
                            card = Pokemon.from_api(card_data)
                            if (self._matches_filters(card, filters) and 
                                card not in results and 
                                len(results) < 25):
                                results.append(card)
                                # Cache the card
                                if card.id not in self._cards:
                                    self._cards[card.id] = card
                                    self._generate_index_for_cards([card])
                                    self.cache.set(card.id, card_data)
                        except Exception as e:
                            self.logger.error(f"Error processing API result: {str(e)}")

            self.logger.debug(f"Search '{query}' found {len(results)} results")
            return results

        except Exception as e:
            self.logger.error(f"Error searching cards: {str(e)}", exc_info=True)
            return []

    async def update_registry(self) -> bool:
        """Update the registry with latest card data."""
        async with self._update_lock:
            try:
                await self._update_sets()
                changed = False

                # Update existing cards
                for card_id in list(self._cards.keys()):
                    card_changed = await self._update_card(card_id)
                    changed = changed or card_changed
                    await asyncio.sleep(random.uniform(0.5, 2))

                self._last_update = datetime.now()
                return changed
            except Exception as e:
                self.logger.error(f"Error updating registry: {str(e)}", exc_info=True)
                raise

    async def _update_sets(self) -> None:
        """Update set information."""
        try:
            self._sets.clear()
            if sets_data := await self.api.get_sets():
                for set_data in sets_data:
                    if set_data:
                        set_obj = CardRegistry.Set(
                            id=set_data["_id"],
                            name=set_data["name"],
                            type=set_data.get("type", ""),
                            expires=datetime.fromisoformat(set_data["expires"].replace("Z", "+00:00")) if set_data.get("expires") else None,
                            url=set_data.get("url"),
                            image=set_data.get("image")
                        )
                        self._sets[set_obj.id] = set_obj

            self.logger.info(f"Updated {len(self._sets)} sets")
        except Exception as e:
            self.logger.error(f"Error updating sets: {str(e)}", exc_info=True)
            raise

    async def _update_card(self, card_id: str) -> bool:
        """Update a single card's data."""
        try:
            if cached_data := self.cache.get(card_id):
                new_card = Pokemon.from_api(cached_data)
                old_card = self._cards.get(card_id)
                
                if not old_card or self._has_card_changed(old_card, new_card):
                    self._cards[card_id] = new_card
                    self._generate_index_for_cards([new_card])
                    return True
                return False

            if card_data := await self.api.get_card(card_id):
                new_card = Pokemon.from_api(card_data)
                old_card = self._cards.get(card_id)

                if not old_card or self._has_card_changed(old_card, new_card):
                    self._cards[card_id] = new_card
                    self._generate_index_for_cards([new_card])
                    self.cache.set(card_id, card_data)
                    return True

            return False
        except Exception as e:
            self.logger.error(f"Error updating card {card_id}: {str(e)}", exc_info=True)
            return False

    def _generate_index_for_cards(self, cards: List[Pokemon]) -> None:
        """Generate search indices for the given cards."""
        for card in cards:
            name_lower = card.name.lower()
            self._name_index[name_lower] = card.id

            if card.pack:
                if card.pack not in self._set_index:
                    self._set_index[card.pack] = []
                if card.id not in self._set_index[card.pack]:
                    self._set_index[card.pack].append(card.id)

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

    @staticmethod
    def _has_card_changed(old: Pokemon, new: Pokemon) -> bool:
        """Check if a card's relevant data has changed."""
        if len(old.abilities) != len(new.abilities):
            return True
        for old_ability, new_ability in zip(old.abilities, new.abilities):
            if (old_ability.name != new_ability.name or 
                old_ability.text != new_ability.text or 
                old_ability.type != new_ability.type):
                return True

        return (
            old.rarity != new.rarity or
            old.moves != new.moves or
            old.obtain != new.obtain or
            old.art_variants != new.art_variants
        )

    def _matches_filters(self, card: Pokemon, filters: Dict[str, str]) -> bool:
        """Check if a card matches the given filters."""
        for key, value in filters.items():
            if not value:  # Skip empty filters
                continue
            if key == "type" and value.lower() not in [t.lower() for t in card.energy_type]:
                return False
            elif key == "set" and value.lower() != card.pack.lower():
                return False
            elif key == "rarity" and value.lower() != card.rarity.lower():
                return False
        return True

    @dataclass
    class Set:
        """Inner class representing a card set."""
        id: str
        name: str
        type: str
        expires: Optional[datetime] = None
        url: Optional[str] = None
        image: Optional[str] = None
