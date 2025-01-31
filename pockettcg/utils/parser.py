import re
import logging
from typing import List, Dict, Any

class CardParser:
    def __init__(self, *, log=None):
        self.logger = log or logging.getLogger("red.pokemonmeta.parser")
    def extract_card_names(self, content: str) -> List[str]:
        """Extract card names from a message using [[CardName]] format."""
        if not content:
            return []
        pattern = r'\[\[(.*?)\]\]'
        matches = re.finditer(pattern, content)
        card_names = []
        for match in matches:
            name = match.group(1).strip()
            if name:
                card_names.append(name)
        return card_names
    def parse_card_query(self, query: str) -> Dict[str, Any]:
        """Parse a card search query with optional filters.
        Example:
        !card pikachu --type electric --rarity rare
        """
        parts = query.split('--')
        base_query = parts[0].strip()
        result = {
            "query": base_query,
            "filters": {}
        }
        if len(parts) > 1:
            for part in parts[1:]:
                if ':' in part:
                    key, value = part.split(':', 1)
                else:
                    key, value = part.split(None, 1)
                result["filters"][key.strip()] = value.strip()
        return result
