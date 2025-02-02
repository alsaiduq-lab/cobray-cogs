import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher

from .models import Pokemon, EXTRA_CARDS
from .cache import Cache

LOGGER_NAME_BASE = "red.pokemonmeta"
log = logging.getLogger(f"{LOGGER_NAME_BASE}.core.registry")

@dataclass
class Set:
    """Card set information."""
    id: str
    name: str
    type: str
    expires: Optional[datetime] = None
    url: Optional[str] = None
    image: Optional[str] = None

class CardRegistry:
    """
    Registry for Pokemon TCG cards. Handles loading and searching of card data from cache.
    """

    def __init__(self, *, cache_dir: str = "assets/cache/cards", api=None):
        """
        Initialize registry.
        Args:
            cache_dir: Path to cards cache directory
            api: Ignored. This registry operates on cached data only.
        """
        if api is not None:
            log.warning("API client provided but will not be used - registry operates on cached data only")
        log.info("Initializing card registry")
        self.cache = Cache(cache_dir=cache_dir)
        # Memory stores
        self._cards: Dict[str, Pokemon] = {}  # id -> card
        self._name_index: Dict[str, str] = {} # lowercase name -> id
        self._set_index: Dict[str, List[str]] = {}  # set name -> [card ids]
        self._rarity_index: Dict[str, List[str]] = {}  # rarity -> [card ids]
        self._type_index: Dict[str, List[str]] = {}  # type -> [card ids]
        # Load static cards
        for card in EXTRA_CARDS:
            self._add_card_to_indices(card)
        self._initialized = False
        log.info("Registry ready for initialization")

    def _add_card_to_indices(self, card: Pokemon) -> None:
        """Add a card to all search indices."""
        # Store card
        self._cards[card.id] = card
        # Name index
        name_key = card.name.lower().strip()
        self._name_index[name_key] = card.id
        # Set index 
        if hasattr(card, 'set'):
            set_name = card.set
        else:
            set_name = getattr(card, 'pack', 'Unknown Set')
        if set_name not in self._set_index:
            self._set_index[set_name] = []
        if card.id not in self._set_index[set_name]:
            self._set_index[set_name].append(card.id)
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

    async def initialize(self) -> None:
        """Initialize registry by loading all cards from cache."""
        if self._initialized:
            return
        try:
            log.info("Starting registry initialization from cache")
            # Get all cached cards
            cached_cards = self.cache.list_cached_cards()
            log.info(f"Found {len(cached_cards)} cards in cache")
            # Process each cached card
            for card_id in cached_cards:
                try:
                    # Load card data
                    card_data = self.cache.get(card_id)
                    if not card_data:
                        continue
                        
                    # Fix field names if needed
                    if "set" not in card_data and "pack" in card_data:
                        card_data["set"] = card_data["pack"]
                        
                    # Add required fields with defaults
                    card_data.setdefault("set", "Unknown Set")
                    card_data.setdefault("cardType", "Unknown")
                    card_data.setdefault("subType", "Unknown")
                    
                    # Create card and add to indices
                    card = Pokemon.from_api(card_data)
                    self._add_card_to_indices(card)
                    
                except Exception as e:
                    log.error(f"Failed to load cached card {card_id}: {e}")
                    continue
            self._initialized = True
            log.info(f"Registry initialization complete - loaded {len(self._cards)} cards")
        except Exception as e:
            log.error(f"Failed to initialize registry: {e}")
            raise

    async def get_card(self, card_id_or_name: str) -> Optional[Pokemon]:
        """Get a card by ID or name."""
        if not card_id_or_name:
            return None
        # Ensure initialized
        if not self._initialized:
            await self.initialize()
        # Direct ID lookup
        if card_id_or_name in self._cards:
            return self._cards[card_id_or_name]
        # Name lookup
        name_key = card_id_or_name.lower().strip()
        if card_id := self._name_index.get(name_key):
            return self._cards.get(card_id)
        # One final try with cache
        if cached_data := self.cache.get(card_id_or_name):
            try:
                if "set" not in cached_data and "pack" in cached_data:
                    cached_data["set"] = cached_data["pack"]
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
            # Prepare search items
            search_items = [
                {"id": card.id, "name": card.name, "card": card}
                for card in self._cards.values()
            ]
            # Get fuzzy matches
            fuzzy_results = self._fuzzy_search(query, search_items)
            # Apply filters
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
            # Calculate match score
            ratio = SequenceMatcher(None, query, target).ratio()
            # Bonus points
            if query == target:
                ratio += 0.6  # Exact match
            elif query in target:
                ratio += 0.3  # Substring match
            elif target.startswith(query):
                ratio += 0.2  # Prefix match
            # Keep if above threshold
            if ratio >= threshold:
                matches.append({**item, "_score": ratio})
        # Sort by score
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
                    card_set = getattr(card, 'set', getattr(card, 'pack', ''))
                    if value.lower().strip() != card_set.lower():
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
