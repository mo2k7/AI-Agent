"""Robots.txt compliance cache for browse_web.

Extracted from ``agent_host.tools.browse_web`` for modularity.

Note: ``_fetch_robots_txt`` calls the module-level ``_fetch_url`` helper in
browse_web via a lazy import to avoid circular dependencies.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any
from urllib.parse import urlparse

# Default constants (mirrored from browse_web module to avoid import cycle).
_ROBOTS_TXT_CACHE_TTL_SECONDS = 300.0
_ROBOTS_TXT_MAX_CACHED_DOMAINS = 500


class RobotsTxtCache:
    """Thread-safe cache and check robots.txt rules for domains.

    Memory-bounded: evicts expired entries on access, and enforces a hard
    cap of ``max_domains`` by removing the oldest entries when exceeded.
    """

    def __init__(
        self,
        ttl_seconds: float = _ROBOTS_TXT_CACHE_TTL_SECONDS,
        max_domains: int = _ROBOTS_TXT_MAX_CACHED_DOMAINS,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_domains = max_domains
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def is_allowed(
        self,
        url: str,
        scheme: str,
        hostname: str,
    ) -> tuple[bool, str]:
        """Check robots.txt for the given URL.

        Returns (allowed, info_message).
        Uses a cached robots.txt if available and fresh.
        Thread-safe: lock protects cache access but is released during
        the blocking network fetch to avoid stalling parallel threads.
        """
        cache_key = f"{scheme}://{hostname}"
        rules = None
        need_fetch = False

        # Check cache under lock.
        with self._lock:
            now = time.monotonic()
            cached = self._cache.get(cache_key)
            if cached and now - cached["fetched_at"] < self._ttl_seconds:
                rules = cached["rules"]
            else:
                need_fetch = True

        # Fetch outside the lock (I/O-bound).
        if need_fetch:
            fetched_rules = self._fetch_robots_txt(scheme, hostname)
            with self._lock:
                # Double-check: another thread may have fetched while we were
                # doing I/O — use theirs if it's fresher.
                now = time.monotonic()
                cached = self._cache.get(cache_key)
                if cached and now - cached["fetched_at"] < self._ttl_seconds:
                    rules = cached["rules"]
                else:
                    self._cache[cache_key] = {
                        "rules": fetched_rules,
                        "fetched_at": now,
                    }
                    rules = fetched_rules
                    # Evict expired + oldest if over cap.
                    self._evict_if_over_cap(now)

        if rules is None:
            # Fail closed when robots.txt cannot be confirmed.
            return False, (
                f"Could not confirm robots.txt policy at {cache_key}/robots.txt. "
                "Request blocked to avoid bypassing site crawl policy."
            )

        path = urlparse(url).path or "/"
        if self._path_is_disallowed(path, rules):
            return False, (
                f"Access to '{path}' is disallowed by {cache_key}/robots.txt. "
                "The site owner has requested that automated agents not access "
                "this path. Respecting this restriction."
            )

        return True, "robots.txt check passed."

    def _fetch_robots_txt(
        self,
        scheme: str,
        hostname: str,
    ) -> list[dict[str, str]] | None:
        """Fetch and parse robots.txt. Returns list of rules or None on failure."""
        # Lazy import to avoid circular dependency with browse_web module.
        from agent_host.adapters.tools.browse_web.handler import _fetch_url

        robots_url = f"{scheme}://{hostname}/robots.txt"
        fetch_result = _fetch_url(
            robots_url,
            timeout_seconds=5,
            max_redirects=2,
            follow_redirects=True,
            custom_headers={"accept": "text/plain"},
            verify_ssl=True,
        )
        if not fetch_result.get("ok"):
            return None

        body = str(fetch_result.get("_raw_body", ""))
        if not body:
            return None
        body = body[:64_000]
        return self._parse_robots_rules(body)

    def _parse_robots_rules(self, body: str) -> list[dict[str, str]]:
        """Parse robots.txt into a list of allow/disallow rules for our user-agent.

        Supports both ``Allow:`` and ``Disallow:`` directives.  When checking
        a path, the longest matching rule wins (standard robots.txt precedence).
        """
        rules: list[dict[str, str]] = []
        applies_to_us = False
        for line in body.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if line.lower().startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip().lower()
                applies_to_us = agent in {"*", "agentbrowser"}
            elif applies_to_us and line.lower().startswith("disallow:"):
                path = line.split(":", 1)[1].strip()
                if path:
                    rules.append({"disallow": path})
            elif applies_to_us and line.lower().startswith("allow:"):
                path = line.split(":", 1)[1].strip()
                if path:
                    rules.append({"allow": path})
        return rules

    def _path_is_disallowed(
        self,
        path: str,
        rules: list[dict[str, str]],
    ) -> bool:
        """Check if a path is disallowed using longest-match-wins precedence.

        Both ``Allow`` and ``Disallow`` rules are considered.  The rule with
        the longest matching prefix determines the outcome.  If two rules
        have the same length, ``Allow`` wins (more permissive by convention).
        """
        best_match_len = -1
        best_is_disallow = False

        for rule in rules:
            directive = "disallow" if "disallow" in rule else "allow"
            pattern = rule.get(directive, "")
            if not pattern:
                continue

            # Check match (handles wildcards and exact prefix).
            matched = False
            if "*" in pattern:
                regex = re.escape(pattern).replace(r"\*", ".*")
                if re.match(regex, path):
                    matched = True
            elif pattern == "/":
                matched = True
            elif path.startswith(pattern):
                matched = True

            if matched and len(pattern) > best_match_len:
                best_match_len = len(pattern)
                best_is_disallow = (directive == "disallow")
            elif matched and len(pattern) == best_match_len:
                # Same length — Allow wins.
                if directive == "allow":
                    best_is_disallow = False

        return best_is_disallow and best_match_len >= 0

    def _evict_if_over_cap(self, now: float) -> None:
        """Evict expired entries first, then oldest by fetch time if still over cap.

        Must be called while holding ``self._lock``.
        """
        # Pass 1: remove expired entries.
        expired = [
            key for key, entry in self._cache.items()
            if now - entry["fetched_at"] >= self._ttl_seconds
        ]
        for key in expired:
            del self._cache[key]
        # Pass 2: if still over cap, remove oldest.
        if len(self._cache) > self._max_domains:
            by_age = sorted(self._cache.items(), key=lambda kv: kv[1]["fetched_at"])
            excess = len(self._cache) - self._max_domains
            for key, _ in by_age[:excess]:
                del self._cache[key]
