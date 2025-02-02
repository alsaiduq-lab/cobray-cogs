import logging
from typing import Dict, List, Optional, Tuple
import asyncio
from pathlib import Path
from urllib.parse import quote
from ..core.models import Pokemon
from ..core.api import PokemonMetaAPI

log = logging.getLogger("red.pokemonmeta.images")

class ImagePipeline:
    """Handles image processing and URL generation for Pokemon cards."""
    CDN_BASE = "https://s3.duellinksmeta.com"
    API_BASE = "https://www.pokemonmeta.com"
    CACHE_DIR = Path("assets/cache/cards/")

    def __init__(self):
        self.api = PokemonMetaAPI()  # Get the singleton instance
        self.rate_limit = asyncio.Semaphore(3)
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        """Initialize the image pipeline."""
        await self.api.initialize()

    async def close(self):
        """Close the image pipeline."""
        # Don't close the API session here, as it's shared
        pass

    def _get_cached_path(self, card_id: str) -> Optional[Path]:
        """Check if card image exists in local cache."""
        try:
            safe_id = str(card_id).strip()
            for file in self.CACHE_DIR.glob(f"*_{safe_id}.webp"):
                log.debug(f"Found cached image: {file}")
                return file
            for file in self.CACHE_DIR.glob("*.webp"):
                if safe_id in file.stem:
                    log.debug(f"Found cached image: {file}")
                    return file
            return None
        except Exception as e:
            log.error(f"Error checking cache path: {e}", exc_info=True)
            return None

    async def _check_url(self, url: str) -> bool:
        """Check if a URL returns a 200 status code."""
        session = await self.api.get_session()
        async with self.rate_limit:
            await asyncio.sleep(0.5)
            try:
                async with session.head(url, timeout=5) as resp:
                    return resp.status == 200
            except Exception as e:
                log.debug(f"Error checking URL {url}: {str(e)}")
                return False

    def get_cdn_card_url(self, card) -> Optional[str]:
        """Generate URL for a card, checking cache first."""
        try:
            # Get MongoDB ID
            mongo_id = getattr(card, '_id', None)

            if not mongo_id:
                log.warning(f"No MongoDB ID found for card: {getattr(card, 'name', 'Unknown')}")
                return None

            cached_path = self._get_cached_path(mongo_id)
            if cached_path:
                log.debug(f"Returning cached image path for {mongo_id}")
                return str(cached_path.absolute())

            url = f"{self.CDN_BASE}/pkm_img/cards/{mongo_id}_w360.webp"
            log.debug(f"Generated S3 URL: {url}")
            return url

        except Exception as e:
            log.error(f"Error generating card URL: {e}", exc_info=True)
            return None

    async def get_image_url(self, card_id: str, variant_idx: int = 0) -> Tuple[bool, str]:
        """Get the image URL for a card, checking cache first."""
        cached_path = self._get_cached_path(card_id)
        if cached_path:
            return True, str(cached_path.absolute())

        log.debug(f"Attempting to get image for card ID: {card_id}")
        variant_url = f"{self.API_BASE}/pkm_img/cards/{card_id}_{variant_idx}.webp"
        if await self._check_url(variant_url):
            return True, variant_url

        base_url = f"{self.API_BASE}/pkm_img/cards/{card_id}.webp"
        if await self._check_url(base_url):
            return True, base_url

        log.debug("No image found for card")
        return False, "Card image not found"
