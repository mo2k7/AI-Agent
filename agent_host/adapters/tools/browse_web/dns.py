"""DNS resolution helpers for browse_web.

Contains the DNS cache, DNS-over-HTTPS resolver, getaddrinfo fallback logic,
and aiodns batch resolution helper.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import ipaddress
import socket
import threading
import time
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DNS_CACHE_TTL_SECONDS = 30.0
_DNS_CACHE_MAX_ENTRIES = 200

_DOH_PROVIDERS: list[dict[str, str]] = [
    {
        "name": "cloudflare",
        "url": "https://1.1.1.1/dns-query",
        "accept": "application/dns-json",
    },
    {
        "name": "google",
        "url": "https://dns.google/resolve",
        "accept": "application/dns-json",
    },
]
_DOH_TIMEOUT_SECONDS = 4.0

# httpx for DoH queries (graceful fallback).
try:
    import httpx as _httpx  # type: ignore[import-untyped]
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

# aiodns for async DNS pre-resolution in batch operations.
try:
    import aiodns  # type: ignore[import-untyped]
    _AIODNS_AVAILABLE = True
except ImportError:
    _AIODNS_AVAILABLE = False


# ---------------------------------------------------------------------------
# DNS Cache
# ---------------------------------------------------------------------------

class _DNSCache:
    """Thread-safe DNS resolution cache with TTL.

    Caches validated DNS resolution results to avoid redundant lookups
    within a short window.  A shared ThreadPoolExecutor is used for all
    DNS resolutions instead of creating one per call.
    """

    def __init__(
        self,
        ttl_seconds: float = _DNS_CACHE_TTL_SECONDS,
        max_entries: int = _DNS_CACHE_MAX_ENTRIES,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._cache: dict[str, tuple[list[str], float]] = {}
        self._lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="dns-resolve",
        )

    def get(self, hostname: str, port: int | None) -> list[str] | None:
        """Return cached IPs or None if miss/expired."""
        key = f"{hostname}:{port or 443}"
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ips, cached_at = entry
            if time.monotonic() - cached_at > self._ttl_seconds:
                self._cache.pop(key, None)
                return None
            return list(ips)

    def put(self, hostname: str, port: int | None, ips: list[str]) -> None:
        """Store validated IPs."""
        key = f"{hostname}:{port or 443}"
        with self._lock:
            self._cache[key] = (list(ips), time.monotonic())
            # Evict oldest if over cap.
            if len(self._cache) > self._max_entries:
                oldest_key = min(
                    self._cache, key=lambda k: self._cache[k][1],
                )
                self._cache.pop(oldest_key, None)

    @property
    def executor(self) -> concurrent.futures.ThreadPoolExecutor:
        """Shared executor for DNS resolution."""
        return self._executor


_dns_cache = _DNSCache()


# ---------------------------------------------------------------------------
# DNS-over-HTTPS (DoH) privacy resolver
# ---------------------------------------------------------------------------

class _DoHResolver:
    """Thread-safe DNS-over-HTTPS resolver using httpx.

    Queries Cloudflare and Google DoH JSON APIs for encrypted DNS resolution.
    Returns (list_of_ips, ttl_seconds) or None on failure.
    Falls back transparently — callers should try socket.getaddrinfo if this returns None.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client: Any = None  # Lazy-initialized httpx.Client

    def _get_client(self) -> Any:
        if self._client is None:
            with self._lock:
                if self._client is None and _HTTPX_AVAILABLE:
                    self._client = _httpx.Client(
                        timeout=_DOH_TIMEOUT_SECONDS,
                        follow_redirects=False,
                        http2=False,
                    )
        return self._client

    def resolve(self, hostname: str, port: int | None = None) -> list[str] | None:
        """Resolve hostname via DoH, returning list of IPs or None on failure."""
        client = self._get_client()
        if client is None:
            return None

        for provider in _DOH_PROVIDERS:
            try:
                ips = self._query_provider(client, provider, hostname)
                if ips:
                    return ips
            except Exception:
                continue
        return None

    def _query_provider(
        self, client: Any, provider: dict[str, str], hostname: str,
    ) -> list[str] | None:
        """Query a single DoH provider for A and AAAA records."""
        ips: list[str] = []
        for qtype in ("A", "AAAA"):
            try:
                resp = client.get(
                    provider["url"],
                    params={"name": hostname, "type": qtype},
                    headers={"Accept": provider["accept"]},
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if data.get("Status") != 0:  # NOERROR
                    continue
                for answer in data.get("Answer", []):
                    if answer.get("type") in (1, 28):  # A=1, AAAA=28
                        ip_str = answer.get("data", "").strip()
                        if ip_str:
                            ips.append(ip_str)
            except Exception:
                continue
        return ips if ips else None


_doh_resolver = _DoHResolver()


def _getaddrinfo_with_fallback(
    hostname: str, port: int, family: int = socket.AF_UNSPEC,
) -> list[tuple[Any, ...]]:
    """Resolve DNS with AF_UNSPEC -> AF_INET/AF_INET6 fallback for macOS compatibility."""
    try:
        return socket.getaddrinfo(hostname, port, family, socket.SOCK_STREAM)
    except socket.gaierror as e:
        if family != socket.AF_UNSPEC:
            raise
        # Fallback for macOS configs where AF_UNSPEC fails but explicit families work.
        res: list[tuple[Any, ...]] = []
        try:
            res.extend(socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM))
        except socket.gaierror:
            pass
        try:
            res.extend(socket.getaddrinfo(hostname, port, socket.AF_INET6, socket.SOCK_STREAM))
        except socket.gaierror:
            pass
        if not res:
            raise e
        return res


