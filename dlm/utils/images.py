import json
import aiohttp
from typing import Dict, List, Optional, Tuple
from PIL import Image
import io
from functools import lru_cache

class ImagePipeline:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    async def get_image_url(self, card_id: str, monster_types: List[str], ocg: bool = False) -> Tuple[bool, str]:
        """Get the image URL for a card."""
        if ocg:
            remote_art = self._get_remote_art_url(f"{card_id}_ocg")
            if await self._is_url_available(remote_art):
                return True, remote_art
            return False, "OCG art not available for this card"

        remote_art = self._get_remote_art_url(card_id)
        if await self._is_url_available(remote_art):
            return True, remote_art

        success, image_data = await self._process_image(card_id, monster_types)
        if success:
            return True, f"https://images.ygoprodeck.com/images/cards/{card_id}.jpg"

        return False, "Card image not found"

    @lru_cache(maxsize=1000)
    def _get_crop_params(self, card_type: str) -> dict:
        if card_type == "Pendulum":
            return {"top": 155, "left": 40, "width": 510, "height": 380}
        return {"top": 155, "left": 70, "width": 450, "height": 450}

    async def _process_image(self, card_id: str, monster_types: List[str]) -> Tuple[bool, bytes]:
        """Process card image and return WebP bytes."""
        if not self.session:
            await self.initialize()

        try:
            url = f"https://images.ygoprodeck.com/images/cards/{card_id}.jpg"
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    return False, b""
                image_data = await resp.read()
                image = Image.open(io.BytesIO(image_data))
                image = image.resize((590, int(590 * image.height / image.width)))
                crop_params = self._get_crop_params("Pendulum" if "Pendulum" in monster_types else "Normal")
                image = image.crop((
                    crop_params["left"],
                    crop_params["top"],
                    crop_params["left"] + crop_params["width"],
                    crop_params["top"] + crop_params["height"]
                ))
                output = io.BytesIO()
                image.save(output, format="WEBP", quality=90)
                return True, output.getvalue()
        except Exception:
            return False, b""

    async def is_ocg_available(self, card_id: str) -> bool:
        """Check if OCG art is available for a card."""
        remote_art = self._get_remote_art_url(f"{card_id}_ocg")
        return await self._is_url_available(remote_art)

    async def _is_url_available(self, url: str) -> bool:
        """Check if a URL returns a 200 status code."""
        if not self.session:
            await self.initialize()
        try:
            async with self.session.head(url, timeout=5) as resp:
                return resp.status == 200
        except:
            return False

    def _get_remote_art_url(self, card_id: str) -> str:
        """Get the remote cropped art URL."""
        return f"https://images.ygoprodeck.com/images/cards_cropped/{card_id}.jpg"
