"""In-memory LRU response cache with TTL for browse_web.

Extracted from ``agent_host.tools.browse_web`` for modularity.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Any

# Default constants (mirrored from browse_web module to avoid import cycle).
_RESPONSE_CACHE_TTL_SECONDS = 120.0
_RESPONSE_CACHE_MAX_ENTRIES = 64


class ResponseCache:
    """Thread-safe LRU cache with TTL for fetched page content."""

    def __init__(
        self,
        max_entries: int = _RESPONSE_CACHE_MAX_ENTRIES,
        ttl_seconds: float = _RESPONSE_CACHE_TTL_SECONDS,
    ) -> None:
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def _cache_key(self, url: str) -> str:
        return hashlib.sha256(url.encode("utf-8", errors="replace")).hexdigest()[:32]

    def get(self, url: str) -> dict[str, Any] | None:
        with self._lock:
            key = self._cache_key(url)
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.monotonic() - entry["cached_at"] > self._ttl_seconds:
                self._cache.pop(key, None)
                return None
            # Move to end (most recently used).
            self._cache.move_to_end(key)
            result = entry["data"].copy()
            result["from_cache"] = True
            result["cache_age_seconds"] = round(
                time.monotonic() - entry["cached_at"], 1
            )
            return result

    def put(self, url: str, data: dict[str, Any]) -> None:
        with self._lock:
            key = self._cache_key(url)
            while len(self._cache) >= self._max_entries and key not in self._cache:
                self._cache.popitem(last=False)
            self._cache[key] = {
                "data": data.copy(),
                "cached_at": time.monotonic(),
            }

    def invalidate(self, url: str) -> bool:
        with self._lock:
            key = self._cache_key(url)
            return self._cache.pop(key, None) is not None
