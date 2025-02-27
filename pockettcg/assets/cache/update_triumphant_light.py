import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime, timezone
import logging
import requests

class TCGCacheManager:
    def __init__(self, cache_dir: Union[str, Path], api_base_url: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sets_cache = self.cache_dir / "sets.json"
        self.cards_cache = self.cache_dir / "processed_cards.json"
        self.cache_info = self.cache_dir / "cache_info.yaml"
        self.api_base_url = api_base_url

    def save_sets(self, sets_data: List[Dict]) -> None:
        try:
            with self.sets_cache.open('w', encoding='utf-8') as f:
                json.dump(sets_data, f, indent=2)
            self._update_cache_info("sets")
            logging.info(f"Saved {len(sets_data)} sets to cache")
        except Exception as e:
            logging.error(f"Error saving sets cache: {e}")
            raise

    def save_cards(self, card_ids: List[str], append: bool = True) -> None:
        """Save a list of card IDs to processed_cards.json, optionally appending."""
        try:
            existing_ids = self.load_cards() or []
            new_ids_count = len(card_ids)
            if append and existing_ids:
                all_ids = list(set(existing_ids + card_ids))
                added_count = len(all_ids) - len(existing_ids)
            else:
                all_ids = list(set(card_ids))
                added_count = new_ids_count

            with self.cards_cache.open('w', encoding='utf-8') as f:
                json.dump(all_ids, f, indent=2)
            self._update_cache_info("cards")
            logging.info(f"Saved {len(all_ids)} unique card IDs (added {added_count} new from {new_ids_count})")
        except Exception as e:
            logging.error(f"Error saving cards cache: {e}")
            raise

    def load_sets(self) -> Optional[List[Dict]]:
        try:
            if self.sets_cache.exists():
                with self.sets_cache.open('r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            logging.error(f"Error loading sets cache: {e}")
            return None

    def load_cards(self) -> Optional[List[str]]:
        """Load list of card IDs from processed_cards.json."""
        try:
            if self.cards_cache.exists():
                with self.cards_cache.open('r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            logging.error(f"Error loading cards cache: {e}")
            return None

    def _update_cache_info(self, cache_type: str) -> None:
        try:
            cache_info = {}
            if self.cache_info.exists():
                with self.cache_info.open('r', encoding='utf-8') as f:
                    cache_info = yaml.safe_load(f) or {}
            cache_info[cache_type] = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "file_size": self._get_file_size(cache_type)
            }
            with self.cache_info.open('w', encoding='utf-8') as f:  # Fixed to cache_info
                yaml.safe_dump(cache_info, f)
        except Exception as e:
            logging.error(f"Error updating cache info: {e}")

    def _get_file_size(self, cache_type: str) -> int:
        cache_file = self.sets_cache if cache_type == "sets" else self.cards_cache
        return cache_file.stat().st_size if cache_file.exists() else 0

    def get_cache_info(self) -> Dict:
        try:
            if self.cache_info.exists():
                with self.cache_info.open('r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            return {}
        except Exception as e:
            logging.error(f"Error reading cache info: {e}")
            return {}

    def clear_cache(self) -> None:
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

    def update_from_api(self, set_name: str = "Triumphant Light") -> None:
        """Fetch and save set and card IDs from PokemonMetaTCG API without API key."""
        try:
            sets_url = f"{self.api_base_url}/sets"
            sets_response = requests.get(sets_url)
            sets_response.raise_for_status()
            sets_data = sets_response.json()

            target_set = next((s for s in sets_data if s.get("name") == set_name), None)
            if not target_set:
                logging.warning(f"{set_name} not found. Using fallback.")
                target_set = {"name": set_name}
            self.save_sets([target_set])
        except requests.RequestException as e:
            logging.error(f"Error fetching sets: {e}")
            self.save_sets([{"name": set_name}])
            return

        try:
            cards_url = f"{self.api_base_url}/cards"
            params = {"set": set_name}
            cards_response = requests.get(cards_url, params=params)
            cards_response.raise_for_status()
            cards_data = cards_response.json()

            if not cards_data:
                logging.warning(f"No cards found for {set_name} yet.")
                return

            card_ids = [card["_id"] for card in cards_data if "_id" in card]
            if not card_ids:
                logging.warning(f"No valid _id fields found in {set_name} cards.")
                return

            self.save_cards(card_ids, append=True)
        except requests.RequestException as e:
            logging.error(f"Error fetching cards: {e}")
            raise

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

if __name__ == "__main__":
    setup_logging()
    cache_dir = Path("/home/cobray/cobray-cogs/pockettcg/assets/cache")
    api_base_url = "https://www.pokemonmeta.com/api/v1"

    cache_mgr = TCGCacheManager(cache_dir, api_base_url)
    cache_mgr.update_from_api("Triumphant Light")

    print("Loaded sets:", cache_mgr.load_sets())
    print("Loaded card IDs:", cache_mgr.load_cards())
    print("Cache info:", cache_mgr.get_cache_info())
