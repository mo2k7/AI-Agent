"""General-purpose device-aware tool routing.

Routes tool calls to either the connected mobile device (via WebSocket
reverse-RPC) or the local Mac backend executor, based on the device's
declared tool capabilities.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Mapping

logger = logging.getLogger(__name__)


class DeviceToolRouter:
    """Intercepts every tool call and routes to device or local executor.

    Routing logic:
      1. macOS / macCatalyst clients → always execute locally.
      2. iOS / iPadOS clients → check ``supported_tools`` from device
         registration.  If the tool is listed, proxy to the device.
         Otherwise fall back to local execution.
    """

    # Platforms that always execute locally (no proxying needed).
    _LOCAL_PLATFORMS = frozenset({"macos", "maccatalyst", ""})

    def __init__(
        self,
        *,
        device_registry: dict[str, dict[str, Any]],
        pending_proxies: dict[str, tuple[str, asyncio.Future[dict[str, Any]]]],
        local_executor: Any,
        send_lifecycle_event: Any,  # async callable(client, request_id, domain, action, payload)
        proxy_timeout_seconds: float = 30.0,
    ) -> None:
        self.device_registry = device_registry
        self.pending_proxies = pending_proxies
        self.local_executor = local_executor
        self._send_lifecycle_event = send_lifecycle_event
        self._proxy_timeout = proxy_timeout_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_proxy(self, client_address: str, tool_name: str) -> bool:
        """Return True if *tool_name* should be proxied to the device."""
        device = self.device_registry.get(client_address)
        if not isinstance(device, dict):
            return False
        platform = str(device.get("platform", "")).strip().lower()
        if platform in self._LOCAL_PLATFORMS:
            return False
        supported = device.get("supported_tools", [])
        if not isinstance(supported, (list, set, frozenset)):
            return False
        return tool_name in set(supported)

    async def execute(
        self,
        client: Any,
        request_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool — either proxied to device or locally."""
        if self.should_proxy(client.address, tool_name):
            logger.info(
                "Proxying tool '%s' to device %s for request %s",
                tool_name,
                client.address,
                request_id,
            )
            return await self._proxy_to_device(
                client, request_id, tool_name, dict(arguments)
            )

        # Local execution on Mac backend
        return await asyncio.to_thread(
            self.local_executor.execute, tool_name, arguments,
        )

    def resolve_proxy(self, proxy_key: str, result: dict[str, Any]) -> bool:
        """Resolve a pending proxy future.  Returns True if resolved."""
        pending = self.pending_proxies.pop(proxy_key, None)
        if pending is None:
            logger.warning("No pending proxy for key: %s", proxy_key)
            return False
        _addr, future = pending
        if future.done():
            logger.warning("Proxy future already done for key: %s", proxy_key)
            return False
        future.set_result(result)
        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _proxy_to_device(
        self,
        client: Any,
        request_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        proxy_key = f"{request_id}:{tool_name}:{time.monotonic_ns()}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.pending_proxies[proxy_key] = (client.address, future)

        try:
            await self._send_lifecycle_event(
                client,
                request_id,
                "device",
                "tool_execute_request",
                {
                    "proxy_key": proxy_key,
                    "tool_name": tool_name,
                    "arguments": arguments,
                },
            )
        except Exception as exc:
            self.pending_proxies.pop(proxy_key, None)
            logger.error("Failed to send proxy request: %s", exc)
            return self._error_result(tool_name, f"Failed to send to device: {exc}")

        try:
            result = await asyncio.wait_for(future, timeout=self._proxy_timeout)
            logger.info(
                "Proxy result for '%s' request %s: ok=%s",
                tool_name,
                request_id,
                result.get("ok"),
            )
            return result
        except asyncio.TimeoutError:
            self.pending_proxies.pop(proxy_key, None)
            logger.warning(
                "Proxy timeout for '%s' request %s after %.1fs",
                tool_name,
                request_id,
                self._proxy_timeout,
            )
            return self._error_result(
                tool_name,
                f"Device tool execution timed out after {self._proxy_timeout:.0f}s",
            )
        except asyncio.CancelledError:
            self.pending_proxies.pop(proxy_key, None)
            return self._error_result(tool_name, "Request cancelled")

    @staticmethod
    def _error_result(tool_name: str, error_message: str) -> dict[str, Any]:
        return {
            "tool": tool_name,
            "ok": False,
            "timestamp": time.time(),
            "started_at": time.time(),
            "finished_at": time.time(),
            "latency_ms": 0,
            "output": {"error": error_message, "status": "failed"},
        }
