import logging
import asyncio
from typing import Dict, List, Optional, Any
from .models import Card
from .api import BaseGameAPI

log = logging.getLogger("red.dlm.core.ygopro")

class YGOProAPI(BaseGameAPI):
    def __init__(self, *, log=None):
        """Initialize YGOProAPI.
        Args:
            log: Optional logger instance. If not provided, uses default logger.
        """
        logger = log or logging.getLogger("red.dlm.core.ygopro")
        super().__init__(base_url="https://db.ygoprodeck.com/api/v7", log=logger)
        self.timeout = 2.0
        self._cache: Dict[str, Any] = {}

    async def get_card_info(self, card_id: str) -> Optional[Card]:
        """Get detailed card information from YGOPRODeck."""
        cache_key = f"card_info_{card_id}"
        if cache_key in self._cache:
            return self._parse_card_data(self._cache[cache_key])
        try:
            async with asyncio.timeout(self.timeout):
                result = await self._make_request(
                    f"{self.BASE_URL}/cardinfo.php",
                    {"id": card_id},
                    request_headers={'Cache-Control': 'no-cache'}
                )
                if result and "data" in result:
                    card_data = result["data"][0]
                    self._cache[cache_key] = card_data
                    return self._parse_card_data(card_data)
        except asyncio.TimeoutError:
            log.warning(f"Timeout fetching card info for ID {card_id}")
        except Exception as e:
            log.error(f"Error fetching card info: {str(e)}")
        return None

    async def search_cards(self, query: str, *, is_autocomplete: bool = False) -> List[Card]:
        """Search for cards by name with improved error handling and caching."""
        cache_key = f"search_{query}"
        if not is_autocomplete and cache_key in self._cache:
            return [self._parse_card_data(card) for card in self._cache[cache_key]]
        try:
            params = {"fname": query}
            if len(query) <= 2:
                params["num"] = 10
                params["offset"] = 0
            async with asyncio.timeout(self.timeout):
                result = await self._make_request(
                    f"{self.BASE_URL}/cardinfo.php",
                    params,
                    request_headers={'Cache-Control': 'no-cache'}
                )
                if result and "data" in result:
                    if not is_autocomplete:
                        self._cache[cache_key] = result["data"]
                    return [self._parse_card_data(card) for card in result["data"]]
        except asyncio.TimeoutError:
            log.warning(f"Timeout searching cards for query: {query}")
        except Exception as e:
            log.error(f"Error searching cards: {str(e)}")
        return []

    def _parse_card_data(self, data: Dict[str, Any]) -> Optional[Card]:
        """Parse YGOPRODeck card data into Card model with improved validation and error handling."""
        try:
            # Validate required fields
            if not isinstance(data, dict):
                log.warning(f"Invalid card data type: {type(data)}")
                return None
                
            if not data.get("id") or not data.get("name"):
                log.warning(f"Missing required card data fields: {data}")
                return None

            # Safe type parsing
            def safe_int(value, default=None):
                if value is None:
                    return default
                try:
                    return int(str(value))
                except (ValueError, TypeError):
                    return default

            # Parse monster types
            monster_types = []
            monster_type = None
            if type_str := data.get("type"):
                if isinstance(type_str, str):
                    # Split and clean type string
                    parts = [p.strip() for p in type_str.replace("-", "/").split("/")]
                    monster_types = [p for p in parts if p]
                    if monster_types:
                        monster_type = monster_types[0]  # Primary type

            # Parse link markers as arrows
            arrows = None
            if link_markers := data.get("linkmarkers"):
                if isinstance(link_markers, list):
                    arrows = link_markers

            # Create card with validated data
            card = Card(
                id=str(data["id"]),
                name=str(data["name"]),
                type=str(data.get("type", "")).lower(),
                race=data.get("race"),
                monster_type=monster_type,
                monster_types=monster_types,
                attribute=data.get("attribute"),
                level=safe_int(data.get("level")),
                description=str(data.get("desc", "")),
                pendulum_effect=data.get("pendulum_effect"),
                atk=safe_int(data.get("atk")),
                def_=safe_int(data.get("def")),
                scale=safe_int(data.get("scale")),
                arrows=arrows,
                # Fields that YGOPro API doesn't provide set to defaults
                status_md=None,
                status_dl=None,
                status_tcg=None,
                status_ocg=None,
                status_goat=None,
                rarity_md=None,
                rarity_dl=None,
                image_url=None,
                url=None,
                sets_paper=[],
                sets_md=[],
                sets_dl=[],
                ocg=False
            )
            return card

        except Exception as e:
            log.error(f"Error parsing card data: {str(e)}", exc_info=True)
            return None
