"""Adapter wrapping MemoryManager to satisfy the MemoryPort protocol.

Thin delegation layer — all calls forwarded to the underlying manager.
Defensive error boundaries ensure that only domain exceptions (MemoryStoreError,
ValueError) pass through; everything else is wrapped in AdapterError.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_host.contracts.types.errors import AdapterError
from agent_host.memory.store import MemoryStoreError

logger = logging.getLogger(__name__)

_PASSTHROUGH = (MemoryStoreError, ValueError)


class MemoryAdapter:
    """Wraps ``MemoryManager`` to satisfy ``MemoryPort`` protocol."""

    def __init__(self, manager: Any) -> None:
        self._manager = manager

    def create_session(self, *, title: str | None = None, memory_mode: Any = None) -> Any:
        try:
            kwargs: dict[str, Any] = {}
            if title is not None:
                kwargs["title"] = title
            if memory_mode is not None:
                kwargs["memory_mode"] = memory_mode
            return self._manager.create_session(**kwargs)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("MemoryAdapter.create_session failed: %s", exc)
            raise AdapterError(
                f"memory.create_session failed: {exc}",
                source="memory",
                cause=exc,
            ) from exc

    def get_session(self, session_id: str) -> Any | None:
        try:
            return self._manager.get_session(session_id)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("MemoryAdapter.get_session failed: %s", exc)
            raise AdapterError(
                f"memory.get_session failed: {exc}",
                source="memory",
                cause=exc,
            ) from exc

    def ensure_session(self, session_id: str, *, memory_mode: Any) -> Any:
        try:
            return self._manager.ensure_session(session_id, memory_mode=memory_mode)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("MemoryAdapter.ensure_session failed: %s", exc)
            raise AdapterError(
                f"memory.ensure_session failed: {exc}",
                source="memory",
                cause=exc,
            ) from exc

    def list_sessions(self, *, limit: int | None = 50) -> list[Any]:
        try:
            return self._manager.list_sessions(limit=limit)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("MemoryAdapter.list_sessions failed: %s", exc)
            raise AdapterError(
                f"memory.list_sessions failed: {exc}",
                source="memory",
                cause=exc,
            ) from exc

    def list_sessions_since(
        self, since_version: int, *, limit: int = 200
    ) -> tuple[list[Any], int]:
        try:
            return self._manager.list_sessions_since(since_version, limit=limit)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("MemoryAdapter.list_sessions_since failed: %s", exc)
            raise AdapterError(
                f"memory.list_sessions_since failed: {exc}",
                source="memory",
                cause=exc,
            ) from exc

    def prepare_prompt_context(
        self,
        *,
        session_id: str,
        prompt: str,
        memory_mode: Any,
        verbosity_level: int = 2,
    ) -> Any:
        try:
            return self._manager.prepare_prompt_context(
                session_id=session_id,
                prompt=prompt,
                memory_mode=memory_mode,
                verbosity_level=verbosity_level,
            )
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("MemoryAdapter.prepare_prompt_context failed: %s", exc)
            raise AdapterError(
                f"memory.prepare_prompt_context failed: {exc}",
                source="memory",
                cause=exc,
            ) from exc

    def record_interaction(
        self,
        *,
        session_id: str,
        memory_mode: Any,
        user_prompt: str,
        assistant_response: str,
        model_name: str,
    ) -> None:
        try:
            self._manager.record_interaction(
                session_id=session_id,
                memory_mode=memory_mode,
                user_prompt=user_prompt,
                assistant_response=assistant_response,
                model_name=model_name,
            )
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("MemoryAdapter.record_interaction failed: %s", exc)
            raise AdapterError(
                f"memory.record_interaction failed: {exc}",
                source="memory",
                cause=exc,
            ) from exc

    def create_note(
        self,
        session_id: str,
        *,
        content: str,
        source: str = "user",
        title: str | None = None,
        workspace_kind: str | None = None,
        extra_tags: Any = None,
    ) -> dict[str, object] | None:
        try:
            return self._manager.create_note(
                session_id,
                content=content,
                source=source,
                title=title,
                workspace_kind=workspace_kind,
                extra_tags=extra_tags,
            )
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("MemoryAdapter.create_note failed: %s", exc)
            raise AdapterError(
                f"memory.create_note failed: {exc}",
                source="memory",
                cause=exc,
            ) from exc

    def update_note(
        self,
        session_id: str,
        note_id: str,
        *,
        content: str | None = None,
        is_pinned: bool | None = None,
        title: str | None = None,
        touch_timestamp: float | None = None,
    ) -> dict[str, object] | None:
        try:
            return self._manager.update_note(
                session_id,
                note_id,
                content=content,
                is_pinned=is_pinned,
                title=title,
                touch_timestamp=touch_timestamp,
            )
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("MemoryAdapter.update_note failed: %s", exc)
            raise AdapterError(
                f"memory.update_note failed: {exc}",
                source="memory",
                cause=exc,
            ) from exc

    def delete_note(self, session_id: str, note_id: str) -> bool:
        try:
            return self._manager.delete_note(session_id, note_id)
        except _PASSTHROUGH:
            raise
        except Exception as exc:
            logger.error("MemoryAdapter.delete_note failed: %s", exc)
            raise AdapterError(
                f"memory.delete_note failed: {exc}",
                source="memory",
                cause=exc,
            ) from exc
