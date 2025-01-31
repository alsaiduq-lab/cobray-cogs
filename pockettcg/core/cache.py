import time
from typing import Dict, Any, Optional
import logging

class Cache:
    def __init__(self, ttl: int = 3600, *, log=None):
        """Initialize cache with time-to-live in seconds."""
        self.ttl = ttl
        self.logger = log or logging.getLogger("red.pokemonmeta.cache")
        self._cache: Dict[str, Dict[str, Any]] = {}
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache if it exists and hasn't expired."""
        if key not in self._cache:
            return None
        entry = self._cache[key]
        if time.time() - entry["timestamp"] > self.ttl:
            self.logger.debug(f"Cache entry expired: {key}")
            del self._cache[key]
            return None
        self.logger.debug(f"Cache hit: {key}")
        return entry["value"]
    def set(self, key: str, value: Any):
        """Set a value in the cache."""
        self.logger.debug(f"Caching value for key: {key}")
        self._cache[key] = {
            "value": value,
            "timestamp": time.time()
        }
    def clear(self):
        """Clear all cached entries."""
        self.logger.info("Clearing cache")
        self._cache.clear()
    def remove(self, key: str):
        """Remove a specific key from cache."""
        if key in self._cache:
            self.logger.debug(f"Removing cache entry: {key}")
            del self._cache[key]