# Monkey-patch Drawbridge's internal DNS resolver to use our fallback logic.
# Drawbridge SSRF-safe HTTP client (graceful fallback).
import sys as _sys
if "/tmp/agent_libs" not in _sys.path:
    _sys.path.insert(0, "/tmp/agent_libs")

try:
    import drawbridge  # type: ignore[import-untyped]  # noqa: F401
    _DRAWBRIDGE_AVAILABLE = True
except ImportError:
    _DRAWBRIDGE_AVAILABLE = False

if _DRAWBRIDGE_AVAILABLE:
    import drawbridge._validator as _db_validator  # type: ignore

    def _patched_sync_getaddrinfo(hostname: str, port: int) -> list[tuple[Any, ...]]:
        """Drawbridge DNS resolver patched with DoH + AF_UNSPEC fallback."""
        # Try DoH first for privacy.
        doh_ips = _doh_resolver.resolve(hostname, port)
        if doh_ips:
            # Convert DoH results to getaddrinfo-compatible tuples.
            results: list[tuple[Any, ...]] = []
            for ip_str in doh_ips:
                try:
                    addr = ipaddress.ip_address(ip_str)
                    if isinstance(addr, ipaddress.IPv4Address):
                        results.append((
                            socket.AF_INET, socket.SOCK_STREAM, 6, "",
                            (ip_str, port),
                        ))
                    else:
                        results.append((
                            socket.AF_INET6, socket.SOCK_STREAM, 6, "",
                            (ip_str, port, 0, 0),
                        ))
                except ValueError:
                    continue
            if results:
                return results

        # Fallback to socket with AF_UNSPEC fix.
        return _getaddrinfo_with_fallback(hostname, port)

    _db_validator._sync_getaddrinfo = _patched_sync_getaddrinfo  # type: ignore


# ---------------------------------------------------------------------------
# aiodns batch pre-resolution helper
# ---------------------------------------------------------------------------

def _aiodns_batch_resolve(hostnames: list[str]) -> dict[str, list[str]]:
    """Pre-resolve a list of hostnames concurrently using aiodns.

    Returns a mapping of hostname -> list of IPs.
    Failures are silently skipped (callers fall back to synchronous resolution).
    """
    if not _AIODNS_AVAILABLE or not hostnames:
        return {}

    results: dict[str, list[str]] = {}

    async def _resolve_all() -> None:
        resolver = aiodns.DNSResolver()
        tasks = {}
        for hostname in set(hostnames):
            # Query A and AAAA records concurrently.
            tasks[hostname] = asyncio.gather(
                _safe_aiodns_query(resolver, hostname, "A"),
                _safe_aiodns_query(resolver, hostname, "AAAA"),
                return_exceptions=True,
            )

        for hostname, task in tasks.items():
            try:
                a_result, aaaa_result = await task
                ips: list[str] = []
                if isinstance(a_result, list):
                    ips.extend(r.host for r in a_result if hasattr(r, "host"))
                if isinstance(aaaa_result, list):
                    ips.extend(r.host for r in aaaa_result if hasattr(r, "host"))
                if ips:
                    results[hostname] = ips
            except Exception:
                continue

    async def _safe_aiodns_query(resolver: Any, hostname: str, qtype: str) -> Any:
        try:
            return await resolver.query(hostname, qtype)
        except Exception:
            return []

    try:
        asyncio.run(_resolve_all())
    except Exception:
        pass

    return results
