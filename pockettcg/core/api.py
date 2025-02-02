import logging
import aiohttp
import asyncio
import time
from typing import Dict, List, Optional, Any
from urllib.parse import quote

LOGGER_NAME_BASE = "red.pokemonmeta"
log = logging.getLogger(f"{LOGGER_NAME_BASE}.core.api")

class PokemonMetaAPI:
    """API client for Pokemon Meta service."""
    BASE_URL = "https://www.pokemonmeta.com/api/v1"
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the API client."""
        if self._initialized:
            return

        log.debug("Initializing PokemonMetaAPI")
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limit = asyncio.Semaphore(3)
        self._cache: Dict[Any, Any] = {}
        self.cache_ttl = 300
        self._initialized = True
        log.info("PokemonMetaAPI initialized")

    async def initialize(self) -> None:
        """Initialize the API client session."""
        if not self.session or self.session.closed:
            log.debug("Creating new aiohttp session")
            self.session = aiohttp.ClientSession()
            log.info("API session created successfully")

    async def close(self) -> None:
        """Close the API client session."""
        if self.session and not self.session.closed:
            log.debug("Closing aiohttp session")
            await self.session.close()
            self.session = None
            log.info("API session closed successfully")
        self._initialized = False

    def _make_cache_key(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Generate a hashable cache key based on endpoint and parameters."""
        params_key = frozenset(sorted(params.items())) if params else None
        return (endpoint, params_key)

    def _get_cached(self, key: Any) -> Optional[Any]:
        """Retrieve a cached response if it exists and is not expired."""
        cached = self._cache.get(key)
        if cached:
            value, expires = cached
            if time.time() < expires:
                log.debug("Cache hit", extra={'cache_key': key})
                return value
            else:
                log.debug("Cache expired", extra={'cache_key': key})
                del self._cache[key]
        return None

    def _set_cache(self, key: Any, value: Any) -> None:
        """Store a value in the cache with the TTL."""
        expires = time.time() + self.cache_ttl
        self._cache[key] = (value, expires)
        log.debug(
            "Cache set",
            extra={
                'cache_key': key,
                'ttl': self.cache_ttl,
                'expires': expires
            }
        )

    @property
    def is_initialized(self) -> bool:
        """Check if the API client is initialized."""
        return self.session is not None and not self.session.closed

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if not self.is_initialized:
            log.debug("Session not initialized, creating new session")
            await self.initialize()
        return self.session

    async def _make_request(
        self,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        ignore_errors: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Make an HTTP request to the API."""
        if not self.is_initialized:
            await self.initialize()

        cache_key = self._make_cache_key(endpoint, params)
        if (cached_response := self._get_cached(cache_key)) is not None:
            return cached_response

        url = f"{self.BASE_URL}/{endpoint}"

        try:
            # Rate limiting - wait for our turn
            async with self.rate_limit:
                # Always wait at least 1 second between requests
                await asyncio.sleep(1.0)
                
                async with self.session.get(url, params=params) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        self._set_cache(cache_key, result)
                        return result
                    elif resp.status == 429:  # Too Many Requests
                        retry_after = int(resp.headers.get('Retry-After', '60'))
                        log.warning(f"Rate limited, waiting {retry_after} seconds")
                        await asyncio.sleep(retry_after)
                        return await self._make_request(endpoint, params=params, ignore_errors=ignore_errors)
                    elif not ignore_errors:
                        err_text = await resp.text()
                        log.error(
                            "API request failed",
                            extra={
                                'endpoint': endpoint,
                                'status': resp.status,
                                'error': err_text
                            }
                        )
                    return None
                    
        except asyncio.TimeoutError:
            log.error(f"API request timeout: {endpoint}")
            return None
        except Exception as e:
            log.error(f"API request error: {str(e)}", exc_info=True)
            return None

    async def get_card(self, card_id: str) -> Optional[Dict[str, Any]]:
        """Get a single card by ID."""
        log.debug("Fetching card", extra={'card_id': card_id})
        result = await self._make_request(f"cards/{card_id}")
        if result:
            log.debug("Card found directly", extra={'card_id': card_id})
            return result

        log.debug(
            "Card not found directly, trying as pokemonId",
            extra={'pokemon_id': card_id}
        )
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
        """Get cards matching specified filters."""
        log.debug(
            "Fetching cards with filters",
            extra={
                'type': type,
                'rarity': rarity,
                'pack': pack,
                'pokemon_id': pokemonId
            }
        )

        params: Dict[str, Any] = {}
        if type:
            params["type"] = type
        if rarity:
            params["rarity"] = rarity
        if pack:
            params["pack"] = pack
        if pokemonId:
            params["pokemonId"] = pokemonId

        data = await self._make_request("cards", params=params)
        result = data if isinstance(data, list) else []
        log.debug(
            "Card search completed",
            extra={
                'results_count': len(result),
                'filters': params
            }
        )
        return result

    async def search_cards(
        self,
        query: str,
        **params
    ) -> List[Dict[str, Any]]:
        """Search for cards by name."""
        log.debug("Searching cards", extra={'query': query, 'params': params})
        data = await self._make_request("cards")
        if not data or not isinstance(data, list):
            log.warning("No data received from API for card search")
            return []

        query = query.lower()
        filtered_cards = [
            card for card in data
            if query in card.get("name", "").lower()
        ]
        log.debug(
            "Card search completed",
            extra={
                'query': query,
                'results_count': len(filtered_cards)
            }
        )
        return filtered_cards[:25]

    async def get_all_cards(self) -> List[Dict[str, Any]]:
        """Get all available cards."""
        log.debug("Fetching all cards")
        data = await self._make_request("cards")
        result = data if isinstance(data, list) else []
        log.debug("Retrieved all cards", extra={'total_cards': len(result)})
        return result

    async def get_sets(self) -> List[Dict[str, Any]]:
        """Get all available sets."""
        log.debug("Fetching all sets")
        data = await self._make_request("sets")
        result = data if isinstance(data, list) else []
        log.debug("Retrieved all sets", extra={'total_sets': len(result)})
        return result

    async def get_set(self, set_id: str) -> Optional[Dict[str, Any]]:
        """Get a single set by ID."""
        log.debug("Fetching set", extra={'set_id': set_id})
        return await self._make_request(f"sets/{set_id}")

    def get_card_image_url(
        self,
        card: Dict[str, Any],
        variant_idx: int = 0
    ) -> Optional[str]:
        """Generate image URL for a card."""
        log.debug(
            "Generating card image URL",
            extra={
                'card_name': card.get('name', 'Unknown'),
                'variant_idx': variant_idx
            }
        )
        if art_variants := card.get("artVariants", []):
            if 0 <= variant_idx < len(art_variants):
                variant = art_variants[variant_idx]
                return f"{self.BASE_URL}/cards/{variant['_id']}/image"
        return None

    def get_set_image_url(self, set_data: Dict[str, Any]) -> Optional[str]:
        """Generate image URL for a set."""
        log.debug(
            "Generating set image URL",
            extra={'set_name': set_data.get('name', 'Unknown')}
        )
        if set_id := set_data.get("_id"):
            return f"{self.BASE_URL}/sets/{set_id}/image"
        return None

    def format_card_url(self, card_name: str, card_id: str) -> str:
        """Format a URL for a card's details page."""
        log.debug(
            "Formatting card URL",
            extra={
                'card_name': card_name,
                'card_id': card_id
            }
        )
        name_parts = [word.capitalize() for word in card_name.split()]
        formatted_name = quote(" ".join(name_parts))
        return f"{self.BASE_URL}/cards/{card_id}"
