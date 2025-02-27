import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime, timezone
import logging
import requests
import os

class TCGCacheManager:
    def __init__(self, cache_dir: Union[str, Path], api_base_url: str):
        self.cache_dir = Path(cache_dir)
        self.cards_dir = self.cache_dir / "cards"
        self.cards_dir.mkdir(parents=True, exist_ok=True)
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

    def save_cards(self, card_data: List[Dict], append: bool = True) -> None:
        """Save card data, handling both old (string IDs) and new (dict) formats."""
        try:
            existing_data = self.load_cards() or []
            new_data_count = len(card_data)

            # Normalize existing data to dict format
            normalized_existing = []
            for item in existing_data:
                if isinstance(item, str):
                    normalized_existing.append({"id": item, "name": "Unknown"})
                elif isinstance(item, dict) and "id" in item:
                    normalized_existing.append(item)

            if append and normalized_existing:
                all_data = {d["id"]: d for d in normalized_existing}
                all_data.update({d["id"]: d for d in card_data})
                all_cards = list(all_data.values())
                added_count = len(all_cards) - len(normalized_existing)
            else:
                all_cards = card_data
                added_count = new_data_count

            # Save to processed_cards.json
            with self.cards_cache.open('w', encoding='utf-8') as f:
                json.dump(all_cards, f, indent=2)

            # Save to individual files in cards/
            for card in all_cards:
                card_id = card["id"]
                card_name = card["name"].replace(" ", "_").replace("/", "_")
                filename = f"{card_name}_{card_id}.json"
                with (self.cards_dir / filename).open('w', encoding='utf-8') as f:
                    json.dump(card, f, indent=2)

            self._update_cache_info("cards")
            logging.info(f"Saved {len(all_cards)} unique cards to cards/ (added {added_count} new from {new_data_count})")
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

    def load_cards(self) -> Optional[List[Dict]]:
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
            with self.cache_info.open('w', encoding='utf-8') as f:
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
            for f in self.cards_dir.glob("*.json"):
                f.unlink()
            logging.info("Cache cleared successfully")
        except Exception as e:
            logging.error(f"Error clearing cache: {e}")
            raise

    def update_from_api(self, set_name: str = "Triumphant Light") -> None:
        try:
            sets_url = f"{self.api_base_url}/sets"
            sets_response = requests.get(sets_url)
            sets_response.raise_for_status()
            sets_data = sets_response.json()
            logging.debug(f"Sets response: {sets_data}")

            target_set = next((s for s in sets_data if s.get("name") == set_name), None)
            if not target_set:
                logging.warning(f"{set_name} not found in sets. Using fallback.")
                target_set = {"name": set_name}
            self.save_sets([target_set])
        except requests.RequestException as e:
            logging.error(f"Error fetching sets: {e}")
            self.save_sets([{"name": set_name}])
            return

        try:
            cards_url = f"{self.api_base_url}/cards"
            all_card_data = []
            offset = 0
            limit = 100
            max_ids = 300

            while True:
                params = {"set": set_name, "limit": limit, "offset": offset}
                logging.info(f"Fetching {set_name} cards, offset {offset}")
                response = requests.get(cards_url, params=params)
                response.raise_for_status()
                cards_data = response.json()
                logging.debug(f"First 5 cards (offset {offset}): {[card.get('name') for card in cards_data[:5]]}")

                if not cards_data:
                    logging.info(f"No more cards for {set_name} at offset {offset}")
                    break

                page_data = [
                    {"id": card["_id"], "name": card["name"]}
                    for card in cards_data if "_id" in card and "name" in card
                ]
                all_card_data.extend(page_data)
                logging.info(f"Fetched {len(page_data)} cards at offset {offset}")

                if len(page_data) < limit or len(all_card_data) >= max_ids:
                    break

                offset += limit

            # Fallback for Arceus ex
            arceus_id = "67c0591452e93386721e093b"
            if not any(card["id"] == arceus_id for card in all_card_data):
                logging.info("Arceus ex not found, fetching by name")
                params = {"name": "Arceus ex", "limit": 1}
                response = requests.get(cards_url, params=params)
                cards_data = response.json()
                if cards_data:
                    all_card_data.append({"id": arceus_id, "name": "Arceus ex"})
                    logging.info(f"Added Arceus ex: {arceus_id}")

            if not all_card_data:
                logging.warning(f"No Triumphant Light cards found")
                return

            self.save_cards(all_card_data, append=True)
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
    print("Loaded cards:", cache_mgr.load_cards())
    print("Cache info:", cache_mgr.get_cache_info())
