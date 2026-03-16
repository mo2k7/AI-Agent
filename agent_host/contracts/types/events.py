"""Event types for the event-driven communication pattern.

Events enable decoupled communication between modules.  A module emits
an event; zero or more subscribers react.  If a subscriber is removed,
the event simply goes unhandled -- no crash.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    """Base event with standard metadata."""

    event_type: str
    timestamp: float = field(default_factory=time.time)
    source: str = ""
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    payload: dict[str, Any] = field(default_factory=dict)


# -- Tool events --


class ToolExecutionStarted(Event):
    """Emitted when a tool begins execution."""

    pass


class ToolExecutionCompleted(Event):
    """Emitted when a tool finishes execution (success or failure)."""

    pass


# -- Prompt events --


class PromptReceived(Event):
    """Emitted when a new prompt is received from the frontend."""

    pass


class PromptCompleted(Event):
    """Emitted when prompt processing finishes."""

    pass


# -- Session events --


class SessionCreated(Event):
    """Emitted when a new session is created."""

    pass


class SessionDeleted(Event):
    """Emitted when a session is deleted."""

    pass


# -- Note events --


class NoteCreated(Event):
    """Emitted when a note is created."""

    pass


class NoteUpdated(Event):
    """Emitted when a note is updated."""

    pass


class NoteDeleted(Event):
    """Emitted when a note is deleted."""

    pass


# -- Memory events --


class MemoryDeleted(Event):
    """Emitted when a semantic memory entry is deleted."""

    pass


# -- System events --


class ErrorOccurred(Event):
    """Emitted when an error occurs at any boundary."""

    pass


class HealthCheckCompleted(Event):
    """Emitted after a component health check."""

    pass
