"""Per-domain circuit breaker for browse_web.

Extracted from ``agent_host.tools.browse_web`` for modularity.
"""

from __future__ import annotations

import threading
import time
from typing import Any

# Default constants (mirrored from browse_web module to avoid import cycle).
_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
_CIRCUIT_BREAKER_RECOVERY_SECONDS = 60.0


class DomainCircuitBreaker:
    """Lightweight per-domain circuit breaker (CLOSED → OPEN → HALF-OPEN).

    Tracks consecutive failures per domain. After ``failure_threshold``
    consecutive failures, the circuit *opens* and rejects requests for
    ``recovery_seconds``.  After the recovery window, one probe request is
    allowed (HALF-OPEN).  If the probe succeeds the circuit closes; if it
    fails the circuit re-opens.

    Thread-safe and memory-bounded (evicts oldest domains when over cap).
    """

    _MAX_TRACKED_DOMAINS = 500

    def __init__(
        self,
        failure_threshold: int = _CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_seconds: float = _CIRCUIT_BREAKER_RECOVERY_SECONDS,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        # domain → {"failures": int, "opened_at": float | None, "state": str}
        self._domains: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def allow_request(self, domain: str) -> tuple[bool, str]:
        """Return (allowed, reason).  If OPEN and past recovery window, transitions to HALF-OPEN."""
        with self._lock:
            entry = self._domains.get(domain)
            if entry is None:
                return True, ""

            state = entry["state"]
            if state == "closed":
                return True, ""
            elif state == "open":
                elapsed = time.monotonic() - (entry.get("opened_at") or 0.0)
                if elapsed >= self._recovery_seconds:
                    entry["state"] = "half-open"
                    return True, ""
                remaining = round(self._recovery_seconds - elapsed, 1)
                return False, (
                    f"Circuit breaker OPEN for domain '{domain}': "
                    f"{entry['failures']} consecutive failures. "
                    f"Retry in ~{remaining}s or try an alternative source."
                )
            else:  # half-open — allow the probe request
                return True, ""

    def record_success(self, domain: str) -> None:
        """Record a successful request — resets the circuit to CLOSED."""
        with self._lock:
            self._domains.pop(domain, None)

    def record_failure(self, domain: str) -> None:
        """Record a failed request.  Opens the circuit after reaching threshold."""
        with self._lock:
            entry = self._domains.setdefault(
                domain, {"failures": 0, "opened_at": None, "state": "closed"}
            )
            entry["failures"] += 1
            if entry["failures"] >= self._failure_threshold:
                entry["state"] = "open"
                entry["opened_at"] = time.monotonic()
            # Evict oldest if over cap.
            if len(self._domains) > self._MAX_TRACKED_DOMAINS:
                oldest = min(
                    self._domains,
                    key=lambda d: self._domains[d].get("opened_at") or 0.0,
                )
                if oldest != domain:
                    del self._domains[oldest]
