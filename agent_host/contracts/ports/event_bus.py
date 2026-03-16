"""Port interface for the event bus.

Enables decoupled cross-module communication via publish/subscribe.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from agent_host.contracts.types.events import Event


@runtime_checkable
class EventBus(Protocol):
    """Abstract interface for event publishing and subscription."""

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers of its type."""
        ...

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Subscribe a handler to events of a specific type."""
        ...

    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Remove a subscription."""
        ...
