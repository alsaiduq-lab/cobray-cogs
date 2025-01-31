"""Registry for Pokemon TCG cards."""
import logging
import asyncio
import re
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set

from .models import Pokemon, EXTRA_CARDS
from .api import PokemonMetaAPI

class CardRegistry:
    """Registry for Pokemon TCG cards, supporting lookups and updates."""

    def __init__(self, api: PokemonMetaAPI, *, log=None) -> None:
        self.logger = log or logging.getLogger("red.pokemonmeta.registry")
        self.api = api
        self._cards: Dict[str, Pokemon] = {}
        self._sets: Dict[str, Set] = {}
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
            await self.api.initialize()  # Changed from init() to initialize()
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
        # Try direct ID lookup
        if card_id_or_name in self._cards:
            return self._cards[card_id_or_name]

        # Try exact name lookup
        name_lower = card_id_or_name.lower()
        if card_id := self._name_index.get(name_lower):
            return self._cards.get(card_id)

        # Try API lookup
        try:
            if card_data := await self.api.get_card(card_id_or_name):
                card = Pokemon.from_api(card_data)
                self._cards[card.id] = card
                self._generate_index_for_cards([card])
                return card
        except Exception as e:
            self.logger.error(f"Error getting card: {str(e)}", exc_info=True)

        return None

    def get_cards_by_set(self, set_name: str) -> List[Pokemon]:
        """Get all cards from a specific set."""
        card_ids = self._set_index.get(set_name, [])
        return [self._cards[cid] for cid in card_ids if cid in self._cards]

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
            if card_data := await self.api.get_card(card_id):
                old_card = self._cards.get(card_id)
                new_card = Pokemon.from_api(card_data)

                if not old_card or self._has_card_changed(old_card, new_card):
                    self._cards[card_id] = new_card
                    self._generate_index_for_cards([new_card])
                    return True

            return False
        except Exception as e:
            self.logger.error(f"Error updating card {card_id}: {str(e)}", exc_info=True)
            return False

    def _generate_index_for_cards(self, cards: List[Pokemon]) -> None:
        """Generate search indices for the given cards."""
        for card in cards:
            # Name index
            name_lower = card.name.lower()
            self._name_index[name_lower] = card.id

            # Set index
            if card.pack:
                if card.pack not in self._set_index:
                    self._set_index[card.pack] = []
                if card.id not in self._set_index[card.pack]:
                    self._set_index[card.pack].append(card.id)

            # Type index
            if card.type:
                if card.type not in self._type_index:
                    self._type_index[card.type] = []
                if card.id not in self._type_index[card.type]:
                    self._type_index[card.type].append(card.id)

            # Rarity index
            if card.rarity:
                if card.rarity not in self._rarity_index:
                    self._rarity_index[card.rarity] = []
                if card.id not in self._rarity_index[card.rarity]:
                    self._rarity_index[card.rarity].append(card.id)

    @staticmethod
    def _has_card_changed(old: Pokemon, new: Pokemon) -> bool:
        """Check if a card's relevant data has changed."""
        return (
            old.rarity != new.rarity or
            old.moves != new.moves or
            old.obtain != new.obtain or
            old.art_variants != new.art_variants
        )

    async def search_cards(self, query: str, **filters) -> List[Pokemon]:
        """Search for cards using fuzzy matching and filters."""
        try:
            if not self._initialized:
                await self.initialize()

            # Try API search first
            cards = await self.api.search_cards(query)
            if cards:
                results = []
                for card_data in cards:
                    try:
                        card = Pokemon.from_api(card_data)
                        if self._matches_filters(card, filters):
                            results.append(card)
                            # Cache the card for future use
                            if card.id not in self._cards:
                                self._cards[card.id] = card
                                self._generate_index_for_cards([card])
                    except Exception as e:
                        self.logger.error(f"Error processing search result: {str(e)}")
                return results[:25]

            # Fall back to local search if API returns nothing
            search_items = [
                {"id": card.id, "name": card.name}
                for card in self._cards.values()
            ]

            results = []
            for item in search_items:
                if query.lower() in item["name"].lower():
                    if card := self._cards.get(item["id"]):
                        if self._matches_filters(card, filters):
                            results.append(card)
            return results[:25]

        except Exception as e:
            self.logger.error(f"Error searching cards: {str(e)}", exc_info=True)
            return []

    def _matches_filters(self, card: Pokemon, filters: Dict[str, str]) -> bool:
        """Check if a card matches the given filters."""
        for key, value in filters.items():
            if key == "type" and value not in card.energy_type:
                return False
            elif key == "set" and card.pack != value:
                return False
            elif key == "rarity" and card.rarity != value:
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
