"""Port interface for memory/session storage.

Abstracts the concrete MemoryManager so the core domain can manage
sessions, messages, and notes without depending on SQLite or encryption.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MemoryPort(Protocol):
    """Abstract interface for session and memory management."""

    # -- Session lifecycle --

    def create_session(self, *, title: str | None = None, memory_mode: Any = None) -> Any:
        """Create a new session."""
        ...

    def get_session(self, session_id: str) -> Any | None:
        """Retrieve session metadata by ID."""
        ...

    def ensure_session(self, session_id: str, *, memory_mode: Any) -> Any:
        """Get or create a session."""
        ...

    def list_sessions(self, *, limit: int | None = 50) -> list[Any]:
        """List sessions ordered by recency."""
        ...

    def list_sessions_since(
        self, since_version: int, *, limit: int = 200
    ) -> tuple[list[Any], int]:
        """List sessions updated since a store version."""
        ...

    # -- Prompt context --

    def prepare_prompt_context(
        self,
        *,
        session_id: str,
        prompt: str,
        memory_mode: Any,
        verbosity_level: int = 2,
    ) -> Any:
        """Prepare augmented prompt with memory context."""
        ...

    def record_interaction(
        self,
        *,
        session_id: str,
        memory_mode: Any,
        user_prompt: str,
        assistant_response: str,
        model_name: str,
    ) -> None:
        """Record a completed interaction turn."""
        ...

    # -- Notes --

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
        """Create a note in a session."""
        ...

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
        """Update a note."""
        ...

    def delete_note(self, session_id: str, note_id: str) -> bool:
        """Soft-delete a note."""
        ...
