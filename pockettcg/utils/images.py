import aiohttp
import logging
from typing import Dict, List, Optional, Tuple
import asyncio
from functools import lru_cache

class ImagePipeline:
    """Handles image processing and URL generation for Pokemon cards."""
    def __init__(self, *, log=None):
        self.logger = log or logging.getLogger("red.pokemonmeta.images")
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limit = asyncio.Semaphore(3)
        self.BASE_URL = "https://www.pokemonmeta.com"

    async def initialize(self):
        """Initialize the image pipeline."""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """Close the image pipeline."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def _is_url_available(self, url: str) -> bool:
        """Check if a URL returns a 200 status code."""
        if not self.session or self.session.closed:
            await self.initialize()
        async with self.rate_limit:
            await asyncio.sleep(0.5)
            try:
                async with self.session.head(url, timeout=5) as resp:
                    return resp.status == 200
            except Exception as e:
                self.logger.debug(f"Error checking URL {url}: {str(e)}")
                return False

    async def get_image_url(self, card_id: str, variant_idx: int = 0) -> Tuple[bool, str]:
        """Get the image URL for a card.
        Args:
            card_id: Card's unique identifier
            variant_idx: Art variant index to use
        Returns:
            Tuple of (success, url)
        """
        if not self.session or self.session.closed:
            await self.initialize()
        self.logger.debug(f"Attempting to get image for card ID: {card_id}")

        variant_url = f"{self.BASE_URL}/pkm_img/cards/{card_id}_{variant_idx}.webp"
        if await self._is_url_available(variant_url):
            return True, variant_url

        base_url = f"{self.BASE_URL}/pkm_img/cards/{card_id}.webp"
        if await self._is_url_available(base_url):
            return True, base_url

        self.logger.debug("No image found for card")
        return False, "Card image not found"

    async def get_set_image_url(self, set_id: str) -> Tuple[bool, str]:
        """Get the image URL for a set.
        Args:
            set_id: Set's unique identifier
        Returns:
            Tuple of (success, url)
        """
        if not self.session or self.session.closed:
            await self.initialize()
        url = f"{self.BASE_URL}/pkm_img/Sets/{set_id}.webp"
        if await self._is_url_available(url):
            return True, url
        return False, "Set image not found"
