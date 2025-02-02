from typing import List, Dict, Any, Callable, Optional, Union
from difflib import SequenceMatcher

__all__ = ['fuzzy_search', 'fuzzy_search_multi']

def fuzzy_search(
    query: str,
    items: List[Dict[str, Any]],
    key: str,
    threshold: float = 0.4,
    max_results: int = 25,
    exact_bonus: float = 0.3
) -> List[Dict[str, Any]]:
    """
    Perform fuzzy search on a list of dictionaries.
    """
    query = query.lower()
    matches = []
    for item in items:
        target = str(item.get(key, "")).lower()
        if not target:
            continue

        if query == target:
            matches.append({**item, "_score": 2.0})  # Perfect match gets highest score
            continue
        if query in target:
            matches.append({**item, "_score": 1.5})  # Substring match gets high score
            continue

        ratio = SequenceMatcher(None, query, target).ratio()
        if target.startswith(query):
            ratio += exact_bonus
        if ratio >= threshold:
            matches.append({**item, "_score": ratio})

    matches.sort(key=lambda x: x["_score"], reverse=True)
    return matches[:max_results]

def fuzzy_search_multi(
    query: str,
    items: List[Dict[str, Any]],
    search_configs: List[Dict[str, Union[str, float, Callable]]],
    threshold: float = 0.4,
    max_results: int = 25
) -> List[Dict[str, Any]]:
    """
    Perform fuzzy search across multiple fields with different weights.
    Args:
        query: Search string
        items: List of dictionaries to search through
        search_configs: List of search configurations, each containing:
            - 'key': Field to search in
            - 'weight': Weight for this field's score (default: 1.0)
            - 'transform': Optional function to transform the value before comparison
            - 'exact_bonus': Bonus for exact matches (default: 0.3)
        threshold: Minimum similarity ratio to include in results
        max_results: Maximum number of results to return
    Returns:
        List of matching items, sorted by relevance
    """
    query = query.lower()
    matches = {}
    for item in items:
        max_score = 0
        for config in search_configs:
            key = config['key']
            weight = float(config.get('weight', 1.0))
            transform = config.get('transform', str)
            exact_bonus = float(config.get('exact_bonus', 0.3))
            raw_value = item.get(key)
            if raw_value is None:
                continue
            target = transform(raw_value).lower()
            ratio = SequenceMatcher(None, query, target).ratio() * weight
            if query in target:
                ratio += exact_bonus * weight
            if query == target:
                ratio += exact_bonus * 2 * weight
            if target.startswith(query):
                ratio += exact_bonus * weight
            max_score = max(max_score, ratio)
        if max_score >= threshold:
            matches[item.get('id')] = {**item, "_score": max_score}
    results = list(matches.values())
    results.sort(key=lambda x: x["_score"], reverse=True)
    return results[:max_results]
