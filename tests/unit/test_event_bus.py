"""Tests for the InMemoryEventBus adapter."""

from __future__ import annotations

import threading

import pytest

from agent_host.adapters.event_bus.in_memory_bus import DeadLetter, InMemoryEventBus
from agent_host.contracts.ports import EventBus
from agent_host.contracts.types.events import (
    Event,
    ToolExecutionCompleted,
    SessionCreated,
    ErrorOccurred,
)


# =========================================================================
# Protocol conformance
# =========================================================================


class TestProtocolConformance:
    def test_satisfies_event_bus_protocol(self):
        bus = InMemoryEventBus()
        assert isinstance(bus, EventBus)


# =========================================================================
# Basic publish / subscribe
# =========================================================================


class TestPublishSubscribe:
    def test_single_subscriber(self):
        bus = InMemoryEventBus()
        received: list[Event] = []
        bus.subscribe("tool.done", received.append)
        bus.publish(Event(event_type="tool.done", payload={"name": "search"}))

        assert len(received) == 1
        assert received[0].event_type == "tool.done"
        assert received[0].payload["name"] == "search"

    def test_multiple_subscribers_same_event(self):
        bus = InMemoryEventBus()
        a, b = [], []
        bus.subscribe("x", a.append)
        bus.subscribe("x", b.append)
        bus.publish(Event(event_type="x"))

        assert len(a) == 1
        assert len(b) == 1

    def test_subscribers_only_receive_matching_events(self):
        bus = InMemoryEventBus()
        received: list[Event] = []
        bus.subscribe("wanted", received.append)
        bus.publish(Event(event_type="unwanted"))
        bus.publish(Event(event_type="wanted"))

        assert len(received) == 1
        assert received[0].event_type == "wanted"

    def test_no_subscribers_does_not_crash(self):
        bus = InMemoryEventBus()
        bus.publish(Event(event_type="orphan.event"))
        assert bus.publish_count == 1

    def test_publish_count_increments(self):
        bus = InMemoryEventBus()
        assert bus.publish_count == 0
        bus.publish(Event(event_type="a"))
        bus.publish(Event(event_type="b"))
        assert bus.publish_count == 2

    def test_event_subclass_delivered(self):
        bus = InMemoryEventBus()
        received: list[Event] = []
        bus.subscribe("tool.completed", received.append)
        bus.publish(ToolExecutionCompleted(event_type="tool.completed", payload={"tool": "browse_web"}))

        assert len(received) == 1
        assert isinstance(received[0], ToolExecutionCompleted)

    def test_multiple_event_types(self):
        bus = InMemoryEventBus()
        tools, sessions = [], []
        bus.subscribe("tool.completed", tools.append)
        bus.subscribe("session.created", sessions.append)

        bus.publish(ToolExecutionCompleted(event_type="tool.completed"))
        bus.publish(SessionCreated(event_type="session.created"))
        bus.publish(ToolExecutionCompleted(event_type="tool.completed"))

        assert len(tools) == 2
        assert len(sessions) == 1


# =========================================================================
# Unsubscribe
# =========================================================================


class TestUnsubscribe:
    def test_unsubscribe_stops_delivery(self):
        bus = InMemoryEventBus()
        received: list[Event] = []
        bus.subscribe("x", received.append)
        bus.publish(Event(event_type="x"))
        assert len(received) == 1

        bus.unsubscribe("x", received.append)
        bus.publish(Event(event_type="x"))
        assert len(received) == 1  # no second delivery

    def test_unsubscribe_nonexistent_handler_is_safe(self):
        bus = InMemoryEventBus()
        bus.unsubscribe("nope", lambda e: None)  # should not raise

    def test_unsubscribe_nonexistent_event_type_is_safe(self):
        bus = InMemoryEventBus()
        bus.unsubscribe("never.registered", lambda e: None)

    def test_unsubscribe_only_removes_target(self):
        bus = InMemoryEventBus()
        a, b = [], []
        handler_a = a.append
        handler_b = b.append
        bus.subscribe("x", handler_a)
        bus.subscribe("x", handler_b)

        bus.unsubscribe("x", handler_a)
        bus.publish(Event(event_type="x"))

        assert len(a) == 0
        assert len(b) == 1


# =========================================================================
# Error handling / dead letter queue
# =========================================================================


