"""Session IPC handler use cases.

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
    _parse_memory_mode,
    _parse_memory_mode_strict,
)
from agent_host.contracts.types.ipc_messages import ErrorMessage, IncomingRequest, ResultMessage
from agent_host.contracts.ports.client_connection import ClientConnectionPort as ClientConnection
from agent_host.contracts.types.errors import MemoryStoreError
from agent_host.contracts.types.domain import MemoryMode

logger = logging.getLogger(__name__)


class SessionUseCases:
    """Encapsulates all session-related IPC handlers."""

    def __init__(
        self,
        *,
        memory_manager: Any,
        ipc_bridge: Any,
        run_blocking: Callable[..., Awaitable[Any]],
        db_timeout_seconds: float,
        audit_logger: Any = None,
        event_bus: Any | None = None,
    ) -> None:
        self._memory = memory_manager
        self._ipc = ipc_bridge
        self._run_blocking = run_blocking
        self._db_timeout = db_timeout_seconds
        self._audit = audit_logger
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # session.create
    # ------------------------------------------------------------------

    async def handle_create(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Create a secure session memory container."""
        title_raw = request.params.get("title")
        mode = MemoryMode.ON
        if "memory_mode" in request.params:
            parsed_mode = _parse_memory_mode_strict(request.params.get("memory_mode"))
            if parsed_mode is None:
                await client.send(
                    ErrorMessage.invalid_request(
                        request.id,
                        f"Invalid memory_mode: {request.params.get('memory_mode')}",
                    ).to_bytes()
                )
                return
            mode = parsed_mode
        title = title_raw if isinstance(title_raw, str) else None
        session = await self._run_blocking(
            label="db.create_session",
            timeout_seconds=self._db_timeout,
            func=self._memory.create_session,
            args=(),
            kwargs={"title": title, "memory_mode": mode},
            request_id=request.id,
            method=request.method,
        )
        payload = self._ipc.session_payload(session)
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())
        await self._ipc.broadcast_session_event(action="created", session=payload)
        if self._event_bus:
            from agent_host.contracts.types.events import SessionCreated
            self._event_bus.publish(SessionCreated(
                event_type="session.created",
                source="session_use_case",
                payload={"session_id": payload.get("session_id", "")},
            ))

    # ------------------------------------------------------------------
    # session.list
    # ------------------------------------------------------------------

    async def handle_list(self, request: IncomingRequest, client: ClientConnection) -> None:
        """List known sessions."""
        limit_raw = request.params.get("limit", 50)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 50
        resolved_limit: int | None = None if limit <= 0 else max(1, min(limit, 5000))
        sessions = await self._run_blocking(
            label="db.list_sessions",
            timeout_seconds=self._db_timeout,
            func=self._memory.list_sessions,
            args=(),
            kwargs={"limit": resolved_limit},
            request_id=request.id,
            method=request.method,
        )
        payload = [self._ipc.session_payload(session) for session in sessions]
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())

    # ------------------------------------------------------------------
    # session.list_since
    # ------------------------------------------------------------------

    async def handle_list_since(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Return sessions changed since a given store_version cursor."""
        since_raw = request.params.get("since_version", 0)
        try:
            since_version = int(since_raw)
        except (TypeError, ValueError):
            since_version = 0
        limit_raw = request.params.get("limit", 200)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 200
        records, max_version = await self._run_blocking(
            label="db.list_sessions_since",
            timeout_seconds=self._db_timeout,
            func=self._memory.list_sessions_since,
            args=(max(0, since_version),),
            kwargs={"limit": max(1, min(limit, 500))},
            request_id=request.id,
            method=request.method,
        )
        result = {
            "sessions": [self._ipc.session_payload(s) for s in records],
            "max_version": max_version,
        }
        await client.send(ResultMessage.create(request.id, json.dumps(result)).to_bytes())

    # ------------------------------------------------------------------
    # session.history
    # ------------------------------------------------------------------

    async def handle_history(self, request: IncomingRequest, client: ClientConnection) -> None:
        """List persisted chat messages for a session."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        if not session_id:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id").to_bytes()
            )
            return

        limit_raw = request.params.get("limit", 500)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 500

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

        if "memory_mode" in request.params:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    "session.history no longer accepts memory_mode",
                ).to_bytes()
            )
            return

        try:
            payload = await self._run_blocking(
                label="db.list_session_messages",
                timeout_seconds=self._db_timeout,
                func=self._memory.list_session_messages,
                args=(),
                kwargs={
                    "session_id": session_id,
                    "limit": max(1, min(limit, 2000)),
                },
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
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())

    # ------------------------------------------------------------------
    # session.history_page
    # ------------------------------------------------------------------

    async def handle_history_page(self, request: IncomingRequest, client: ClientConnection) -> None:
        """List a bounded page of persisted chat messages for a session."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        if not session_id:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id").to_bytes()
            )
            return

        direction = str(request.params.get("direction", "latest") or "latest").strip().lower()
        if direction not in {"latest", "older"}:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    f"Unsupported session.history_page direction: {direction}",
                ).to_bytes()
            )
            return

        limit_raw = request.params.get("limit", 120)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 120

        anchor_raw = request.params.get("anchor_turn_index")
        anchor_turn_index: int | None = None
        if anchor_raw is not None:
            try:
                anchor_turn_index = int(anchor_raw)
            except (TypeError, ValueError):
                await client.send(
                    ErrorMessage.invalid_request(
                        request.id,
                        "anchor_turn_index must be an integer",
                    ).to_bytes()
                )
                return

        if direction == "older" and anchor_turn_index is None:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    "anchor_turn_index is required for older history pages",
                ).to_bytes()
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

        try:
            payload = await self._run_blocking(
                label="db.list_session_messages_page",
                timeout_seconds=self._db_timeout,
                func=self._memory.list_session_messages_page,
                args=(),
                kwargs={
                    "session_id": session_id,
                    "direction": direction,
                    "limit": max(1, min(limit, 120)),
                    "anchor_turn_index": anchor_turn_index,
                },
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
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())

    # ------------------------------------------------------------------
    # session.set_mode
    # ------------------------------------------------------------------

    async def handle_set_mode(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Update a session's memory mode."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        mode_raw = request.params.get("memory_mode")
        if not session_id or not isinstance(mode_raw, str):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or memory_mode").to_bytes()
            )
            return

        normalized_mode = mode_raw.strip().lower()
        mode = _parse_memory_mode(mode_raw, default=MemoryMode.ON)
        if normalized_mode != mode.value:
            await client.send(
                ErrorMessage.invalid_request(request.id, f"Invalid memory_mode: {mode_raw}").to_bytes()
            )
            return

        try:
            updated = await self._run_blocking(
                label="db.set_session_mode",
                timeout_seconds=self._db_timeout,
                func=self._memory.set_session_mode,
                args=(),
                kwargs={"session_id": session_id, "memory_mode": mode},
                request_id=request.id,
                method=request.method,
            )
        except ValueError as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    _format_exception_message(exc, fallback="Unable to set session mode"),
                ).to_bytes()
            )
            return

        payload = self._ipc.session_payload(updated)
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())
        await self._ipc.broadcast_session_event(action="updated", session=payload)

    # ------------------------------------------------------------------
    # session.rename
    # ------------------------------------------------------------------

    async def handle_rename(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Rename a session."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        title_raw = request.params.get("title")
        title = title_raw.strip() if isinstance(title_raw, str) else ""
        if not session_id or not title:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or title").to_bytes()
            )
            return

        try:
            renamed = await self._run_blocking(
                label="db.rename_session",
                timeout_seconds=self._db_timeout,
                func=self._memory.rename_session,
                args=(),
                kwargs={"session_id": session_id, "title": title},
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Unable to rename session")
                ).to_bytes()
            )
            return
        payload = self._ipc.session_payload(renamed)
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())
        await self._ipc.broadcast_session_event(action="updated", session=payload)

    # ------------------------------------------------------------------
    # session.delete
    # ------------------------------------------------------------------

    async def handle_delete(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Delete a session and its encrypted memory store."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        if not session_id:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id").to_bytes()
            )
            return
        existing_session = await self._run_blocking(
            label="db.get_session",
            timeout_seconds=self._db_timeout,
            func=self._memory.get_session,
            args=(session_id,),
            request_id=request.id,
            method=request.method,
        )
        try:
            await self._run_blocking(
                label="db.delete_session",
                timeout_seconds=self._db_timeout,
                func=self._memory.delete_session,
                args=(session_id,),
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    _format_exception_message(exc, fallback=f"Unable to delete session: {session_id}"),
                ).to_bytes()
            )
            return

        payload = {
            "deleted": True,
            "session_id": session_id,
        }
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())
        await self._ipc.broadcast_session_event(
            action="deleted",
            session=(
                self._ipc.session_payload(existing_session)
                if existing_session is not None
                else {"session_id": session_id, "status": "deleted"}
            ),
        )
        if self._event_bus:
            from agent_host.contracts.types.events import SessionDeleted
            self._event_bus.publish(SessionDeleted(
                event_type="session.deleted",
                source="session_use_case",
                payload={"session_id": session_id},
            ))

    # ------------------------------------------------------------------
    # session.delete_many
    # ------------------------------------------------------------------

    async def handle_delete_many(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Delete multiple sessions and return per-session outcomes."""
        raw_ids = request.params.get("session_ids")
        if not isinstance(raw_ids, list):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_ids list").to_bytes()
            )
            return

        ordered_ids: list[str] = []
        seen: set[str] = set()
        for raw in raw_ids:
            normalized = _normalize_session_id(raw, fallback="")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered_ids.append(normalized)

        if not ordered_ids:
            await client.send(
                ErrorMessage.invalid_request(request.id, "No valid session_ids provided").to_bytes()
            )
            return

        try:
            deleted_ids, failed = await self._run_blocking(
                label="db.delete_sessions",
                timeout_seconds=min(max(self._db_timeout, len(ordered_ids) * 5.0), 60.0),
                func=self._memory.delete_sessions,
                args=(ordered_ids,),
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    _format_exception_message(exc, fallback="Unable to delete sessions"),
                ).to_bytes()
            )
            return

        payload = {
            "requested_count": len(ordered_ids),
            "deleted_count": len(deleted_ids),
            "deleted_session_ids": deleted_ids,
            "failed": [
                {"session_id": session_id, "error": reason}
                for session_id, reason in failed.items()
            ],
        }
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())
        for deleted_session_id in deleted_ids:
            await self._ipc.broadcast_session_event(
                action="deleted",
                session={"session_id": deleted_session_id, "status": "deleted"},
            )
        if self._event_bus and deleted_ids:
            from agent_host.contracts.types.events import SessionDeleted
            for deleted_session_id in deleted_ids:
                self._event_bus.publish(SessionDeleted(
                    event_type="session.deleted",
                    source="session_use_case",
                    payload={"session_id": deleted_session_id},
                ))
