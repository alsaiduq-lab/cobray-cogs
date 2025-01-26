import json
import aiohttp
from typing import Dict, List, Optional, Tuple

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
            if await self.is_ocg_available(card_id):
                return True, self._get_image_url(f"{card_id}_ocg")
            return False, "OCG art not available for this card"

        if await self._is_url_available(self._get_image_url(card_id)):
            return True, self._get_image_url(card_id)

        remote_art = self._get_remote_art_url(card_id)
        if await self._is_url_available(remote_art):
            return True, remote_art

        remote_image = self._get_remote_image_url(card_id)
        if await self._is_url_available(remote_image):
            return True, self._get_remote_imaginary_url(card_id, monster_types)

        return False, "Card image not found"

    async def is_ocg_available(self, card_id: str) -> bool:
        """Check if OCG art is available for a card."""
        url = self._get_image_url(f"{card_id}_ocg")
        return await self._is_url_available(url)

    async def _is_url_available(self, url: str) -> bool:
        """Check if a URL returns a 200 status code."""
        if not self.session:
            await self.initialize()
        try:
            async with self.session.head(url) as resp:
                return resp.status == 200
        except:
            return False

    def _get_image_url(self, card_id: str) -> str:
        """Get the base image URL."""
        return f"https://s3.lain.dev/ygo/{card_id}.webp"

    def _get_remote_art_url(self, card_id: str) -> str:
        """Get the remote cropped art URL."""
        return f"https://images.ygoprodeck.com/images/cards_cropped/{card_id}.jpg"

    def _get_remote_image_url(self, card_id: str) -> str:
        """Get the remote full image URL."""
        return f"https://images.ygoprodeck.com/images/cards/{card_id}.jpg"

    def _get_remote_imaginary_url(self, card_id: str, types: List[str]) -> str:
        """Get the processed image URL using imaginary service."""
        pipeline = []

        pipeline.append({
            "operation": "resize",
            "params": {
                "width": 590,
                "force": True
            }
        })

        if "Pendulum" in types:
            pipeline.append({
                "operation": "extract",
                "params": {
                    "top": 155,
                    "left": 40,
                    "areawidth": 510,
                    "areaheight": 380
                }
            })
        else:
            pipeline.append({
                "operation": "extract",
                "params": {
                    "top": 155,
                    "left": 70,
                    "areawidth": 450,
                    "areaheight": 450
                }
            })

        pipeline.append({
            "operation": "convert",
            "params": {
                "type": "webp"
            }
        })

        pipeline_json = json.dumps(pipeline)
        base_url = f"https://images.ygoprodeck.com/images/cards/{card_id}.jpg"
        return f"https://imaginary.lain.dev/pipeline?url={base_url}&operations={pipeline_json}"
