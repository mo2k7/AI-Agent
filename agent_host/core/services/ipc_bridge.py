"""IPC messaging bridge for request-scoped communication.

Encapsulates the send/broadcast helpers that were previously closure
functions inside ``run_server()``.  The IPCBridge is created once per
server lifecycle and passed to handlers and the prompt orchestrator.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class IPCBridge:
    """Encapsulates IPC message sending, broadcasting, and request tracking."""

    def __init__(
        self,
        *,
        server: Any,  # IPCServer — avoids circular import
        active_tasks: dict[str, asyncio.Task],
        cancelled_requests: set[str],
    ) -> None:
        self._server = server
        self._active_tasks = active_tasks
        self._cancelled = cancelled_requests
        self._lifecycle_seq = itertools.count(1)

    # ------------------------------------------------------------------
    # Connection & request tracking
    # ------------------------------------------------------------------

    @staticmethod
    def client_is_connected(client: Any) -> bool:
        writer = getattr(client, "writer", None)
        if writer is None:
            # Test doubles and alternate transport adapters may omit `writer`.
            return True
        is_closing = getattr(writer, "is_closing", None)
        if not callable(is_closing):
            return True
        try:
            return not bool(is_closing())
        except Exception:
            return False

    def is_request_in_flight(self, request_id: str) -> bool:
        current_task = asyncio.current_task()
        tracked_task = self._active_tasks.get(request_id)
        if current_task is None or tracked_task is None:
            return False
        if tracked_task is not current_task:
            return False
        if tracked_task.done():
            return False
        if request_id in self._cancelled:
            return False
        return True

    # ------------------------------------------------------------------
    # Sending messages to a single client
    # ------------------------------------------------------------------

    async def send_request_message(
        self,
        *,
        client: Any,
        request_id: str,
        payload: bytes,
        require_in_flight: bool,
    ) -> bool:
        if require_in_flight and not self.is_request_in_flight(request_id):
            return False
        if not self.client_is_connected(client):
            return False
        try:
            await client.send(payload)
            return True
        except (BrokenPipeError, ConnectionError, OSError):
            return False
        except RuntimeError:
            logger.warning(
                "RuntimeError while sending to client (transport likely closed)",
                extra={"request_id": request_id},
            )
            return False

    async def send_request_error(
        self,
        client: Any,
        request_id: str,
        code: int,
        message: str,
        *,
        data: dict[str, Any] | None = None,
        require_in_flight: bool = False,
    ) -> None:
        """Send a structured error and terminal status updates for a request."""
        from agent_host.contracts.types.ipc_messages import ErrorMessage, StatusUpdate

        await self.send_request_message(
            client=client,
            request_id=request_id,
            payload=ErrorMessage.create(request_id, code, message, data=data).to_bytes(),
            require_in_flight=require_in_flight,
        )
        await self.send_request_message(
            client=client,
            request_id=request_id,
            payload=StatusUpdate.error(request_id, message).to_bytes(),
            require_in_flight=require_in_flight,
        )
        await self.send_request_message(
            client=client,
            request_id=request_id,
            payload=StatusUpdate.complete(request_id).to_bytes(),
            require_in_flight=require_in_flight,
        )

    # ------------------------------------------------------------------
    # Session payload serialisation
    # ------------------------------------------------------------------

    @staticmethod
    def session_payload(session: object) -> dict[str, object]:
        """Serialize a session record into the canonical IPC payload shape."""
        return {
            "session_id": getattr(session, "session_id"),
            "title": getattr(session, "title"),
            "memory_mode": getattr(getattr(session, "memory_mode"), "value"),
            "created_at": getattr(session, "created_at"),
            "updated_at": getattr(session, "updated_at"),
            "last_activity": getattr(session, "last_activity"),
            "status": getattr(session, "status"),
            "store_version": getattr(session, "store_version", 0),
        }

    # ------------------------------------------------------------------
    # Broadcasting to all connected clients
    # ------------------------------------------------------------------

    async def broadcast_system_message(self, message: Any) -> None:
        """Broadcast a system message to all connected IPC clients."""
        try:
            await self._server.broadcast(message.to_bytes())
        except Exception as exc:  # pragma: no cover - defensive transport guard
            logger.warning("Failed to broadcast system event: %s", exc)

    async def broadcast_session_event(self, *, action: str, session: dict[str, object]) -> None:
        from agent_host.contracts.types.ipc_messages import SystemMessage

        msg = SystemMessage.session_event(
            str(uuid.uuid4()),
            action=action,
            session=session,
        )
        msg.system["seq"] = next(self._lifecycle_seq)
        await self.broadcast_system_message(msg)

    async def broadcast_notes_event(
        self,
        *,
        action: str,
        session_id: str,
        note: dict[str, object] | None = None,
        note_id: str | None = None,
    ) -> None:
        from agent_host.contracts.types.ipc_messages import SystemMessage

        msg = SystemMessage.notes_event(
            str(uuid.uuid4()),
            action=action,
            session_id=session_id,
            note=note,
            note_id=note_id,
        )
        msg.system["seq"] = next(self._lifecycle_seq)
        await self.broadcast_system_message(msg)

    async def broadcast_memory_event(
        self,
        *,
        action: str,
        session_id: str,
        memory_id: str | None = None,
    ) -> None:
        from agent_host.contracts.types.ipc_messages import SystemMessage

        msg = SystemMessage.memory_event(
            str(uuid.uuid4()),
            action=action,
            session_id=session_id,
            memory_id=memory_id,
        )
        msg.system["seq"] = next(self._lifecycle_seq)
        await self.broadcast_system_message(msg)
