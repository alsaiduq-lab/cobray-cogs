"""Fuzzy search utility for Pokemon TCG cog."""
from typing import List, Dict, Any, Callable
from difflib import SequenceMatcher
import logging

log = logging.getLogger("red.pokemonmeta.utils.fsearch")

__all__ = ['fuzzy_search']

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
    
    Args:
        query: Search string
        items: List of dictionaries to search through
        key: Dictionary key to search in
        threshold: Minimum similarity ratio to include in results
        max_results: Maximum number of results to return
        exact_bonus: Bonus score for exact substring matches
    
    Returns:
        List of matching items, sorted by relevance
    """
    try:
        query = query.lower()
        matches = []
        
        for item in items:
            target = str(item.get(key, "")).lower()
            if not target:
                continue
                
            # Calculate base similarity ratio
            ratio = SequenceMatcher(None, query, target).ratio()
            
            # Add bonus for exact substring matches
            if query in target:
                ratio += exact_bonus
                
            # Add higher bonus for exact matches
            if query == target:
                ratio += exact_bonus * 2
                
            # Add bonus for starts with
            if target.startswith(query):
                ratio += exact_bonus
                
            if ratio >= threshold:
                matches.append({**item, "_score": ratio})
                
        # Sort by score and limit results
        matches.sort(key=lambda x: x["_score"], reverse=True)
        return matches[:max_results]
        
    except Exception as e:
        log.error(f"Error in fuzzy search: {str(e)}")
        return []
