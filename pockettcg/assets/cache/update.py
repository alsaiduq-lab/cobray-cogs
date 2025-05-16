import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime, timezone
import logging


class TCGCacheManager:
    def __init__(self, cache_dir: Union[str, Path]):
        """
        Initialize the cache manager.
        Args:
            cache_dir: Path to the cache directory
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sets_cache = self.cache_dir / "sets.json"
        self.cards_cache = self.cache_dir / "cards.json"
        self.cache_info = self.cache_dir / "cache_info.yaml"

    def save_sets(self, sets_data: List[Dict]) -> None:
        """Save sets data to cache."""
        try:
            with self.sets_cache.open("w", encoding="utf-8") as f:
                json.dump(sets_data, f, indent=2)
            self._update_cache_info("sets")
            logging.info(f"Saved {len(sets_data)} sets to cache")
        except Exception as e:
            logging.error(f"Error saving sets cache: {e}")
            raise

    def save_cards(self, cards_data: List[Dict]) -> None:
        """Save cards data to cache."""
        try:
            with self.cards_cache.open("w", encoding="utf-8") as f:
                json.dump(cards_data, f, indent=2)
            self._update_cache_info("cards")
            logging.info(f"Saved {len(cards_data)} cards to cache")
        except Exception as e:
            logging.error(f"Error saving cards cache: {e}")
            raise

    def load_sets(self) -> Optional[List[Dict]]:
        """Load sets from cache."""
        try:
            if self.sets_cache.exists():
                with self.sets_cache.open("r", encoding="utf-8") as f:
                    return json.load(f)
            return None
        except Exception as e:
            logging.error(f"Error loading sets cache: {e}")
            return None

    def load_cards(self) -> Optional[List[Dict]]:
        """Load cards from cache."""
        try:
            if self.cards_cache.exists():
                with self.cards_cache.open("r", encoding="utf-8") as f:
                    return json.load(f)
            return None
        except Exception as e:
            logging.error(f"Error loading cards cache: {e}")
            return None

    def _update_cache_info(self, cache_type: str) -> None:
        """Update cache information."""
        try:
            cache_info = {}
            if self.cache_info.exists():
                with self.cache_info.open("r", encoding="utf-8") as f:
                    cache_info = yaml.safe_load(f) or {}
            cache_info[cache_type] = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "file_size": self._get_file_size(cache_type),
            }
            with self.cache_info.open("w", encoding="utf-8") as f:
                yaml.safe_dump(cache_info, f)
        except Exception as e:
            logging.error(f"Error updating cache info: {e}")

    def _get_file_size(self, cache_type: str) -> int:
        """Get the size of a cache file in bytes."""
        cache_file = self.sets_cache if cache_type == "sets" else self.cards_cache
        return cache_file.stat().st_size if cache_file.exists() else 0

    def get_cache_info(self) -> Dict:
        """Get information about the cache."""
        try:
            if self.cache_info.exists():
                with self.cache_info.open("r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            return {}
        except Exception as e:
            logging.error(f"Error reading cache info: {e}")
            return {}

    def clear_cache(self) -> None:
        """Clear all cached data."""
        try:
            if self.sets_cache.exists():
                self.sets_cache.unlink()
            if self.cards_cache.exists():
                self.cards_cache.unlink()
            if self.cache_info.exists():
                self.cache_info.unlink()
            logging.info("Cache cleared successfully")
        except Exception as e:
            logging.error(f"Error clearing cache: {e}")
            raise


def setup_logging():
    """Setup basic logging configuration."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


if __name__ == "__main__":
    setup_logging()
    cache_dir = Path("/home/cobray/cobray-cogs/pockettcg/assets/cache")
    cache_mgr = TCGCacheManager(cache_dir)
    example_sets = [{"name": "Test Set"}]
    cache_mgr.save_sets(example_sets)
    loaded_sets = cache_mgr.load_sets()
    cache_info = cache_mgr.get_cache_info()
    print("Cache info:", cache_info)
