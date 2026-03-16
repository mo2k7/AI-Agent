"""In-memory event bus for synchronous, in-process pub/sub.

Satisfies the ``EventBus`` protocol from ``agent_host.contracts.ports``.
Designed for single-process use — all publish/subscribe operations are
thread-safe via a ``threading.Lock``.

Failed handler invocations are captured in a dead letter queue for
debugging without impacting other subscribers or the publisher.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from agent_host.contracts.types.events import Event

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeadLetter:
    """Record of a failed event handler invocation."""

    event: Event
    handler_name: str
    error: str
    timestamp: float = field(default_factory=time.time)
    attempt: int = 1


class InMemoryEventBus:
    """Synchronous in-process event bus.

    Satisfies the ``EventBus`` protocol::

        bus = InMemoryEventBus()
        bus.subscribe("tool.completed", my_handler)
        bus.publish(ToolExecutionCompleted(event_type="tool.completed", ...))

    Thread Safety
    -------------
    All mutations to subscriber lists and the dead letter queue are
    protected by a ``threading.Lock``.  Publishing iterates over a
    snapshot of the handler list so handlers may subscribe/unsubscribe
    during dispatch without deadlocking.

    Dead Letter Queue
    -----------------
    When a handler raises an exception, the event is retried up to
    ``max_retries`` times.  After exhausting retries, a ``DeadLetter``
    record is appended to ``dead_letters`` for later inspection.
    The dead letter queue is bounded to ``max_dead_letters`` entries.
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        max_dead_letters: int = 500,
    ) -> None:
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}
        self._lock = threading.Lock()
        self._max_retries = max_retries
        self.dead_letters: deque[DeadLetter] = deque(maxlen=max_dead_letters)
        self._publish_count = 0
        self._error_count = 0

    # ------------------------------------------------------------------
    # EventBus protocol
    # ------------------------------------------------------------------

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers of its type.

        Each handler is invoked synchronously.  A failing handler does
        not prevent other handlers from receiving the event.
        """
        with self._lock:
            handlers = list(self._subscribers.get(event.event_type, []))
        self._publish_count += 1

        for handler in handlers:
            self._invoke_with_retry(handler, event)

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], None],
    ) -> None:
        """Subscribe a handler to events of a specific type."""
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(
        self,
        event_type: str,
        handler: Callable[[Event], None],
    ) -> None:
        """Remove a handler subscription.

        Silently does nothing if the handler is not subscribed.
        """
        with self._lock:
            handlers = self._subscribers.get(event_type, [])
            try:
                handlers.remove(handler)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Retry + dead letter
    # ------------------------------------------------------------------

    def _invoke_with_retry(
        self,
        handler: Callable[[Event], None],
        event: Event,
    ) -> None:
        handler_name = getattr(handler, "__qualname__", repr(handler))

        for attempt in range(1, self._max_retries + 1):
            try:
                handler(event)
                return  # success
            except Exception as exc:
                logger.warning(
                    "Event handler %s failed (attempt %d/%d) for %s: %s",
                    handler_name,
                    attempt,
                    self._max_retries,
                    event.event_type,
                    exc,
                )
                if attempt == self._max_retries:
                    self._error_count += 1
                    dead = DeadLetter(
                        event=event,
                        handler_name=handler_name,
                        error=str(exc),
                        attempt=attempt,
                    )
                    with self._lock:
                        self.dead_letters.append(dead)
                    logger.error(
                        "Event handler %s exhausted retries for %s; "
                        "added to dead letter queue",
                        handler_name,
                        event.event_type,
                    )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def subscriber_count(self) -> int:
        """Total number of active subscriptions across all event types."""
        with self._lock:
            return sum(len(h) for h in self._subscribers.values())

    @property
    def publish_count(self) -> int:
        """Total number of events published since creation."""
        return self._publish_count

    @property
    def error_count(self) -> int:
        """Total number of handler failures that exhausted retries."""
        return self._error_count

    def subscriber_count_for(self, event_type: str) -> int:
        """Number of subscribers for a specific event type."""
        with self._lock:
            return len(self._subscribers.get(event_type, []))

    def clear(self) -> None:
        """Remove all subscribers and dead letters."""
        with self._lock:
            self._subscribers.clear()
            self.dead_letters.clear()
        self._publish_count = 0
        self._error_count = 0
