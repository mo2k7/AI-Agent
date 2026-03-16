"""URL security validation for browse_web.

Contains SSRF prevention, DNS rebinding mitigation, URL structure validation,
IP reservation checks, and redirect target validation.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urlparse

from agent_host.tools.executor import ToolExecutionError
from agent_host.adapters.tools.browse_web.dns import (
    _dns_cache,
    _doh_resolver,
    _getaddrinfo_with_fallback,
)

# ---------------------------------------------------------------------------
# Constants (duplicated from browse_web.py for standalone use)
# ---------------------------------------------------------------------------

_ALLOWED_SCHEMES = frozenset({"http", "https"})

_DANGEROUS_SCHEMES = frozenset({
    "file", "ftp", "gopher", "dict", "ldap", "ldaps",
    "sftp", "telnet", "tftp", "data", "javascript",
})

_MAX_URL_LENGTH = 2048

# Cloud metadata endpoints that SSRF attacks commonly target.
_CLOUD_METADATA_IPS = frozenset({
    "169.254.169.254",   # AWS / GCP / Azure IMDS
    "100.100.100.200",   # Alibaba Cloud
    "fd00:ec2::254",     # AWS IMDSv2 IPv6
})

_DNS_RESOLUTION_TIMEOUT_SECONDS = 5.0


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class URLSecurityViolation(ToolExecutionError):
    """Raised when a URL fails security validation."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_url_structure(url: str) -> tuple[str, str, str, int | None]:
    """Parse and structurally validate a URL.

    Returns (scheme, hostname, path, port) or raises URLSecurityViolation.
    """
    if not url or not isinstance(url, str):
        raise URLSecurityViolation("URL must be a non-empty string.")
    url = url.strip()
    if len(url) > _MAX_URL_LENGTH:
        raise URLSecurityViolation(
            f"URL exceeds maximum length of {_MAX_URL_LENGTH} characters."
        )

    # Reject URLs with embedded credentials (user:pass@host).
    if "@" in url.split("//", 1)[-1].split("/", 1)[0]:
        raise URLSecurityViolation(
            "URLs with embedded credentials are not permitted."
        )

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise URLSecurityViolation(f"Malformed URL: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if not scheme:
        raise URLSecurityViolation("URL is missing a scheme (e.g., https://).")
    if scheme in _DANGEROUS_SCHEMES:
        raise URLSecurityViolation(
            f"Scheme '{scheme}' is blocked for security reasons. "
            f"Only {', '.join(sorted(_ALLOWED_SCHEMES))} are permitted."
        )
    if scheme not in _ALLOWED_SCHEMES:
        raise URLSecurityViolation(
            f"Unsupported scheme '{scheme}'. "
            f"Allowed: {', '.join(sorted(_ALLOWED_SCHEMES))}."
        )

    hostname = (parsed.hostname or "").lower().strip(".")
    if not hostname:
        raise URLSecurityViolation("URL is missing a hostname.")
    if len(hostname) > 253:
        raise URLSecurityViolation("Hostname exceeds maximum length.")

    # Block numeric-only hostnames that could be octal/hex IP tricks.
    if re.match(r"^[0-9]+$", hostname):
        raise URLSecurityViolation(
            "Bare numeric hostnames are not permitted (possible IP obfuscation)."
        )

    # Block hostnames with null bytes or control characters.
    if any(ord(c) < 32 or ord(c) == 127 for c in hostname):
        raise URLSecurityViolation(
            "Hostname contains invalid control characters."
        )

    port = parsed.port
    if port is not None and (port < 1 or port > 65535):
        raise URLSecurityViolation(f"Port {port} is out of valid range.")

    # Block common internal-only ports.
    _internal_ports = {6379, 11211, 27017, 3306, 5432, 9200, 2379, 8500}
    if port in _internal_ports:
        raise URLSecurityViolation(
            f"Port {port} is commonly used by internal services and is blocked."
        )

    return scheme, hostname, parsed.path or "/", port


def _is_private_or_reserved_ip(ip_str: str) -> bool:
    """Check if an IP address is private, reserved, loopback, or link-local."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # If we can't parse it, treat it as unsafe.

    if isinstance(addr, ipaddress.IPv4Address):
        return (
            addr.is_private
            or addr.is_reserved
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_unspecified
            or str(addr).startswith("0.")
        )
    elif isinstance(addr, ipaddress.IPv6Address):
        # Also check IPv4-mapped IPv6 addresses (::ffff:127.0.0.1).
        if addr.ipv4_mapped:
            return _is_private_or_reserved_ip(str(addr.ipv4_mapped))
        return (
            addr.is_private
            or addr.is_reserved
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_unspecified
        )
    return True


def _is_cloud_metadata_ip(ip_str: str) -> bool:
    """Check if an IP matches known cloud metadata service endpoints."""
    return ip_str in _CLOUD_METADATA_IPS


def _resolve_and_validate_hostname(
    hostname: str,
    port: int | None = None,
) -> list[str]:
    """Resolve a hostname to IP addresses and validate every result.

    This is the core SSRF and DNS rebinding defense. We resolve the
    hostname ourselves and check every resolved IP before allowing any
    connection. The resolved IPs are returned so the caller can pin
    the connection to them, preventing a second (rebound) resolution.

    Uses a short-lived DNS cache to avoid redundant lookups during
    batch operations. The shared ThreadPoolExecutor avoids creating
    one per call.

    Raises URLSecurityViolation if any resolved IP is unsafe.
    """
    # Check DNS cache first.
    cached_ips = _dns_cache.get(hostname, port)
    if cached_ips is not None:
        return cached_ips

    try:
        # Step 1: Try DoH (DNS-over-HTTPS) for privacy-respecting resolution.
        doh_ips = _doh_resolver.resolve(hostname, port)
        if doh_ips:
            # Convert DoH results to getaddrinfo-compatible tuples for uniform processing.
            results: list[tuple[Any, ...]] = []
            for ip_str in doh_ips:
                try:
                    addr = ipaddress.ip_address(ip_str)
                    if isinstance(addr, ipaddress.IPv4Address):
                        results.append((
                            socket.AF_INET, socket.SOCK_STREAM, 6, "",
                            (ip_str, port or 443),
                        ))
                    else:
                        results.append((
                            socket.AF_INET6, socket.SOCK_STREAM, 6, "",
                            (ip_str, port or 443, 0, 0),
                        ))
                except ValueError:
                    continue
        else:
            # Step 2: Fallback to socket.getaddrinfo with AF_UNSPEC fix.
            dns_future = _dns_cache.executor.submit(
                _getaddrinfo_with_fallback, hostname, port or 443,
            )
            try:
                results = dns_future.result(timeout=_DNS_RESOLUTION_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                raise URLSecurityViolation(
                    f"DNS resolution timed out for '{hostname}' "
                    f"after {_DNS_RESOLUTION_TIMEOUT_SECONDS}s. "
                    "The DNS server may be slow or unreachable."
                )
    except socket.gaierror as exc:
        raise URLSecurityViolation(
            f"DNS resolution failed for '{hostname}': {exc}. "
            "The domain may not exist or DNS is unreachable."
        ) from exc

    if not results:
        raise URLSecurityViolation(
            f"DNS resolution returned no results for '{hostname}'."
        )

    resolved_ips: list[str] = []
    for family, socktype, proto, canonname, sockaddr in results:
        ip = sockaddr[0]
        if _is_private_or_reserved_ip(ip):
            raise URLSecurityViolation(
                f"Hostname '{hostname}' resolved to private/reserved IP "
                f"'{ip}'. This is blocked to prevent SSRF attacks. "
                "If you need to access internal resources, use a dedicated "
                "internal tool instead."
            )
        if _is_cloud_metadata_ip(ip):
            raise URLSecurityViolation(
                f"Hostname '{hostname}' resolved to cloud metadata IP "
                f"'{ip}'. This is blocked to prevent credential theft via SSRF."
            )
        resolved_ips.append(ip)

    validated = list(dict.fromkeys(resolved_ips))  # Deduplicated, order-preserved.
    # Cache the validated result.
    _dns_cache.put(hostname, port, validated)
    return validated


def _validate_redirect_target(
    redirect_url: str,
    original_hostname: str,
) -> tuple[str, str, list[str], bool]:
    """Validate a redirect URL with the same rigor as the original request.

    Returns (validated_url, hostname, resolved_ips, is_cross_origin).
    """
    scheme, hostname, path, port = _validate_url_structure(redirect_url)
    resolved_ips = _resolve_and_validate_hostname(hostname, port)
    is_cross_origin = hostname != original_hostname
    return redirect_url, hostname, resolved_ips, is_cross_origin
