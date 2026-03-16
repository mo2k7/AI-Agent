"""Port interface for an IPC client connection."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ClientConnectionPort(Protocol):
    """Minimal interface for an IPC client connection.

    This protocol captures the subset of ``ipc.server.ClientConnection``
    that the core layer actually uses, so core/ never needs to import the
    concrete server module.
    """

    @property
    def address(self) -> str: ...

    async def send(self, data: bytes) -> None: ...
