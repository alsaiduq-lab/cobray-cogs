from difflib import SequenceMatcher
from typing import List, Dict

def fuzzy_search(query: str, items: List[Dict], key: str = "title", threshold: float = 0.6) -> List[Dict]:
    def similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
    
    results = []
    query = query.lower()
    
    for item in items:
        if not isinstance(item, dict) or key not in item:
            continue
        item_value = str(item[key])
        score = similarity(query, item_value)
        if score >= threshold:
            item['_score'] = score
            results.append(item)
    
    return sorted(results, key=lambda x: x['_score'], reverse=True)
