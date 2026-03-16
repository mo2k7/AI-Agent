"""Notes IPC handler use cases.

Extracted from ``agent_host/main.py`` to reduce the monolith's size.
All closure dependencies are injected via the constructor.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Callable, Awaitable

from agent_host.core.services.prompt_service import (
    _format_exception_message,
    _normalize_session_id,
)
from agent_host.contracts.types.ipc_messages import ErrorMessage, IncomingRequest, ResultMessage
from agent_host.contracts.ports.client_connection import ClientConnectionPort as ClientConnection

logger = logging.getLogger(__name__)


class NotesUseCases:
    """Encapsulates all notes-related IPC handlers."""

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
    # notes.list
    # ------------------------------------------------------------------

    async def handle_list(self, request: IncomingRequest, client: ClientConnection) -> None:
        """List notes for a session."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        if not session_id:
            await client.send(ErrorMessage.invalid_request(request.id, "Missing session_id").to_bytes())
            return
        limit_raw = request.params.get("limit", 200)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 200
        try:
            notes = await self._run_blocking(
                label="db.list_notes",
                timeout_seconds=self._db_timeout,
                func=self._memory.list_notes,
                args=(session_id,),
                kwargs={"limit": max(1, min(limit, 500))},
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to list notes"),
                ).to_bytes()
            )
            return
        await client.send(ResultMessage.create(request.id, json.dumps(notes)).to_bytes())

    # ------------------------------------------------------------------
    # notes.create
    # ------------------------------------------------------------------

    async def handle_create(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Create a new note."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        content = request.params.get("content")
        if not session_id or not isinstance(content, str) or not content.strip():
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or content").to_bytes()
            )
            return
        source = request.params.get("source", "user")
        if source not in ("user", "agent"):
            source = "user"
        title = request.params.get("title")
        if title is not None and not isinstance(title, str):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Invalid title: expected string when provided").to_bytes()
            )
            return
        workspace_kind = request.params.get("workspace_kind")
        if workspace_kind is not None:
            if not isinstance(workspace_kind, str) or workspace_kind.strip().lower() not in {"session_pad", "tab"}:
                await client.send(
                    ErrorMessage.invalid_request(
                        request.id,
                        "Invalid workspace_kind: expected 'session_pad' or 'tab'",
                    ).to_bytes()
                )
                return
            workspace_kind = workspace_kind.strip().lower()
        is_default_tab = request.params.get("is_default_tab")
        if is_default_tab is not None and not isinstance(is_default_tab, bool):
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, "Invalid is_default_tab: expected boolean when provided",
                ).to_bytes()
            )
            return
        tab_order = request.params.get("tab_order")
        if tab_order is not None and not isinstance(tab_order, int):
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, "Invalid tab_order: expected integer when provided",
                ).to_bytes()
            )
            return
        try:
            note = await self._run_blocking(
                label="db.create_note",
                timeout_seconds=self._db_timeout,
                func=self._memory.create_note,
                args=(session_id,),
                kwargs={
                    "content": content.strip(),
                    "source": source,
                    "title": title,
                    "workspace_kind": workspace_kind,
                    "is_default_tab": bool(is_default_tab),
                    "tab_order": tab_order,
                },
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to create note"),
                ).to_bytes()
            )
            return
        await client.send(ResultMessage.create(request.id, json.dumps(note)).to_bytes())
        await self._ipc.broadcast_notes_event(
            action="created",
            session_id=session_id,
            note=note,
        )
        await self._broadcast_session_refresh(
            session_id=session_id,
            request_id=request.id,
            method=request.method,
        )
        if self._event_bus:
            from agent_host.contracts.types.events import NoteCreated
            self._event_bus.publish(NoteCreated(
                event_type="note.created",
                source="notes_use_case",
                payload={
                    "session_id": session_id,
                    "note_id": note.get("note_id", "") if isinstance(note, dict) else "",
                },
            ))

    # ------------------------------------------------------------------
    # notes.update
    # ------------------------------------------------------------------

    async def handle_update(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Update an existing note."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        note_id = request.params.get("note_id")
        if not session_id or not isinstance(note_id, str):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or note_id").to_bytes()
            )
            return
        content = request.params.get("content")
        if content is not None and not isinstance(content, str):
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, "Invalid content: expected string when provided",
                ).to_bytes()
            )
            return
        is_pinned = request.params.get("is_pinned")
        if is_pinned is not None and not isinstance(is_pinned, bool):
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, "Invalid is_pinned: expected boolean when provided",
                ).to_bytes()
            )
            return
        title = request.params.get("title")
        if title is not None and not isinstance(title, str):
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, "Invalid title: expected string when provided",
                ).to_bytes()
            )
            return
        try:
            updated = await self._run_blocking(
                label="db.update_note",
                timeout_seconds=self._db_timeout,
                func=self._memory.update_note,
                args=(session_id, note_id.strip()),
                kwargs={
                    "content": content,
                    "is_pinned": is_pinned,
                    "title": title,
                },
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to update note"),
                ).to_bytes()
            )
            return
        if updated is None:
            await client.send(
                ErrorMessage.invalid_request(request.id, f"Note not found: {note_id}").to_bytes()
            )
            return
        await client.send(ResultMessage.create(request.id, json.dumps(updated)).to_bytes())
        await self._ipc.broadcast_notes_event(
            action="updated",
            session_id=session_id,
            note=updated,
        )
        await self._broadcast_session_refresh(
            session_id=session_id,
            request_id=request.id,
            method=request.method,
        )
        if self._event_bus:
            from agent_host.contracts.types.events import NoteUpdated
            self._event_bus.publish(NoteUpdated(
                event_type="note.updated",
                source="notes_use_case",
                payload={
                    "session_id": session_id,
                    "note_id": updated.get("note_id", "") if isinstance(updated, dict) else "",
                },
            ))

    # ------------------------------------------------------------------
    # notes.delete
    # ------------------------------------------------------------------

    async def handle_delete(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Delete a note (soft-delete)."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        note_id = request.params.get("note_id")
        if not session_id or not isinstance(note_id, str):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or note_id").to_bytes()
            )
            return
        normalized_note_id = note_id.strip()
        try:
            deleted = await self._run_blocking(
                label="db.delete_note",
                timeout_seconds=self._db_timeout,
                func=self._memory.delete_note,
                args=(session_id, normalized_note_id),
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to delete note"),
                ).to_bytes()
            )
            return
        await client.send(
            ResultMessage.create(
                request.id, json.dumps({"deleted": deleted, "note_id": normalized_note_id}),
            ).to_bytes()
        )
        if deleted:
            await self._ipc.broadcast_notes_event(
                action="deleted",
                session_id=session_id,
                note_id=normalized_note_id,
            )
            await self._broadcast_session_refresh(
                session_id=session_id,
                request_id=request.id,
                method=request.method,
            )
            if self._event_bus:
                from agent_host.contracts.types.events import NoteDeleted
                self._event_bus.publish(NoteDeleted(
                    event_type="note.deleted",
                    source="notes_use_case",
                    payload={
                        "session_id": session_id,
                        "note_id": normalized_note_id,
                    },
                ))

    # ------------------------------------------------------------------
    # notes.get_image
    # ------------------------------------------------------------------

    async def handle_get_image(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Return a single note image's data (base64-encoded) by image_id."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        image_id = request.params.get("image_id")
        if not session_id or not isinstance(image_id, str) or not image_id.strip():
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or image_id").to_bytes()
            )
            return
        try:
            img = await self._run_blocking(
                label="db.get_note_image",
                timeout_seconds=self._db_timeout,
                func=self._memory.get_note_image,
                args=(session_id, image_id.strip()),
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to get note image"),
                ).to_bytes()
            )
            return
        if img is None:
            await client.send(
                ErrorMessage.invalid_request(request.id, f"Image not found: {image_id}").to_bytes()
            )
            return
        result = {
            "image_id": img["image_id"],
            "note_id": img["note_id"],
            "image_data": base64.b64encode(img["image_data"]).decode("ascii"),
            "mime_type": img["mime_type"],
            "width": img["width"],
            "height": img["height"],
            "alt_text": img["alt_text"],
        }
        await client.send(ResultMessage.create(request.id, json.dumps(result)).to_bytes())

    # ------------------------------------------------------------------
    # notes.list_versions
    # ------------------------------------------------------------------

    async def handle_list_versions(self, request: IncomingRequest, client: ClientConnection) -> None:
        """Return version history for a note."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        note_id = request.params.get("note_id")
        if not session_id or not isinstance(note_id, str) or not note_id.strip():
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or note_id").to_bytes()
            )
            return
        try:
            versions = await self._run_blocking(
                label="db.list_note_versions",
                timeout_seconds=self._db_timeout,
                func=self._memory.list_note_versions,
                args=(session_id, note_id.strip()),
                kwargs={"limit": 50},
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to list versions"),
                ).to_bytes()
            )
            return
        await client.send(ResultMessage.create(request.id, json.dumps(versions)).to_bytes())
