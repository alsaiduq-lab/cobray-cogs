import logging
import asyncio
import re
import random
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set as SetType

from .models import Card, CardSet, EXTRA_CARDS, EXTRA_SETS, ALTERNATE_SEARCH_NAMES
from .api import DLMApi, MDMApi, YGOProApi
from ..utils.fsearch import fuzzy_search

class CardRegistry:
    """
    A registry for Yu-Gi-Oh! cards, supporting lookups and updates from multiple
    external APIs (DLM, MDM, YGOPro).
    """

    def __init__(self, *, log=None) -> None:
        """Initialize the CardRegistry's APIs and in-memory structures.
        
        Args:
            log: Optional logger instance. If not provided, uses default logger.
        """
        self.logger = log or logging.getLogger("red.dlm.core.registry")
        
        self.dlm_api = DLMApi(log=self.logger)
        self.mdm_api = MDMApi(log=self.logger)
        self.ygopro_api = YGOProApi(log=self.logger)

        self._cards: Dict[str, Card] = {}
        self._sets: Dict[str, CardSet] = {}
        self._index: Dict[str, SetType[str]] = {}

        self._last_update: Optional[datetime] = None
        self._update_lock = asyncio.Lock()
        self._initialized = False

        for card in EXTRA_CARDS:
            self._cards[card.id] = card

        self._generate_index_for_cards(EXTRA_CARDS + ALTERNATE_SEARCH_NAMES)

    def get_card_by_id(self, card_id: str) -> Optional[Card]:
        """
        Get a card by its ID.
        """
        return self._cards.get(card_id)

    def get_set_by_id(self, set_id: str) -> Optional[CardSet]:
        """
        Get a set by its ID.
        """
        return self._sets.get(set_id)

    def get_sets(self) -> List[CardSet]:
        """Return all known sets as a list."""
        return list(self._sets.values())



    async def initialize(self) -> None:
        """Initialize APIs and update the registry if not already initialized."""
        if self._initialized:
            return

        try:
            await asyncio.gather(
                self.dlm_api.initialize(),
                self.mdm_api.initialize(),
                self.ygopro_api.initialize(),
            )
            self._initialized = True
            await self.update_registry()
        except Exception as e:
            self.logger.error(f"Failed to initialize registry: {str(e)}", exc_info=True)
            raise

    async def close(self) -> None:
        """Close any resources held by the APIs."""
        try:
            await asyncio.gather(
                self.dlm_api.close(),
                self.mdm_api.close(),
                self.ygopro_api.close(),
                return_exceptions=True,
            )
        except Exception as e:
            self.logger.error(f"Error during cleanup: {str(e)}", exc_info=True)

    async def get_card(self, query: str) -> Optional[Card]:
        """
        Get a card by ID or exact name using YGOPro's API. If found in
        self._cards, returns from cache.
        """
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
            self.logger.error(f"Error getting card: {str(e)}", exc_info=True)

        return None

    async def _process_card_data(self, card_data: Dict) -> Optional[Card]:
        """
        Convert raw YGOPro/API data to Card, then fetch Master Duel & Duel Links info.
        """
        try:
            card = Card(
                id=str(card_data.get("id") or card_data.get("konamiID", "")),  # Handle both API formats
                name=card_data.get("name", ""),
                type=card_data.get("type", "").lower(),
                description=card_data.get("desc") or card_data.get("description", ""),
                race=card_data.get("race"),
                attribute=card_data.get("attribute"),
                level=card_data.get("level"),
                atk=card_data.get("atk"),
                def_=card_data.get("def"),
                monster_type=card_data.get("frameType", "").lower() if "frameType" in card_data 
                           else card_data.get("monsterType", []) if isinstance(card_data.get("monsterType"), list)
                           else None
            )
            card_id = card.id

            if "deckTypes" in card_data:
                card.deck_types = card_data["deckTypes"]
            if "linkArrows" in card_data:
                card.link_arrows = card_data["linkArrows"]
            if "obtain" in card_data:
                card.obtain = card_data["obtain"]
            if "release" in card_data:
                try:
                    card.release_date = datetime.fromisoformat(card_data["release"].replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            try:
                md_data = await self.mdm_api.get_card_details(card_id)
                if isinstance(md_data, list) and md_data:
                    md_data = md_data[0]
                if md_data and isinstance(md_data, dict):
                    card.status_md = self.mdm_api.STATUS_MAPPING.get(
                        md_data.get("banStatus")
                    )
                    card.rarity_md = self.mdm_api.RARITY_MAPPING.get(
                        md_data.get("rarity")
                    )
                    if "obtain" in md_data:
                        card.sets_md = [
                            src["source"]["_id"] for src in md_data["obtain"]
                        ]
            except Exception as e:
                self.logger.debug(f"Error getting MD data for {card_id}: {str(e)}")

            # Duel Links data:
            try:
                dl_data = await self.dlm_api.get_card_details(card_id)
                if isinstance(dl_data, list) and dl_data:
                    dl_data = dl_data[0]
                if dl_data and isinstance(dl_data, dict):
                    card.status_dl = self.dlm_api.STATUS_MAPPING.get(
                        dl_data.get("banStatus")
                    )
                    card.rarity_dl = self.dlm_api.RARITY_MAPPING.get(
                        dl_data.get("rarity")
                    )
                    if "obtain" in dl_data:
                        card.sets_dl = [
                            src["source"]["_id"] for src in dl_data["obtain"]
                        ]
            except Exception as e:
                self.logger.debug(f"Error getting DL data for {card_id}: {str(e)}")

            return card

        except Exception as e:
            self.logger.error(f"Error processing card data: {str(e)}", exc_info=True)
            return None

    async def update_registry(self) -> bool:
        """Update the registry."""
        async with self._update_lock:
            try:
                await self._update_sets()
                changed = False
                for card_id in list(self._cards.keys()):
                    card_changed = await self._update_card_status(card_id)
                    changed = changed or card_changed
                    await asyncio.sleep(random.uniform(0.5, 2))

                self._last_update = datetime.now()
                return changed
            except Exception as e:
                self.logger.error(f"Error updating registry: {str(e)}", exc_info=True)
                raise

    async def _update_sets(self) -> None:
        """
        Fetch set data from DLM / MDM APIs and process them properly.
        """
        try:
            self._sets.clear()
            dl_sets = []
            md_sets = []
            set_cache = {}

            try:
                if hasattr(self.dlm_api, "get_sets"):
                    raw_sets = await self.dlm_api.get_sets()
                    for set_data in raw_sets:
                        if isinstance(set_data, dict):
                            if "obtain" in set_data:
                                for obtain in set_data["obtain"]:
                                    if "source" in obtain and isinstance(obtain["source"], dict):
                                        source = obtain["source"]
                                        set_id = source.get("_id")
                                        if set_id and set_id not in set_cache:
                                            card_set = CardSet(
                                                id=set_id,
                                                name=source.get("name", "Unknown Set"),
                                                type=source.get("type", "Unknown Type"),
                                                release_date=source.get("release"),
                                                game="Duel Links"
                                            )
                                            set_cache[set_id] = card_set
                                            dl_sets.append(card_set)
            except Exception as e:
                self.logger.error(f"Error fetching DL sets: {str(e)}", exc_info=True)

            try:
                if hasattr(self.mdm_api, "get_sets"):
                    md_sets = await self.mdm_api.get_sets()
            except Exception as e:
                self.logger.error(f"Error fetching MD sets: {str(e)}", exc_info=True)

            for set_data in [*EXTRA_SETS, *dl_sets, *md_sets]:
                if isinstance(set_data, CardSet):
                    self._sets[set_data.id] = set_data

            self.logger.info(f"Updated {len(self._sets)} sets")
        except Exception as e:
            self.logger.error(f"Error updating sets: {str(e)}", exc_info=True)
            raise

    async def _update_card_status(self, card_id: str) -> bool:
        """Update format-specific data for a single card."""
        try:
            if card_id not in self._cards:
                card_data = await self.ygopro_api.get_card_info(card_id)
                if not card_data:
                    return False
                self._cards[card_id] = card_data

            card = self._cards[card_id]
            changed = False

            try:
                md_data = await self.mdm_api.get_card_details(card_id)
                if isinstance(md_data, list) and md_data:
                    md_data = md_data[0]
                if md_data and isinstance(md_data, dict):
                    old_status = card.status_md
                    old_rarity = card.rarity_md
                    old_sets = card.sets_md

                    card.status_md = self.mdm_api.STATUS_MAPPING.get(
                        md_data.get("banStatus")
                    )
                    card.rarity_md = self.mdm_api.RARITY_MAPPING.get(
                        md_data.get("rarity")
                    )
                    if "obtain" in md_data:
                        card.sets_md = [
                            src["source"]["_id"] for src in md_data["obtain"]
                        ]

                    if (old_status != card.status_md or
                        old_rarity != card.rarity_md or
                        old_sets != card.sets_md):
                        changed = True
            except Exception as e:
                self.logger.debug(f"Error updating MD data for {card_id}: {str(e)}")

            try:
                dl_data = await self.dlm_api.get_card_details(card_id)
                if isinstance(dl_data, list) and dl_data:
                    dl_data = dl_data[0]
                if dl_data and isinstance(dl_data, dict):
                    old_status = card.status_dl
                    old_rarity = card.rarity_dl
                    old_sets = card.sets_dl

                    card.status_dl = self.dlm_api.STATUS_MAPPING.get(
                        dl_data.get("banStatus")
                    )
                    card.rarity_dl = self.dlm_api.RARITY_MAPPING.get(
                        dl_data.get("rarity")
                    )
                    if "obtain" in dl_data:
                        card.sets_dl = [
                            src["source"]["_id"] for src in dl_data["obtain"]
                        ]

                    if (old_status != card.status_dl or
                        old_rarity != card.rarity_dl or
                        old_sets != card.sets_dl):
                        changed = True
            except Exception as e:
                self.logger.debug(f"Error updating DL data for {card_id}: {str(e)}")

            return changed

        except Exception as e:
            self.logger.error(f"Error updating card {card_id}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def _normalize_string(text: str) -> str:
        """
        Normalize a string for indexing by removing non-alphanumeric chars
        and making it lowercase.
        """
        return re.sub(r"[^a-z0-9.]", "", text.lower())

    @staticmethod
    def _tokenize_string(text: str) -> List[str]:
        """
        Create list of 3-character tokens from the normalized string.
        """
        if len(text) < 3:
            return []
        return [text[i : i + 3] for i in range(len(text) - 2)]

    def _generate_index_for_cards(self, cards: List[Card]) -> None:
        """
        Build or update the tokenized search index for the given cards.
        """
        for card in cards:
            name = self._normalize_string(card.name)
            tokens = [name] + self._tokenize_string(name)
            for token in tokens:
                if token not in self._index:
                    self._index[token] = set()
                self._index[token].add(card.id)


