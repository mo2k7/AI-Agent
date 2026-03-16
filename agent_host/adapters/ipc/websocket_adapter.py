"""Adapter wrapping IPCServer to satisfy the IPCPort protocol.

Thin delegation layer — all calls forwarded to the underlying server.
Defensive error boundaries ensure that only transport exceptions (ConnectionError,
OSError) pass through; everything else is wrapped in AdapterError.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from agent_host.contracts.types.errors import AdapterError

logger = logging.getLogger(__name__)

_PASSTHROUGH = (ConnectionError, OSError)


class WebSocketAdapter:
    """Wraps ``IPCServer`` to satisfy ``IPCPort`` protocol."""

    def __init__(self, server: Any) -> None:
        self._server = server

    def register_handler(
        self,
        method: str,
        handler: Callable[..., Awaitable[None]],
    ) -> None:
        try:
            self._server.register_handler(method, handler)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("WebSocketAdapter.register_handler failed: %s", exc)
            raise AdapterError(
                f"websocket.register_handler failed: {exc}",
                source="websocket",
                cause=exc,
            ) from exc

    async def broadcast(self, message: bytes) -> None:
        try:
            await self._server.broadcast(message)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("WebSocketAdapter.broadcast failed: %s", exc)
            raise AdapterError(
                f"websocket.broadcast failed: {exc}",
                source="websocket",
                cause=exc,
            ) from exc

    async def start(self) -> None:
        try:
            await self._server.start()
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("WebSocketAdapter.start failed: %s", exc)
            raise AdapterError(
                f"websocket.start failed: {exc}",
                source="websocket",
                cause=exc,
            ) from exc

    async def stop(self) -> None:
        try:
            await self._server.stop()
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("WebSocketAdapter.stop failed: %s", exc)
            raise AdapterError(
                f"websocket.stop failed: {exc}",
                source="websocket",
                cause=exc,
            ) from exc
