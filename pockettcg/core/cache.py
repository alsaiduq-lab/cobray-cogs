import os
import json
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

LOGGER_NAME_BASE = "red.pokemonmeta"
log = logging.getLogger(f"{LOGGER_NAME_BASE}.core.cache")

class Cache:
    """
    File-based caching system for Pokemon TCG data.
    
    Handles caching of card data, images, and related assets while maintaining
    a memory cache for frequently accessed items.
    """
    
    def __init__(self, ttl: int = 3600, *, cache_dir: str = "assets/cache/cards"):
        """Initialize the cache system.
        
        Args:
            ttl: Time-to-live in seconds for cached items
            cache_dir: Path to the cache directory, relative to cog root
        """
        self.ttl = max(1, ttl)  # Ensure positive TTL
        self._cache: Dict[str, Dict[str, Any]] = {}  # Memory cache
        
        # Resolve cache directory relative to cog root
        cog_root = Path(__file__).parent.parent
        self.cache_dir = (cog_root / cache_dir).resolve()
        
        # Initialize cache directory
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log.critical(f"Failed to create cache directory: {e}", exc_info=True)
            raise
            
        log.info(f"Cache initialized at: {self.cache_dir}")

    def get(self, key: str) -> Optional[Any]:
        """Retrieve an item from cache.
        
        Args:
            key: Cache key to look up
            
        Returns:
            Cached data if found and valid, None otherwise
        """
        if not key or not isinstance(key, str):
            return None
            
        # Check memory cache first
        if data := self._get_from_memory(key):
            return data
            
        # Fall back to file cache
        return self._get_from_file(key)

    def set(self, key: str, value: Any, persist: bool = True) -> bool:
        """Store an item in cache.
        
        Args:
            key: Cache key
            value: Data to cache
            persist: Whether to write to disk
            
        Returns:
            True if successful, False otherwise
        """
        if not key or not isinstance(key, str):
            return False
            
        try:
            # Update memory cache
            self._cache[key.lower()] = {
                'value': value,
                'timestamp': time.time()
            }
            
            # Write to disk if requested
            if persist:
                return self._write_to_file(key, value)
                
            return True
            
        except Exception as e:
            log.error(f"Failed to set cache entry: {e}", exc_info=True)
            return False

    def get_image_path(self, key: str) -> Optional[str]:
        """Get path to cached image file.
        
        Args:
            key: Cache key for image
            
        Returns:
            Path to image file if it exists, None otherwise
        """
        if not key:
            return None
            
        file_path = self._get_file_path(key, ".webp")
        return str(file_path) if file_path and file_path.is_file() else None

    def get_deck_data(self, key: str) -> Optional[Dict]:
        """Get cached deck data.
        
        Args:
            key: Cache key for deck data
            
        Returns:
            Deck data if found, None otherwise
        """
        if not key:
            return None
            
        file_path = self._get_file_path(key, "_decks.json")
        if file_path and file_path.is_file():
            return self._read_json_file(file_path)
        return None

    def _get_from_memory(self, key: str) -> Optional[Any]:
        """Check memory cache for valid entry."""
        cached = self._cache.get(key.lower())
        if not cached:
            return None
            
        # Check if entry is still valid
        if time.time() - cached['timestamp'] <= self.ttl:
            return cached['value']
            
        # Entry expired, remove it
        del self._cache[key.lower()]
        return None

    def _get_from_file(self, key: str) -> Optional[Any]:
        """Load item from file cache."""
        file_path = self._get_file_path(key, ".json")
        if not file_path or not file_path.is_file():
            return None
            
        data = self._read_json_file(file_path)
        if data is not None:
            # Update memory cache
            self._cache[key.lower()] = {
                'value': data,
                'timestamp': time.time()
            }
        return data

    def _write_to_file(self, key: str, value: Any) -> bool:
        """Write cache entry to file."""
        try:
            # Handle special case for card data
            card_id = None
            if isinstance(value, dict):
                card_id = value.get("id") or value.get("pokemonId")
            
            filename = self._get_safe_filename(key, card_id)
            file_path = self.cache_dir / filename
            
            # Write to temporary file first
            temp_path = file_path.with_suffix('.tmp')
            with temp_path.open('w', encoding='utf-8') as f:
                json.dump(value, f, indent=2, ensure_ascii=False)
                
            # Atomic rename
            temp_path.replace(file_path)
            return True
            
        except Exception as e:
            log.error(f"Failed to write cache file: {e}", exc_info=True)
            return False

    def _get_file_path(self, key: str, suffix: str) -> Optional[Path]:
        """Get path for cache file."""
        try:
            # Try exact match first
            filename = self._get_safe_filename(key)
            file_path = self.cache_dir / f"{filename}{suffix}"
            if file_path.is_file():
                return file_path
                
            # Search for files with card ID
            base_name = filename.lower()
            for path in self.cache_dir.glob(f"*{suffix}"):
                name = path.stem.lower()
                if name.startswith(f"{base_name}_") or name == base_name:
                    return path
                    
            return None
            
        except Exception as e:
            log.error(f"Error resolving file path: {e}", exc_info=True)
            return None

    def _read_json_file(self, path: Path) -> Optional[Any]:
        """Read and parse JSON file."""
        try:
            with path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to read JSON file {path}: {e}", exc_info=True)
            return None

    def _get_safe_filename(self, key: str, card_id: Optional[str] = None) -> str:
        """Generate safe filename from key."""
        # Remove surrounding quotes and normalize whitespace
        safe_name = key.strip("'\"").strip()
        
        if card_id:
            return f"{safe_name}_{card_id}"
        return safe_name

    def list_cached_cards(self) -> Dict[str, str]:
        """List all cached card data.
        
        Returns:
            Dictionary mapping normalized keys to original card names
        """
        cards = {}
        try:
            # Get all JSON files except deck data
            for path in self.cache_dir.glob("*.json"):
                if path.name.endswith("_decks.json"):
                    continue
                    
                data = self._read_json_file(path)
                if not data or not isinstance(data, dict):
                    continue
                    
                # Get card name from data or filename
                name = data.get("name", path.stem.split('_')[0].strip("'\""))
                cards[name.lower()] = name
                
        except Exception as e:
            log.error(f"Error listing cached cards: {e}", exc_info=True)
            
        return cards

    def refresh(self, key: str) -> Optional[Any]:
        """Refresh cache entry from disk.
        
        Args:
            key: Cache key to refresh
            
        Returns:
            Refreshed data if successful, None otherwise
        """
        # Remove from memory cache
        key_lower = key.lower()
        if key_lower in self._cache:
            del self._cache[key_lower]
            
        # Reload from file
        return self._get_from_file(key)

    def remove(self, key: str, remove_files: bool = False) -> bool:
        """Remove item from cache.
        
        Args:
            key: Cache key
            remove_files: Whether to delete associated files
            
        Returns:
            True if successful, False otherwise
        """
        success = True
        key_lower = key.lower()
        
        # Remove from memory cache
        if key_lower in self._cache:
            del self._cache[key_lower]
            
        # Remove files if requested
        if remove_files:
            for suffix in [".json", ".webp", "_decks.json"]:
                if file_path := self._get_file_path(key, suffix):
                    try:
                        file_path.unlink(missing_ok=True)
                    except Exception as e:
                        log.error(f"Failed to remove file {file_path}: {e}")
                        success = False
                        
        return success

    def clear(self) -> None:
        """Clear memory cache."""
        self._cache.clear()
