import logging
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Union, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

def get_similarity(a: str, b: str) -> float:
    """Calculate similarity ratio between two strings."""
    try:
        if str(a).lower() in str(b).lower():
            return 1.0
        return SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()
    except Exception as e:
        log.error(f"Error calculating similarity: {e}")
        return 0.0

def fuzzy_search(
    query: str,
    items: List[Dict[str, Any]],
    key: str = "name",
    threshold: float = 0.4,
    max_results: int = 5,
    exact_bonus: float = 0.3
) -> List[Dict[str, Any]]:
    """
    Perform fuzzy search on a list of dictionaries with card-specific optimizations.
    Args:
        query: Search term
        items: List of dictionaries to search through
        key: Dictionary key to search in (default: "name" for card names)
        threshold: Minimum similarity score (0-1)
        max_results: Maximum number of results to return
        exact_bonus: Bonus score for exact substring matches
    Returns:
        List of matching items sorted by similarity score
    """
    try:
        if not isinstance(query, str):
            raise TypeError("Query must be a string")
        if not isinstance(items, list):
            raise TypeError("Items must be a list")
        if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
            raise ValueError("Threshold must be a number between 0 and 1")

        results = []
        query = query.lower().strip()
        if not query:
            return []

        log.debug(f"Performing fuzzy search for '{query}' with threshold {threshold}")

        for item in items:
            try:
                if not isinstance(item, dict):
                    log.warning(f"Skipping non-dictionary item: {item}")
                    continue
                if key not in item:
                    log.warning(f"Key '{key}' not found in item: {item}")
                    continue

                item_value = str(item[key]).lower()
                score = get_similarity(query, item_value)
                if query in item_value:
                    score += exact_bonus
                    if item_value.startswith(query):
                        score += 0.1

                dynamic_threshold = max(threshold, 0.3 + (len(query) * 0.05))
                if score >= dynamic_threshold:
                    item_copy = item.copy()
                    item_copy['_score'] = min(score, 1.0)
                    results.append(item_copy)

            except Exception as e:
                log.error(f"Error processing item {item}: {e}")
                continue

        sorted_results = sorted(results, key=lambda x: x['_score'], reverse=True)
        final_results = sorted_results[:max_results]
        log.debug(f"Found {len(final_results)} matches out of {len(results)} potential matches")
        return final_results

    except Exception as e:
        log.error(f"Fatal error in fuzzy search: {e}")
        return []
