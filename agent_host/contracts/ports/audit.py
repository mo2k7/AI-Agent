"""Port interface for audit logging.

Abstracts the concrete AuditLogger so audit recording can be swapped
(e.g., file-based, database, event-driven) without touching core logic.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AuditPort(Protocol):
    """Abstract interface for audit event recording."""

    def log_event(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Record an audit event."""
        ...

    def log_error(
        self,
        error_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an error event."""
        ...
