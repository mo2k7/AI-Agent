"""Memory IPC handler use cases.

Extracted from ``agent_host/main.py`` to reduce the monolith's size.
All closure dependencies are injected via the constructor.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable

from agent_host.core.services.prompt_service import (
    _format_exception_message,
    _normalize_session_id,
)
from agent_host.contracts.types.ipc_messages import ErrorMessage, IncomingRequest, ResultMessage
from agent_host.contracts.ports.client_connection import ClientConnectionPort as ClientConnection
from agent_host.contracts.types.errors import MemoryStoreError

logger = logging.getLogger(__name__)


class MemoryUseCases:
    """Encapsulates all memory-related IPC handlers."""

    def __init__(
        self,
        *,
        memory_manager: Any,
        ipc_bridge: Any,
        run_blocking: Callable[..., Awaitable[Any]],
        db_timeout_seconds: float,
        broadcast_session_refresh: Callable[..., Awaitable[None]],
        event_bus: Any | None = None,
    ) -> None:
        self._memory = memory_manager
        self._ipc = ipc_bridge
        self._run_blocking = run_blocking
        self._db_timeout = db_timeout_seconds
        self._broadcast_session_refresh = broadcast_session_refresh
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # memory.list
    # ------------------------------------------------------------------

    async def handle_list(self, request: IncomingRequest, client: ClientConnection) -> None:
        """List semantic memories for a session."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        if not session_id:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id").to_bytes()
            )
            return
        session_exists = await self._run_blocking(
            label="db.get_session",
            timeout_seconds=self._db_timeout,
            func=self._memory.get_session,
            args=(session_id,),
            request_id=request.id,
            method=request.method,
        )
        if session_exists is None:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    f"Unknown session_id: {session_id}",
                ).to_bytes()
            )
            return
        limit_raw = request.params.get("limit", 100)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 100
        try:
            memories = await self._run_blocking(
                label="db.list_memories",
                timeout_seconds=self._db_timeout,
                func=self._memory.list_memories,
                args=(session_id,),
                kwargs={"limit": max(1, min(limit, 500))},
                request_id=request.id,
                method=request.method,
            )
        except ValueError as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    _format_exception_message(exc, fallback="Unknown session"),
                ).to_bytes()
            )
            return
        except MemoryStoreError as exc:
            await client.send(
                ErrorMessage.internal_error(
                    request.id,
                    _format_exception_message(exc, fallback="Session data corrupted"),
                ).to_bytes()
            )
            return
        await client.send(ResultMessage.create(request.id, json.dumps(memories)).to_bytes())

    # ------------------------------------------------------------------
    # memory.delete
    # ------------------------------------------------------------------

    async def handle_delete(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Delete a semantic memory entry."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        memory_id = request.params.get("memory_id")
        if not session_id or not isinstance(memory_id, str):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or memory_id").to_bytes()
            )
            return
        session_exists = await self._run_blocking(
            label="db.get_session",
            timeout_seconds=self._db_timeout,
            func=self._memory.get_session,
            args=(session_id,),
            request_id=request.id,
            method=request.method,
        )
        if session_exists is None:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    f"Unknown session_id: {session_id}",
                ).to_bytes()
            )
            return
        normalized_memory_id = memory_id.strip()
        try:
            deleted = await self._run_blocking(
                label="db.delete_memory",
                timeout_seconds=self._db_timeout,
                func=self._memory.delete_memory,
                args=(session_id, normalized_memory_id),
                request_id=request.id,
                method=request.method,
            )
        except ValueError as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    _format_exception_message(exc, fallback="Unknown session"),
                ).to_bytes()
            )
            return
        await client.send(
            ResultMessage.create(
                request.id,
                json.dumps({"deleted": deleted, "memory_id": normalized_memory_id}),
            ).to_bytes()
        )
        if deleted:
            await self._ipc.broadcast_memory_event(
                action="deleted",
                session_id=session_id,
                memory_id=normalized_memory_id,
            )
            await self._broadcast_session_refresh(
                session_id=session_id,
                request_id=request.id,
                method=request.method,
            )
            if self._event_bus:
                from agent_host.contracts.types.events import MemoryDeleted
                self._event_bus.publish(MemoryDeleted(
                    event_type="memory.deleted",
                    source="memory_use_case",
                    payload={
                        "session_id": session_id,
                        "memory_id": normalized_memory_id,
                    },
                ))
