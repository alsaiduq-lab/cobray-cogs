import json
import logging
import os
import random
import re
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Union
from urllib.parse import quote, urljoin

import pytz
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ContentDownloader:
    def __init__(
        self,
        api_base_url: str = "https://www.pokemonmeta.com/api/v1",
        cdn_base_url: str = "https://s3.duellinksmeta.com",
        min_delay: int = 3,  # Reduced delays for efficiency
        max_delay: int = 5,
        max_retries: int = 3,
    ):
        self.api_base_url = api_base_url
        self.cdn_base_url = cdn_base_url
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.session = self._setup_session()
        self.setup_logging()
        self.failed_downloads = []

    def _setup_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Referer": "https://www.pokemonmeta.com/",
                "Origin": "https://www.pokemonmeta.com",
            }
        )
        return session

    def setup_logging(self):
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"download_{current_time}.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(), logging.FileHandler(log_file)],
        )

    def _sanitize_filename(self, filename: str) -> str:
        sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename)
        sanitized = sanitized.strip(". ")
        return sanitized if sanitized else "unnamed"

    def _validate_card_id(self, card_id: str) -> bool:
        return bool(re.match(r"^[a-zA-Z0-9_-]+$", str(card_id)))

    def random_delay(self):
        delay = random.uniform(self.min_delay, self.max_delay)
        logging.info(f"Waiting {delay:.2f} seconds...")
        time.sleep(delay)

    def fetch_all_cards(self) -> list:
        try:
            params = {"limit": 0}
            url = f"{self.api_base_url}/cards"
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            logging.info(f"Successfully fetched all cards: {len(data)} total cards")
            return data
        except Exception as e:
            logging.error(f"Error fetching all cards: {str(e)}")
            raise

    def fetch_card_data(self, card_name: str) -> list:
        try:
            params = {"name": card_name, "limit": 0}
            url = f"{self.api_base_url}/cards"
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            logging.info(f"Successfully fetched data for card: {card_name}")
            return data
        except Exception as e:
            logging.error(f"Error fetching card data: {str(e)}")
            raise

    def fetch_deck_data(self, card_ids: list, limit: int = 10) -> list:
        try:
            params = {"main.card[$in]": ",".join(card_ids), "sort": "-created", "fields": "-_id,-__v", "limit": limit}
            url = f"{self.api_base_url}/top-decks"
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            logging.info(f"Successfully fetched deck data for cards: {card_ids}")
            return data
        except Exception as e:
            logging.error(f"Error fetching deck data: {str(e)}")
            raise

    def process_image_url(self, card_id: str, size: str = "w420") -> str:
        return f"{self.cdn_base_url}/pkm_img/cards/{card_id}_{size}.webp"

    def save_json_data(self, data: dict, save_path: Path) -> None:
        temp_path = save_path.with_suffix(".temp.json")
        try:
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with temp_path.open("w", encoding="utf-8") as f:
                f.write(json_str)
            temp_path.rename(save_path)
            logging.info(f"Successfully saved data to {save_path}")
        except Exception as e:
            logging.error(f"Error saving data: {str(e)}")
            if temp_path.exists():
                temp_path.unlink()
            raise

    def download_card_image(self, card_id: str, save_path: Path, size: str = "w420") -> bool:
        if not self._validate_card_id(card_id):
            logging.error(f"Invalid card ID format: {card_id}")
            return False

        url = self.process_image_url(card_id, size)
        temp_path = save_path.with_suffix(".temp")

        try:
            logging.info(f"Downloading image: {url}")
            response = self.session.get(url, stream=True, timeout=30)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if not content_type.startswith(("image/webp", "image/png", "image/jpeg")):
                raise ValueError(f"Invalid content type: {content_type}")

            save_path.parent.mkdir(parents=True, exist_ok=True)
            with temp_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            temp_path.rename(save_path)
            logging.info(f"Successfully downloaded: {save_path}")
            return True
        except Exception as e:
            logging.error(f"Download error for {url}: {str(e)}")
            self.failed_downloads.append((url, str(e)))
            return False
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _get_last_update_time(self, cache_dir: Path) -> datetime:
        """Get the timestamp of last update."""
        timestamp_file = cache_dir / "last_update.json"
        if timestamp_file.exists():
            with timestamp_file.open("r") as f:
                data = json.load(f)
                return datetime.fromisoformat(data["last_update"])
        return datetime.min.replace(tzinfo=pytz.UTC)

    def _save_update_time(self, cache_dir: Path):
        """Save current time as last update."""
        timestamp_file = cache_dir / "last_update.json"
        with timestamp_file.open("w") as f:
            json.dump({"last_update": datetime.now(pytz.UTC).isoformat()}, f)

    def _get_existing_files(self, cards_dir: Path) -> Dict[str, Set[str]]:
        """Get mapping of card names to their IDs from existing files."""
        card_mapping = {}
        if not cards_dir.exists():
            return card_mapping
        for file in cards_dir.glob("*.json"):
            if file.stem.endswith("_decks"):
                continue
            try:
                name, card_id = file.stem.rsplit("_", 1)
                if name not in card_mapping:
                    card_mapping[name] = set()
                card_mapping[name].add(card_id)
            except ValueError:
                continue
        return card_mapping

    def needs_update(self, card: dict, existing_files: Dict[str, Set[str]]) -> bool:
        """Check if card or its variants need updating."""
        card_name = self._sanitize_filename(card.get("name", "unnamed"))
        card_id = str(card.get("_id", ""))
        # Check if this is a new card
        if card_name not in existing_files:
            return True
        # Check if this variant exists
        if card_id not in existing_files[card_name]:
            return True
        # Check alt art variants
        if "artVariants" in card:
            for variant in card["artVariants"]:
                variant_id = str(variant.get("_id", ""))
                if variant_id and variant_id not in existing_files[card_name]:
                    return True
        return False

    def update_cards(self, cache_dir: Path):
        """Update card data and images."""
        cards_dir = cache_dir / "cards"
        cards_dir.mkdir(exist_ok=True)

        # Get existing files
        existing_files = self._get_existing_files(cards_dir)
        logging.info(f"Found {sum(len(ids) for ids in existing_files.values())} existing card files")

        # Get all current cards
        all_cards = self.fetch_all_cards()
        total_cards = len(all_cards)
        logging.info(f"Found {total_cards} total cards")

        # Group cards by name to handle variants together
        card_groups = {}
        for card in all_cards:
            name = self._sanitize_filename(card.get("name", "unnamed"))
            if name not in card_groups:
                card_groups[name] = []
            card_groups[name].append(card)

        updated_count = 0
        for card_name, cards in card_groups.items():
            needs_update = any(self.needs_update(card, existing_files) for card in cards)
            if not needs_update:
                logging.info(f"Skipping up-to-date card group: {card_name}")
                continue

            logging.info(f"Processing card group: {card_name}")
            card_ids = []

            for card in cards:
                card_id = str(card.get("_id", ""))
                if not self._validate_card_id(card_id):
                    logging.error(f"Invalid card ID: {card_id}")
                    continue

                # Save card data
                card_file = cards_dir / f"{card_name}_{card_id}.json"
                self.save_json_data(card, card_file)

                # Download card image
                img_file = cards_dir / f"{card_name}_{card_id}.webp"
                if not img_file.exists():
                    if self.download_card_image(card_id, img_file):
                        self.random_delay()

                card_ids.append(card_id)

                # Handle art variants
                if "artVariants" in card:
                    for variant in card["artVariants"]:
                        variant_id = str(variant.get("_id", ""))
                        if not self._validate_card_id(variant_id):
                            continue

                        variant_file = cards_dir / f"{card_name}_{variant_id}.json"
                        self.save_json_data(variant, variant_file)

                        variant_img = cards_dir / f"{card_name}_{variant_id}.webp"
                        if not variant_img.exists():
                            if self.download_card_image(variant_id, variant_img):
                                self.random_delay()

                        card_ids.append(variant_id)

            # Update deck data for all variants at once
            if card_ids:
                deck_data = self.fetch_deck_data(card_ids)
                deck_file = cards_dir / f"{card_name}_decks.json"
                self.save_json_data(deck_data, deck_file)
                updated_count += 1
                self.random_delay()

        # Save update timestamp
        self._save_update_time(cache_dir)
        logging.info(f"Update complete. Updated {updated_count} card groups")


def main():
    try:
        script_dir = Path(__file__).parent
        base_dir = script_dir.parent.parent
        cache_dir = base_dir / "assets" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        downloader = ContentDownloader()
        downloader.update_cards(cache_dir)
        logging.info("Update completed successfully!")

    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        raise


if __name__ == "__main__":
    main()
