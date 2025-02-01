import os
import json
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

class Cache:
    """Cache system with memory and file-based caching support."""
    def __init__(self, ttl: int = 3600, *, log=None, cache_dir: str = "assets/cached/cards"):
        """Initialize cache with time-to-live in seconds."""
        self.ttl = ttl
        self.logger = log or logging.getLogger("red.pokemonmeta.cache")
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    def _parse_cache_filename(self, filename: str) -> tuple[str, str]:
        """Parse a cache filename into name and id components.
        Example: "Zapdos_671ef0f25279bcfb3c1e2529.json" -> ("Zapdos", "671ef0f25279bcfb3c1e2529")
        """
        base = filename.rsplit('.', 1)[0]  # Remove extension
        if '_' in base:
            name, id_part = base.rsplit('_', 1)
            return name, id_part
        return base, ""

    def _get_file_path(self, key: str, suffix: str = ".json") -> Optional[Path]:
        """Get the full file path for a cache key, handling both direct IDs and names."""
        direct_path = self.cache_dir / f"{key}{suffix}"
        if direct_path.exists():
            return direct_path
        matching_files = list(self.cache_dir.glob(f"{key}_*{suffix}"))
        if matching_files:
            return matching_files[0]  # Return first match
        if suffix == ".json":
            return direct_path
        return None
    def _list_all_files(self, pattern: str = "*.json") -> Dict[str, Path]:
        """List all cached files matching pattern, keyed by card name."""
        files = {}
        for path in self.cache_dir.glob(pattern):
            name, _ = self._parse_cache_filename(path.name)
            files[name.lower()] = path
        return files
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache if it exists and hasn't expired."""
        key_lower = key.lower()
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["timestamp"] <= self.ttl:
                self.logger.debug(f"Memory cache hit: {key}")
                return entry["value"]
            self.logger.debug(f"Cache entry expired: {key}")
            del self._cache[key]
        if json_path := self._get_file_path(key, ".json"):
            try:
                with json_path.open('r') as f:
                    data = json.load(f)
                    self.set(key, data)  # Cache original key
                    name, id_part = self._parse_cache_filename(json_path.stem)
                    if id_part and id_part != key:
                        self.set(id_part, data, persist=False)  # Cache ID reference
                    self.logger.debug(f"File cache hit: {key} -> {json_path}")
                    return data
            except Exception as e:
                self.logger.error(f"Error reading cache file {json_path}: {str(e)}")
        all_files = self._list_all_files("*.json")
        if key_lower in all_files:
            try:
                with all_files[key_lower].open('r') as f:
                    data = json.load(f)
                    self.set(key, data)  # Cache in memory
                    self.logger.debug(f"File cache hit by name: {key}")
                    return data
            except Exception as e:
                self.logger.error(f"Error reading cache file {all_files[key_lower]}: {str(e)}")
        return None
    def set(self, key: str, value: Any, persist: bool = True):
        """Set a value in the cache."""
        self.logger.debug(f"Caching value for key: {key}")
        self._cache[key] = {
            "value": value,
            "timestamp": time.time()
        }
        if persist:
            json_path = self._get_file_path(key, ".json")
            try:
                with json_path.open('w') as f:
                    json.dump(value, f, indent=2)
                self.logger.debug(f"Persisted to file: {key}")
            except Exception as e:
                self.logger.error(f"Error writing cache file {json_path}: {str(e)}")
    def get_image_path(self, key: str) -> Optional[str]:
        """Get path to cached image file if it exists."""
        webp_path = self._get_file_path(key, ".webp")
        if webp_path.exists():
            return str(webp_path)
        return None
    def get_deck_data(self, key: str) -> Optional[Dict]:
        """Get cached deck data if it exists."""
        deck_path = self._get_file_path(key, "_decks.json")
        if deck_path.exists():
            try:
                with deck_path.open('r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Error reading deck data {deck_path}: {str(e)}")
        return None
    def clear(self):
        """Clear memory cache (file cache remains)."""
        self.logger.info("Clearing cache")
        self._cache.clear()
    def remove(self, key: str, remove_files: bool = False):
        """Remove a specific key from cache."""
        if key in self._cache:
            self.logger.debug(f"Removing cache entry: {key}")
            del self._cache[key]
        if remove_files:
            for suffix in [".json", ".webp", "_decks.json"]:
                file_path = self._get_file_path(key, suffix)
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except Exception as e:
                        self.logger.error(f"Error removing cache file {file_path}: {str(e)}")
    def list_cached_cards(self) -> Dict[str, str]:
        """List all cached cards, returning dict of {name: id}."""
        cards = {}
        for path in self.cache_dir.glob("*.json"):
            if not path.stem.endswith("_decks"):
                name, id_part = self._parse_cache_filename(path.stem)
                cards[name.lower()] = id_part or path.stem
        return cards
