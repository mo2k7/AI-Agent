"""Per-domain sliding-window rate limiter for browse_web.

Extracted from ``agent_host.tools.browse_web`` for modularity.
"""

from __future__ import annotations

import threading
import time
from typing import Any

# Default constants (mirrored from browse_web module to avoid import cycle).
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_RATE_LIMIT_MAX_PER_DOMAIN = 30
_RATE_LIMIT_MAX_TRACKED_DOMAINS = 500


class DomainRateLimiter:
    """Thread-safe sliding-window rate limiter per domain.

    Memory-bounded: evicts the least-recently-active domains when the
    tracked domain count exceeds ``max_tracked_domains``.
    """

    def __init__(
        self,
        max_requests: int = _RATE_LIMIT_MAX_PER_DOMAIN,
        window_seconds: float = _RATE_LIMIT_WINDOW_SECONDS,
        max_tracked_domains: int = _RATE_LIMIT_MAX_TRACKED_DOMAINS,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._max_tracked_domains = max_tracked_domains
        self._domain_timestamps: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _evict_stale_domains(self, now: float) -> None:
        """Remove domains with no recent activity, then evict oldest if still over cap."""
        cutoff = now - self._window_seconds
        # First pass: remove entirely expired domains.
        stale = [d for d, ts in self._domain_timestamps.items() if not any(t > cutoff for t in ts)]
        for d in stale:
            del self._domain_timestamps[d]
        # Second pass: if still over cap, evict domains with oldest last-activity.
        if len(self._domain_timestamps) > self._max_tracked_domains:
            by_last_activity = sorted(
                self._domain_timestamps.items(),
                key=lambda pair: max(pair[1]) if pair[1] else 0.0,
            )
            excess = len(self._domain_timestamps) - self._max_tracked_domains
            for domain, _ in by_last_activity[:excess]:
                del self._domain_timestamps[domain]

    def check_and_record(self, domain: str) -> tuple[bool, str]:
        """Return (allowed, reason). Records the request if allowed."""
        with self._lock:
            now = time.monotonic()
            timestamps = self._domain_timestamps.setdefault(domain, [])

            # Prune old entries outside the window.
            cutoff = now - self._window_seconds
            self._domain_timestamps[domain] = [
                ts for ts in timestamps if ts > cutoff
            ]
            timestamps = self._domain_timestamps[domain]

            if len(timestamps) >= self._max_requests:
                wait_seconds = round(timestamps[0] - cutoff + 0.5, 1)
                return False, (
                    f"Rate limit reached for domain '{domain}': "
                    f"{self._max_requests} requests in {self._window_seconds}s window. "
                    f"Try again in ~{wait_seconds}s."
                )

            timestamps.append(now)

            # Evict stale domains if we've grown too large.
            if len(self._domain_timestamps) > self._max_tracked_domains:
                self._evict_stale_domains(now)

            return True, ""

    def check_only(self, domain: str) -> tuple[bool, str]:
        """Check rate limit without recording the request."""
        with self._lock:
            now = time.monotonic()
            cutoff = now - self._window_seconds
            timestamps = self._domain_timestamps.get(domain, [])
            recent = [ts for ts in timestamps if ts > cutoff]
            if len(recent) >= self._max_requests:
                wait_seconds = round(recent[0] - cutoff + 0.5, 1)
                return False, (
                    f"Rate limit reached for domain '{domain}': "
                    f"{self._max_requests} requests in {self._window_seconds}s window. "
                    f"Try again in ~{wait_seconds}s."
                )
            return True, ""

    def record(self, domain: str) -> None:
        """Record a request against the rate limit after a successful fetch."""
        with self._lock:
            now = time.monotonic()
            timestamps = self._domain_timestamps.setdefault(domain, [])
            cutoff = now - self._window_seconds
            self._domain_timestamps[domain] = [
                ts for ts in timestamps if ts > cutoff
            ]
            self._domain_timestamps[domain].append(now)
            if len(self._domain_timestamps) > self._max_tracked_domains:
                self._evict_stale_domains(now)

    def get_domain_usage(self, domain: str) -> dict[str, Any]:
        """Return current usage stats for a domain."""
        with self._lock:
            now = time.monotonic()
            cutoff = now - self._window_seconds
            timestamps = self._domain_timestamps.get(domain, [])
            recent = [ts for ts in timestamps if ts > cutoff]
            return {
                "domain": domain,
                "requests_in_window": len(recent),
                "max_allowed": self._max_requests,
                "window_seconds": self._window_seconds,
            }
