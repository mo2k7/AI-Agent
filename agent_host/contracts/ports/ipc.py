"""Port interface for IPC (Inter-Process Communication).

Abstracts the WebSocket-based IPC server so the core domain
can communicate with frontends without depending on a specific transport.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable, Protocol, runtime_checkable


@runtime_checkable
class IPCPort(Protocol):
    """Abstract interface for the IPC server."""

    def register_handler(
        self,
        method: str,
        handler: Callable[..., Awaitable[None]],
    ) -> None:
        """Register an async handler for an IPC method."""
        ...

    async def broadcast(self, message: bytes) -> None:
        """Broadcast a message to all connected clients."""
        ...

    async def start(self) -> None:
        """Start the IPC server."""
        ...

    async def stop(self) -> None:
        """Stop the IPC server."""
        ...
