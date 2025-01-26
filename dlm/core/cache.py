from typing import Optional, Dict, Any
import time
import aiohttp
from datetime import datetime, timedelta

__all__ = [
    "DLMCache",
    "DLMAPIError",
    "DLMRateLimitError",
    "DLMNotFoundError",
    "DLMServerError",
    "handle_api_response",
    "parse_cache_control"
]

class DLMCache:
    def __init__(self):
        self.cache = {}
    def set(self, key: str, value: Any, ttl: int = 300):
        self.cache[key] = {
            'value': value,
            'expires': time.time() + ttl
        }
    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            cache_data = self.cache[key]
            if time.time() < cache_data['expires']:
                return cache_data['value']
            del self.cache[key]
        return None
    def clear(self):
        self.cache.clear()

class DLMAPIError(Exception):
    pass

class DLMRateLimitError(DLMAPIError):
    pass

class DLMNotFoundError(DLMAPIError):
    pass

class DLMServerError(DLMAPIError):
    pass

async def handle_api_response(response: aiohttp.ClientResponse) -> Dict:
    if response.status == 200:
        return await response.json()
    elif response.status == 404:
        raise DLMNotFoundError("Resource not found")
    elif response.status == 429:
        raise DLMRateLimitError("Rate limit exceeded")
    elif response.status >= 500:
        raise DLMServerError(f"Server error: {response.status}")
    else:
        raise DLMAPIError(f"API error: {response.status}")

def parse_cache_control(header: str) -> int:
    if not header:
        return 300
    parts = header.split(',')
    for part in parts:
        if 'max-age' in part:
            try:
                return int(part.split('=')[1].strip())
            except (IndexError, ValueError):
                pass
    return 300
