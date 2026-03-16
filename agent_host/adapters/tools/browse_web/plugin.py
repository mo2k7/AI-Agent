"""Tool plugin: browse_web.

Fetches and extracts content from web URLs with comprehensive security
hardening (SSRF prevention, DNS rebinding mitigation, robots.txt
compliance, rate limiting, circuit breaking, and content safety analysis).

The 5,400+ lines of core logic remain in ``agent_host.tools.browse_web``.
This plugin owns the five infrastructure instances that the core logic
requires and wires them in via keyword arguments.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

from agent_host.contracts.types.errors import AgentError, ErrorCode
from agent_host.contracts.types.result import Failure, Result, Success

logger = logging.getLogger(__name__)


class BrowseWebPlugin:
    """Self-contained plugin for the ``browse_web`` tool.

    Creates and owns the five infrastructure instances required by the
    browse_web handler:

    - ``DomainRateLimiter``     -- per-domain request throttling
    - ``RobotsTxtCache``        -- cached robots.txt lookups
    - ``DomainCircuitBreaker``  -- circuit breaker per domain
    - ``ResponseCache``         -- LRU response cache with TTL
    - ``BrowseIncidentMonitor`` -- anti-bot challenge spike detector
    """

    def __init__(self) -> None:
        from agent_host.adapters.tools.browse_web.handler import (
            BrowseIncidentMonitor,
            DomainCircuitBreaker,
            DomainRateLimiter,
            ResponseCache,
            RobotsTxtCache,
            _load_browse_compliance_policy,
        )

        self._rate_limiter = DomainRateLimiter()
        self._robots_cache = RobotsTxtCache()
        self._circuit_breaker = DomainCircuitBreaker()

        policy = _load_browse_compliance_policy()
        retention = policy.get("retention", {})
        cache_ttl = float(retention.get("response_cache_ttl_seconds", 120))
        cache_max = int(retention.get("response_cache_max_entries", 64))
        self._response_cache = ResponseCache(
            max_entries=max(8, cache_max),
            ttl_seconds=max(30.0, cache_ttl),
        )

        incident_cfg = policy.get("incident_response", {})
        self._incident_monitor = BrowseIncidentMonitor(
            threshold=int(incident_cfg.get("challenge_spike_threshold", 6)),
            window_seconds=float(incident_cfg.get("window_seconds", 300)),
            cooldown_seconds=float(incident_cfg.get("cooldown_seconds", 600)),
            incident_log_path=str(
                incident_cfg.get(
                    "incident_log_path",
                    Path.home()
                    / "Library"
                    / "Application Support"
                    / "AIAgent"
                    / "security"
                    / "browse_incidents.jsonl",
                )
            ),
        )

    # ------------------------------------------------------------------
    # ToolPlugin protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "browse_web"

    @property
    def description(self) -> str:
        return "Fetch and extract content from web URLs"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Single URL to fetch",
                },
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple URLs to fetch in parallel (max 20)",
                },
                "search_query": {
                    "type": "string",
                    "description": "Search query to run across search engines",
                },
                "search_engines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Engines to use. Default: ['google']. "
                        "Available: 'duckduckgo', 'brave', 'google'."
                    ),
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Per-request timeout (default 15, max 60)",
                },
                "follow_redirects": {
                    "type": "boolean",
                    "description": "Follow HTTP redirects (default true)",
                },
                "max_redirects": {
                    "type": "integer",
                    "description": "Max redirect hops (default 5)",
                },
                "include_raw_html": {
                    "type": "boolean",
                    "description": "Include raw HTML in response (default false)",
                },
                "respect_robots_txt": {
                    "type": "boolean",
                    "description": "Check robots.txt first (default true)",
                },
                "use_cache": {
                    "type": "boolean",
                    "description": "Use response cache (default true)",
                },
                "custom_headers": {
                    "type": "object",
                    "description": "Safe custom headers (limited allowlist)",
                },
                "verify_ssl": {
                    "type": "boolean",
                    "description": "Verify SSL certificates (default true)",
                },
                "compliance_action": {
                    "type": "string",
                    "description": (
                        "Compliance action: purge_cache_url, purge_cache_domain, "
                        "purge_cache_all, delete_subject_data, acknowledge_incident"
                    ),
                },
            },
        }

    def execute(self, arguments: Mapping[str, Any]) -> Result[dict[str, Any]]:
        """Execute the browse_web tool, returning Success or Failure."""
        from agent_host.adapters.tools.browse_web.handler import handle as _browse_handle
        from agent_host.tools.executor import ToolExecutionError

        try:
            output = _browse_handle(
                arguments,
                rate_limiter=self._rate_limiter,
                robots_cache=self._robots_cache,
                circuit_breaker=self._circuit_breaker,
                response_cache=self._response_cache,
                incident_monitor=self._incident_monitor,
            )
            return Success(output)
        except ToolExecutionError as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=str(exc),
                source="browse_web",
                retryable=getattr(exc, "retryable", False),
            ))
        except Exception as exc:
            logger.exception("Unexpected error in browse_web plugin")
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Unexpected error in browse_web: {exc}",
                source="browse_web",
            ))

    def health_check(self) -> Result[bool]:
        """Verify browse_web infrastructure is operational."""
        from agent_host.adapters.tools.browse_web.handler import _get_diagnostics

        try:
            diagnostics = _get_diagnostics(
                rate_limiter=self._rate_limiter,
                robots_cache=self._robots_cache,
                circuit_breaker=self._circuit_breaker,
                response_cache=self._response_cache,
                incident_monitor=self._incident_monitor,
            )
            # If diagnostics can be computed, infrastructure is healthy.
            if isinstance(diagnostics, dict):
                return Success(True)
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message="Diagnostics returned unexpected type",
                source="browse_web",
            ))
        except Exception as exc:
            return Failure(AgentError(
                code=ErrorCode.INTERNAL,
                message=f"Health check failed: {exc}",
                source="browse_web",
            ))
