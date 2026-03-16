"""Anti-bot/security incident monitor for browse_web.

Extracted from ``agent_host.tools.browse_web`` for modularity.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)


class BrowseIncidentMonitor:
    """Track anti-bot/security events and activate response mode on spikes."""

    def __init__(
        self,
        threshold: int,
        window_seconds: float,
        cooldown_seconds: float,
        incident_log_path: str,
    ) -> None:
        self._threshold = max(1, int(threshold))
        self._window_seconds = max(30.0, float(window_seconds))
        self._cooldown_seconds = max(30.0, float(cooldown_seconds))
        self._incident_log_path = Path(incident_log_path).expanduser()
        self._events: dict[str, list[float]] = {}
        self._open_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def check_domain(self, domain: str) -> tuple[bool, str]:
        now = time.monotonic()
        with self._lock:
            open_until = self._open_until.get(domain, 0.0)
            if open_until > now:
                remaining = round(open_until - now, 1)
                return False, (
                    f"Incident response active for '{domain}' due to repeated anti-bot/security "
                    f"events. Cooldown remaining: ~{remaining}s."
                )
            return True, ""

    def record_event(self, domain: str, *, event_type: str, details: Mapping[str, Any]) -> None:
        now = time.monotonic()
        with self._lock:
            samples = self._events.setdefault(domain, [])
            cutoff = now - self._window_seconds
            samples[:] = [ts for ts in samples if ts >= cutoff]
            samples.append(now)
            if len(samples) >= self._threshold:
                self._open_until[domain] = now + self._cooldown_seconds
                self._write_incident_event(
                    domain=domain,
                    event_type=event_type,
                    details={
                        **dict(details),
                        "count_in_window": len(samples),
                        "window_seconds": self._window_seconds,
                        "cooldown_seconds": self._cooldown_seconds,
                    },
                )

    def reset(self, domain: str | None = None) -> None:
        with self._lock:
            if domain:
                self._events.pop(domain, None)
                self._open_until.pop(domain, None)
            else:
                self._events.clear()
                self._open_until.clear()

    def _write_incident_event(self, *, domain: str, event_type: str, details: Mapping[str, Any]) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain": domain,
            "event_type": event_type,
            "details": details,
        }
        try:
            self._incident_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._incident_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False))
                f.write("\n")
        except OSError:
            logger.warning("Unable to write browse incident event for domain '%s'.", domain)