class TestDeadLetterQueue:
    def test_failing_handler_retries(self):
        bus = InMemoryEventBus(max_retries=3)
        call_count = 0

        def flaky(e):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("transient")

        bus.subscribe("fail", flaky)
        bus.publish(Event(event_type="fail"))

        assert call_count == 3
        assert len(bus.dead_letters) == 1

    def test_dead_letter_captures_error_details(self):
        bus = InMemoryEventBus(max_retries=2)

        def bad(e):
            raise ValueError("bad input")

        bus.subscribe("err", bad)
        event = Event(event_type="err", source="test", payload={"k": "v"})
        bus.publish(event)

        dl = bus.dead_letters[0]
        assert dl.error == "bad input"
        assert dl.handler_name.endswith("bad")
        assert dl.event is event
        assert dl.attempt == 2

    def test_failing_handler_does_not_block_others(self):
        bus = InMemoryEventBus(max_retries=1)
        received: list[Event] = []

        def bad(e):
            raise RuntimeError("boom")

        bus.subscribe("x", bad)
        bus.subscribe("x", received.append)
        bus.publish(Event(event_type="x"))

        assert len(received) == 1  # second handler still runs
        assert len(bus.dead_letters) == 1

    def test_error_count_tracks_exhausted_retries(self):
        bus = InMemoryEventBus(max_retries=1)

        bus.subscribe("a", lambda e: (_ for _ in ()).throw(RuntimeError("x")))
        bus.subscribe("b", lambda e: (_ for _ in ()).throw(RuntimeError("y")))

        bus.publish(Event(event_type="a"))
        bus.publish(Event(event_type="b"))

        assert bus.error_count == 2

    def test_dead_letter_queue_bounded(self):
        bus = InMemoryEventBus(max_retries=1, max_dead_letters=3)
        bus.subscribe("x", lambda e: (_ for _ in ()).throw(RuntimeError()))

        for i in range(10):
            bus.publish(Event(event_type="x", payload={"i": i}))

        assert len(bus.dead_letters) == 3
        # Oldest entries evicted — only last 3 remain
        assert bus.dead_letters[0].event.payload["i"] == 7

    def test_handler_succeeds_on_retry(self):
        bus = InMemoryEventBus(max_retries=3)
        call_count = 0

        def eventually_ok(e):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("not yet")

        bus.subscribe("retry", eventually_ok)
        bus.publish(Event(event_type="retry"))

        assert call_count == 3
        assert len(bus.dead_letters) == 0  # succeeded on 3rd try


# =========================================================================
# Introspection
# =========================================================================


class TestIntrospection:
    def test_subscriber_count(self):
        bus = InMemoryEventBus()
        assert bus.subscriber_count == 0

        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        bus.subscribe("a", lambda e: None)
        assert bus.subscriber_count == 3

    def test_subscriber_count_for(self):
        bus = InMemoryEventBus()
        bus.subscribe("x", lambda e: None)
        bus.subscribe("x", lambda e: None)
        bus.subscribe("y", lambda e: None)

        assert bus.subscriber_count_for("x") == 2
        assert bus.subscriber_count_for("y") == 1
        assert bus.subscriber_count_for("z") == 0

    def test_clear(self):
        bus = InMemoryEventBus(max_retries=1)
        bus.subscribe("x", lambda e: (_ for _ in ()).throw(RuntimeError()))
        bus.publish(Event(event_type="x"))

        assert bus.subscriber_count > 0
        assert len(bus.dead_letters) > 0
        assert bus.publish_count > 0

        bus.clear()

        assert bus.subscriber_count == 0
        assert len(bus.dead_letters) == 0
        assert bus.publish_count == 0


# =========================================================================
# Thread safety
# =========================================================================


class TestThreadSafety:
    def test_concurrent_publish_subscribe(self):
        bus = InMemoryEventBus()
        received: list[Event] = []
        lock = threading.Lock()

        def safe_append(e):
            with lock:
                received.append(e)

        bus.subscribe("concurrent", safe_append)

        def publisher():
            for _ in range(100):
                bus.publish(Event(event_type="concurrent"))

        threads = [threading.Thread(target=publisher) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(received) == 400

    def test_subscribe_during_publish(self):
        """Subscribing during publish doesn't cause deadlock or crash."""
        bus = InMemoryEventBus()

        def subscribe_more(e):
            bus.subscribe("other", lambda e: None)

        bus.subscribe("trigger", subscribe_more)
        bus.publish(Event(event_type="trigger"))

        assert bus.subscriber_count_for("other") == 1
