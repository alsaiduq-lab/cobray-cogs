import logging
from pathlib import Path
from typing import Optional, Tuple, List
from ..core.cache import Cache

class ImagePipeline:
    def __init__(self):
        self.logger = logging.getLogger("red.pokemonmeta.images")
        self.cache = Cache()

    async def get_image_url(self, card_id: str, variant_idx: int = 0) -> Tuple[bool, str]:
        """Get the image URL for a card."""
        try:
            self.logger.debug(f"Getting image for card ID: {card_id} (variant: {variant_idx})")

            if image_path := self.cache.get_image_path(card_id):
                self.logger.debug(f"Found image: {image_path}")
                return True, image_path

            self.logger.debug(f"No image found for card ID: {card_id}")
            return False, "No images found"

        except Exception as e:
            self.logger.error(f"Error getting image for {card_id}: {e}", exc_info=True)
            return False, f"Error: {str(e)}"
