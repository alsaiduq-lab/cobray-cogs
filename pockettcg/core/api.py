import logging
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from urllib.parse import quote

class PokemonMetaAPI:
    """API Client for Pokemon Meta API."""
    BASE_URL = "https://www.pokemonmeta.com/api/v1"
    RARITY_MAPPING = {
        "d-1": "common",
        "d-2": "uncommon",
        "d-3": "rare",
        "d-4": "rare ultra",
        "d-5": "rare secret"
    }

    def __init__(self, *, log=None) -> None:
        """Initialize the API client."""
        self.logger = log or logging.getLogger("red.pokemonmeta.api")
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limit = asyncio.Semaphore(3)
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the API client session."""
        if self._initialized:
            return
        self.session = aiohttp.ClientSession()
        self._initialized = True
        self.logger.info("PokemonMeta API initialized")

    async def close(self) -> None:
        """Close the API client session."""
        if self.session and not self.session.closed:
            await self.session.close()
        self._initialized = False

    async def _make_request(
        self,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        ignore_errors: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Make a request to the Pokemon Meta API."""
        if not self._initialized:
            await self.initialize()

        url = f"{self.BASE_URL}/{endpoint}"
        try:
            async with self.rate_limit:
                await asyncio.sleep(0.5)  # Basic rate limiting
                async with self.session.get(url, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif not ignore_errors:
                        self.logger.error(
                            f"API request failed: {resp.status} - {await resp.text()}"
                        )
                    return None
        except asyncio.TimeoutError:
            self.logger.error(f"Request to {endpoint} timed out")
            return None
        except Exception as e:
            self.logger.error(f"API request error: {str(e)}")
            return None

    async def get_card(self, card_id: str) -> Optional[Dict[str, Any]]:
        """Get card details by ID or pokemonId."""
        result = await self._make_request(f"cards/{card_id}")
        if result:
            return result

        cards = await self.get_cards(pokemonId=card_id)
        return cards[0] if cards else None

    async def get_cards(
        self,
        *,
        type: Optional[str] = None,
        rarity: Optional[str] = None,
        pack: Optional[str] = None,
        pokemonId: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get cards with optional filters."""
        params = {}
        if type:
            params["type"] = type
        if rarity:
            params["rarity"] = rarity
        if pack:
            params["pack"] = pack
        if pokemonId:
            params["pokemonId"] = pokemonId

        data = await self._make_request("cards", params=params)
        return data if isinstance(data, list) else []

    async def search_cards(
        self,
        query: str,
        **params
    ) -> List[Dict[str, Any]]:
        """Search for cards by name and optional parameters."""
        data = await self._make_request("cards")
        if not data or not isinstance(data, list):
            return []
        query = query.lower()
        filtered_cards = []
        for card in data:
            if query in card.get("name", "").lower():
                filtered_cards.append(card)
        return filtered_cards[:25]  # Limit to 25 results

    async def get_all_cards(self) -> List[Dict[str, Any]]:
        """Get all available cards."""
        data = await self._make_request("cards")
        return data if isinstance(data, list) else []

    async def get_sets(self) -> List[Dict[str, Any]]:
        """Get all available sets."""
        data = await self._make_request("sets")
        return data if isinstance(data, list) else []

    async def get_set(self, set_id: str) -> Optional[Dict[str, Any]]:
        """Get set details by ID."""
        return await self._make_request(f"sets/{set_id}")

    def get_card_image_url(self, card: Dict[str, Any], variant_idx: int = 0) -> Optional[str]:
        """Generate card image URL."""
        BASE_IMAGE_URL = "https://www.pokemonmeta.com"
        if art_variants := card.get("artVariants", []):
            if 0 <= variant_idx < len(art_variants):
                variant = art_variants[variant_idx]
                return f"{BASE_IMAGE_URL}/pkm_img/cards/{variant['_id']}.webp"
        if obtain := card.get("obtain", []):
            for entry in obtain:
                if source := entry.get("source"):
                    if linked_article := source.get("linkedArticle"):
                        if image := linked_article.get("image"):
                            return f"{BASE_IMAGE_URL}{image}"
        if limitless_id := card.get("limitlessId"):
            return f"{BASE_IMAGE_URL}/pkm_img/cards/{limitless_id}.webp"
        return None

    def get_set_image_url(self, set_data: Dict[str, Any]) -> Optional[str]:
        """Generate set image URL."""
        BASE_IMAGE_URL = "https://www.pokemonmeta.com"
        if source := set_data.get("source"):
            if linked_article := source.get("linkedArticle"):
                if image := linked_article.get("image"):
                    return f"{BASE_IMAGE_URL}{image}"
        return None

    def format_card_url(self, card_name: str, card_id: str) -> str:
        """Generate properly formatted card URL."""
        name_parts = [word.capitalize() for word in card_name.split()]
        formatted_name = quote(" ".join(name_parts))
        return f"https://www.PokemonMeta.com/cards/{formatted_name}/{card_id}"
