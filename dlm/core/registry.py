import logging
import asyncio
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set as SetType

from .models import Card, CardSet, EXTRA_CARDS, EXTRA_SETS, ALTERNATE_SEARCH_NAMES
from .api import DLMApi, MDMApi, YGOProApi

log = logging.getLogger("red.dlm.registry")


class CardRegistry:
    """
    A registry for Yu-Gi-Oh! cards, supporting lookups and updates from multiple
    external APIs (DLM, MDM, YGOPro).
    """

    def __init__(self) -> None:
        """Initialize the CardRegistry's APIs and in-memory structures."""
        self.dlm_api = DLMApi()
        self.mdm_api = MDMApi()
        self.ygopro_api = YGOProApi()

        self._cards: Dict[str, Card] = {}
        self._sets: Dict[str, CardSet] = {}
        self._index: Dict[str, SetType[str]] = {}

        self._last_update: Optional[datetime] = None
        self._update_lock = asyncio.Lock()
        self._initialized = False

        for card in EXTRA_CARDS:
            self._cards[card.id] = card

        self._generate_index_for_cards(EXTRA_CARDS + ALTERNATE_SEARCH_NAMES)

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
            log.error(f"Failed to initialize registry: {str(e)}")
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
            log.error(f"Error during cleanup: {str(e)}")

    def get_card_by_id(self, card_id: str) -> Optional[Card]:
        """
        Get a card by its ID.

        :param card_id: The unique string ID of the card.
        :return: The matching Card object, or None.
        """
        return self._cards.get(card_id)

    def get_set_by_id(self, set_id: str) -> Optional[CardSet]:
        """
        Get a set by its ID.

        :param set_id: The unique string ID of the set.
        :return: The matching CardSet object, or None.
        """
        return self._sets.get(set_id)

    def get_sets(self) -> List[CardSet]:
        """
        Get all known sets.

        :return: A list of CardSet objects.
        """
        return list(self._sets.values())

    async def get_card(self, query: str) -> Optional[Card]:
        """
        Get a card by ID or exact name search via YGOPro API.

        :param query: Card ID or name.
        :return: Card object if found, else None.
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
            log.error(f"Error getting card: {str(e)}")

        return None

    async def _process_card_data(self, card_data: Dict) -> Optional[Card]:
        """
        Convert raw API data into a Card instance, then fetch platform-specific
        status/rarity info.

        :param card_data: Dictionary of raw card data from YGOPro.
        :return: A properly populated Card object, or None on failure.
        """
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
                monster_type=card_data.get("frameType", "").lower()
                if "frameType" in card_data
                else None,
            )

            card_id = str(card.id)

            # Master Duel data
            try:
                md_data = await self.mdm_api.get_card_details(card_id)
                if md_data:
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
                log.debug(f"Error getting MD data for {card_id}: {str(e)}")

            # Duel Links data
            try:
                dl_data = await self.dlm_api.get_card_details(card_id)
                if dl_data:
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
                log.debug(f"Error getting DL data for {card_id}: {str(e)}")

            return card
        except Exception as e:
            log.error(f"Error processing card data: {str(e)}")
            return None

    def search_cards(self, query: str) -> List[Card]:
        """
        Search for cards by name (partial matches). Uses a tokenized
        index to find close matches.

        :param query: Partial or full card name to search.
        :return: A list of matching Card objects in descending order of frequency.
        """
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
            reverse=True,
        )

        return [self._cards[cid] for cid, _ in sorted_ids if cid in self._cards]

    async def update_registry(self) -> None:
        """
        Update the entire registry (sets, then mark last_update) within a lock.
        """
        async with self._update_lock:
            await self._update_sets()
            self._last_update = datetime.now()
            log.info("Registry updated successfully")

    async def _update_sets(self) -> None:
        """Fetch set data from Duel Links and Master Duel APIs and store them."""
        try:
            self._sets.clear()
            dl_sets = []
            md_sets = []

            # Duel Links sets
            try:
                dl_sets = await self.dlm_api.get_sets()
            except Exception as e:
                log.error(f"Error fetching DL sets: {str(e)}")

            # Master Duel sets
            try:
                md_sets = await self.mdm_api.get_sets()
            except Exception as e:
                log.error(f"Error fetching MD sets: {str(e)}")

            # Combine with extra sets
            for set_data in [*EXTRA_SETS, *dl_sets, *md_sets]:
                if isinstance(set_data, CardSet):
                    self._sets[set_data.id] = set_data

            log.info(f"Updated {len(self._sets)} sets")
        except Exception as e:
            log.error(f"Error updating sets: {str(e)}")
            raise

    def _generate_index_for_cards(self, cards: List[Card]) -> None:
        """
        Build or update the tokenized search index for a list of Cards.

        :param cards: The list of Card objects to index.
        """
        for card in cards:
            name = self._normalize_string(card.name)
            tokens = [name] + self._tokenize_string(name)

            for token in tokens:
                if token not in self._index:
                    self._index[token] = set()
                self._index[token].add(card.id)

    @staticmethod
    def _normalize_string(text: str) -> str:
        """
        Normalize a string for indexing by removing non-alphanumeric characters
        (except periods) and making it lowercase.

        :param text: The original string.
        :return: Normalized string.
        """
        return re.sub(r"[^a-z0-9.]", "", text.lower())

    @staticmethod
    def _tokenize_string(text: str) -> List[str]:
        """
        Create (and return) a list of 3-character tokens from the given string.

        :param text: The normalized string.
        :return: A list of substring tokens.
        """
        if len(text) < 3:
            return []
        return [text[i : i + 3] for i in range(len(text) - 2)]
