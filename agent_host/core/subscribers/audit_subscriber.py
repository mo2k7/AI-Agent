"""Audit event subscriber -- logs domain events to the audit trail.

Registered in the Composition Root.  Can be removed without affecting
core system operation (the system runs correctly without audit subscribers).
"""

from __future__ import annotations

import logging
from typing import Any

from agent_host.contracts.types.events import Event

logger = logging.getLogger(__name__)


class AuditEventSubscriber:
    """Subscribes to domain events and logs them to the audit trail."""

    def __init__(self, audit_logger: Any) -> None:
        self._audit = audit_logger

    def on_tool_execution_completed(self, event: Event) -> None:
        """Handle tool.execution.completed events."""
        self._audit.log_event("TOOL_EVENT", {
            "event_type": event.event_type,
            "tool": event.payload.get("tool", "unknown"),
            "ok": event.payload.get("ok", False),
            "latency_ms": event.payload.get("latency_ms", 0),
            "correlation_id": event.correlation_id,
        })

    def on_session_event(self, event: Event) -> None:
        """Handle session.created and session.deleted events."""
        self._audit.log_event("SESSION_EVENT", {
            "event_type": event.event_type,
            "session_id": event.payload.get("session_id", ""),
            "correlation_id": event.correlation_id,
        })

    def on_note_event(self, event: Event) -> None:
        """Handle note.created, note.updated, and note.deleted events."""
        self._audit.log_event("NOTE_EVENT", {
            "event_type": event.event_type,
            "session_id": event.payload.get("session_id", ""),
            "note_id": event.payload.get("note_id", ""),
            "correlation_id": event.correlation_id,
        })

    def on_memory_event(self, event: Event) -> None:
        """Handle memory.deleted events."""
        self._audit.log_event("MEMORY_EVENT", {
            "event_type": event.event_type,
            "session_id": event.payload.get("session_id", ""),
            "memory_id": event.payload.get("memory_id", ""),
            "correlation_id": event.correlation_id,
        })

    def on_error(self, event: Event) -> None:
        """Handle error.occurred events."""
        self._audit.log_event("ERROR_EVENT", {
            "event_type": event.event_type,
            "error": event.payload.get("error", ""),
            "source": event.source,
            "correlation_id": event.correlation_id,
        })

    def register(self, event_bus: Any) -> None:
        """Register all subscriptions with the event bus."""
        event_bus.subscribe("tool.execution.completed", self.on_tool_execution_completed)
        event_bus.subscribe("session.created", self.on_session_event)
        event_bus.subscribe("session.deleted", self.on_session_event)
        event_bus.subscribe("note.created", self.on_note_event)
        event_bus.subscribe("note.updated", self.on_note_event)
        event_bus.subscribe("note.deleted", self.on_note_event)
        event_bus.subscribe("memory.deleted", self.on_memory_event)
        event_bus.subscribe("error.occurred", self.on_error)
