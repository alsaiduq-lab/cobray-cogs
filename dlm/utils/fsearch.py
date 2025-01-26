import logging
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Union

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fuzzy_search(
    query: str, 
    items: List[Dict], 
    key: str = "title", 
    threshold: float = 0.6
) -> List[Dict]:
    """
    Perform fuzzy search on a list of dictionaries.
    
    Args:
        query: Search term
        items: List of dictionaries to search through
        key: Dictionary key to search in
        threshold: Minimum similarity score (0-1)
        
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
            
        def similarity(a: str, b: str) -> float:
            try:
                return SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()
            except Exception as e:
                logger.error(f"Error calculating similarity: {e}")
                return 0.0
        
        results = []
        query = query.lower()
        logger.info(f"Performing fuzzy search for '{query}' with threshold {threshold}")
        
        for item in items:
            try:
                if not isinstance(item, dict):
                    logger.warning(f"Skipping non-dictionary item: {item}")
                    continue
                    
                if key not in item:
                    logger.warning(f"Key '{key}' not found in item: {item}")
                    continue
                    
                item_value = str(item[key])
                score = similarity(query, item_value)
                
                if score >= threshold:
                    item_copy = item.copy()
                    item_copy['_score'] = score
                    results.append(item_copy)
                    
            except Exception as e:
                logger.error(f"Error processing item {item}: {e}")
                continue
        
        logger.info(f"Found {len(results)} matches")
        return sorted(results, key=lambda x: x['_score'], reverse=True)
        
    except Exception as e:
        logger.error(f"Fatal error in fuzzy search: {e}")
        return []
