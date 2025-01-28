import logging
import re
from difflib import SequenceMatcher
from typing import List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

def sanitize_text(text: str) -> str:
    """
    Normalize text by:
      – Lowercasing
      – Stripping leading/trailing spaces
      – Removing punctuation/dashes/apostrophes
      – Collapsing multiple spaces
    """
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text

def get_similarity(a: str, b: str) -> float:
    """
    Calculate similarity ratio between two sanitized strings.
    If 'a' is entirely contained in 'b', treat that as a near-perfect match.
    Otherwise, use SequenceMatcher's ratio.
    """
    if a in b:
        return 0.95
    return SequenceMatcher(None, a, b).ratio()

def fuzzy_search(
    query: str,
    items: List[Dict[str, Any]],
    key: str = "name",
    threshold: float = 0.4,
    max_results: int = 5,
    exact_bonus: float = 0.3,
    alt_names_key: str = "alt_names"
) -> List[Dict[str, Any]]:
    """
    Fuzzy search for Yu-Gi-Oh! cards, with special handling of exact matches and alt names.

    Args:
        query:              The user's search term (unsanitized).
        items:              List of dicts representing cards.
        key:                The dict key for the "primary" name (default: "name").
        threshold:          Minimum similarity score required to qualify (0–1).
        max_results:        How many final matches to return.
        exact_bonus:        Extra points added if the query is a substring match.
        alt_names_key:      Optional dict key where alternate titles are stored (list of strings).

    Returns:
        A list of matching items, sorted by descending similarity score.

    Structure of each item:
        {
          "name": "Dark Magician",
          "alt_names": [
             "Dark Magician (Arkana)",
             "Dark Magician (Movie Promo)"
             ...
          ],
          ... other fields ...
        }
    """
    try:
        if not isinstance(query, str):
            raise TypeError("Query must be a string")
        if not isinstance(items, list):
            raise TypeError("Items must be a list")
        if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
            raise ValueError("Threshold must be a number between 0 and 1")

        query_sanitized = sanitize_text(query)
        if not query_sanitized:
            return []

        log.debug(f"Performing fuzzy search for '{query_sanitized}' with threshold {threshold}")
        results = []

        for item in items:
            if not isinstance(item, dict):
                log.warning(f"Skipping non-dict item: {item}")
                continue
            if key not in item:
                log.warning(f"Key '{key}' not found in item: {item}")
                continue

            main_name_sanitized = sanitize_text(str(item[key]))
            if not main_name_sanitized:
                continue

            alt_names = item.get(alt_names_key, [])
            alt_names = alt_names if isinstance(alt_names, list) else []
            alt_names_sanitized = [sanitize_text(alt) for alt in alt_names]

            if query_sanitized == main_name_sanitized or query_sanitized in alt_names_sanitized:
                exact_score = 1.0
                item_copy = item.copy()
                item_copy['_score'] = exact_score
                results.append(item_copy)
                continue

            score_main = get_similarity(query_sanitized, main_name_sanitized)

            score_alts = [get_similarity(query_sanitized, alt) for alt in alt_names_sanitized]
            best_alt_score = max(score_alts) if score_alts else 0.0

            best_score = max(score_main, best_alt_score)

            if query_sanitized in main_name_sanitized or any(query_sanitized in alt for alt in alt_names_sanitized):
                best_score += exact_bonus

            if main_name_sanitized.startswith(query_sanitized):
                best_score += 0.1

            dynamic_threshold = max(threshold, 0.3 + (len(query_sanitized) * 0.03))

            if best_score >= dynamic_threshold:
                item_copy = item.copy()
                item_copy['_score'] = min(best_score, 1.0)
                results.append(item_copy)

        sorted_results = sorted(results, key=lambda x: x['_score'], reverse=True)
        final_results = sorted_results[:max_results]
        log.debug(f"Found {len(final_results)} matches from {len(results)} candidates.")
        return final_results

    except Exception as e:
        log.error(f"Fatal error in fuzzy search: {e}", exc_info=True)
        return []
