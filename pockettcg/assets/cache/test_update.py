import json
from pathlib import Path
import requests
import logging

class ContentDownloader:
    def __init__(self, api_base_url: str = "https://www.pokemonmeta.com/api/v1"):
        self.api_base_url = api_base_url
        self.session = requests.Session()
        self.setup_logging()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def fetch_all_cards(self) -> list:
        try:
            params = {'limit': 0}
            url = f"{self.api_base_url}/cards"
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            logging.info(f"Fetched {len(data)} cards")
            return data
        except Exception as e:
            logging.error(f"Error fetching cards: {str(e)}")
            raise

    def save_card_ids(self, cache_dir: Path):
        cards = self.fetch_all_cards()
        card_ids = [card["_id"] for card in cards if "_id" in card]
        save_path = cache_dir / "processed_cards.json"
        with save_path.open('w', encoding='utf-8') as f:
            json.dump(card_ids, f, indent=2)
        logging.info(f"Saved {len(card_ids)} card IDs to {save_path}")

def main():
    cache_dir = Path("/home/cobray/cobray-cogs/pockettcg/assets/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    downloader = ContentDownloader()
    downloader.save_card_ids(cache_dir)

if __name__ == "__main__":
    main()
