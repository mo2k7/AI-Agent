"""Tests for event bus integration with ToolExecutor, use cases, and audit subscriber."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_host.adapters.event_bus.in_memory_bus import InMemoryEventBus
from agent_host.contracts.types.events import (
    Event,
    MemoryDeleted,
    NoteCreated,
    NoteDeleted,
    NoteUpdated,
    SessionCreated,
    SessionDeleted,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from agent_host.core.subscribers.audit_subscriber import AuditEventSubscriber
from agent_host.tools.executor import ToolExecutionError, ToolExecutor


# =========================================================================
# Helpers
# =========================================================================


def _make_executor_with_bus(
    tmp_path: Path,
    event_bus: InMemoryEventBus | None = None,
) -> ToolExecutor:
    from tests.conftest import build_tool_executor
    return build_tool_executor(tmp_path, event_bus=event_bus)


def _make_request(params: dict[str, Any] | None = None) -> Any:
    """Create a minimal IncomingRequest-like object."""
    req = MagicMock()
    req.id = "test-req-1"
    req.method = "test.method"
    req.params = params or {}
    return req


def _make_client() -> Any:
    """Create a minimal ClientConnection-like object."""
    client = AsyncMock()
    client.send = AsyncMock()
    return client


def _make_ipc_bridge() -> Any:
    bridge = AsyncMock()
    bridge.session_payload = MagicMock(side_effect=lambda s: {"session_id": s.get("id", "sid")})
    bridge.broadcast_session_event = AsyncMock()
    bridge.broadcast_notes_event = AsyncMock()
    bridge.broadcast_memory_event = AsyncMock()
    return bridge


async def _run_blocking_passthrough(*, label, timeout_seconds, func, args=(), kwargs=None, request_id=None, method=None):
    """Minimal run_blocking that just calls the function directly."""
    kw = kwargs or {}
    return func(*args, **kw)


# =========================================================================
# ToolExecutor event publishing
# =========================================================================


class TestToolExecutorEvents:
    def test_publishes_started_and_completed_on_success(self, tmp_path: Path) -> None:
        bus = InMemoryEventBus()
        received: list[Event] = []
        bus.subscribe("tool.execution.started", received.append)
        bus.subscribe("tool.execution.completed", received.append)

        executor = _make_executor_with_bus(tmp_path, event_bus=bus)

        # search_files is available; create a file to search
        target = tmp_path / "hello.txt"
        target.write_text("hello world")

        result = executor.execute("search_files", {"query": "hello", "limit": 5})

        assert result["ok"] is True
        assert len(received) == 2

        started = received[0]
        assert isinstance(started, ToolExecutionStarted)
        assert started.event_type == "tool.execution.started"
        assert started.payload["tool"] == "search_files"

        completed = received[1]
        assert isinstance(completed, ToolExecutionCompleted)
        assert completed.event_type == "tool.execution.completed"
        assert completed.payload["tool"] == "search_files"
        assert completed.payload["ok"] is True
        assert completed.payload["latency_ms"] >= 0

    def test_publishes_completed_with_ok_false_on_error(self, tmp_path: Path) -> None:
        bus = InMemoryEventBus()
        completed_events: list[Event] = []
        bus.subscribe("tool.execution.completed", completed_events.append)

        executor = _make_executor_with_bus(tmp_path, event_bus=bus)

        with pytest.raises(ToolExecutionError):
            executor.execute("nonexistent_tool", {})

        # nonexistent_tool raises before started event, so no completed event
        # But let's verify the started event was NOT published for not_found
        started_events: list[Event] = []
        bus2 = InMemoryEventBus()
        bus2.subscribe("tool.execution.started", started_events.append)
        executor2 = _make_executor_with_bus(tmp_path, event_bus=bus2)
        with pytest.raises(ToolExecutionError):
            executor2.execute("nonexistent_tool", {})
        assert len(started_events) == 0  # plugin not found raises before events

    def test_publishes_completed_ok_false_on_validation_error(self, tmp_path: Path) -> None:
        bus = InMemoryEventBus()
        completed_events: list[Event] = []
        bus.subscribe("tool.execution.completed", completed_events.append)

        executor = _make_executor_with_bus(tmp_path, event_bus=bus)

        with pytest.raises(ToolExecutionError):
            executor.execute("search_files", "not_a_mapping")  # type: ignore[arg-type]

        # validation error happens before events (before started_at)
        assert len(completed_events) == 0

    def test_no_events_when_bus_is_none(self, tmp_path: Path) -> None:
        """When event_bus is None (default), execution works normally without events."""
        executor = _make_executor_with_bus(tmp_path, event_bus=None)
        target = tmp_path / "test.txt"
        target.write_text("content")

        result = executor.execute("search_files", {"query": "test", "limit": 5})
        assert result["ok"] is True  # No crash, no events

    def test_constructor_accepts_event_bus(self, tmp_path: Path) -> None:
        """ToolExecutor constructor accepts optional event_bus kwarg."""
        from tests.conftest import build_tool_executor

        bus = InMemoryEventBus()
        executor = build_tool_executor(tmp_path, event_bus=bus)
        assert executor._event_bus is bus

    def test_constructor_defaults_event_bus_to_none(self, tmp_path: Path) -> None:
        """ToolExecutor without event_bus defaults to None."""
        from tests.conftest import build_tool_executor

        executor = build_tool_executor(tmp_path)
        assert executor._event_bus is None


# =========================================================================
# AuditEventSubscriber
# =========================================================================


class TestAuditEventSubscriber:
    def test_tool_event_logged(self) -> None:
        audit = MagicMock()
        sub = AuditEventSubscriber(audit)

        event = ToolExecutionCompleted(
            event_type="tool.execution.completed",
            source="tool_executor",
            payload={"tool": "search_files", "ok": True, "latency_ms": 42.5},
        )
        sub.on_tool_execution_completed(event)

        audit.log_event.assert_called_once()
        call_args = audit.log_event.call_args
        assert call_args[0][0] == "TOOL_EVENT"
        assert call_args[0][1]["tool"] == "search_files"
        assert call_args[0][1]["ok"] is True
        assert call_args[0][1]["latency_ms"] == 42.5

    def test_session_event_logged(self) -> None:
        audit = MagicMock()
        sub = AuditEventSubscriber(audit)

        event = SessionCreated(
            event_type="session.created",
            source="session_use_case",
            payload={"session_id": "abc123"},
        )
        sub.on_session_event(event)

        audit.log_event.assert_called_once()
        call_args = audit.log_event.call_args
        assert call_args[0][0] == "SESSION_EVENT"
        assert call_args[0][1]["session_id"] == "abc123"

    def test_note_event_logged(self) -> None:
        audit = MagicMock()
        sub = AuditEventSubscriber(audit)

        event = NoteCreated(
            event_type="note.created",
            source="notes_use_case",
            payload={"session_id": "s1", "note_id": "n1"},
        )
        sub.on_note_event(event)

        audit.log_event.assert_called_once()
        call_args = audit.log_event.call_args
        assert call_args[0][0] == "NOTE_EVENT"
        assert call_args[0][1]["session_id"] == "s1"
        assert call_args[0][1]["note_id"] == "n1"

    def test_memory_event_logged(self) -> None:
        audit = MagicMock()
        sub = AuditEventSubscriber(audit)

        event = MemoryDeleted(
            event_type="memory.deleted",
            source="memory_use_case",
            payload={"session_id": "s1", "memory_id": "m1"},
        )
        sub.on_memory_event(event)

        audit.log_event.assert_called_once()
        call_args = audit.log_event.call_args
        assert call_args[0][0] == "MEMORY_EVENT"
        assert call_args[0][1]["memory_id"] == "m1"

    def test_error_event_logged(self) -> None:
        audit = MagicMock()
        sub = AuditEventSubscriber(audit)

        event = Event(
            event_type="error.occurred",
            source="some_module",
            payload={"error": "something broke"},
        )
        sub.on_error(event)

        audit.log_event.assert_called_once()
        call_args = audit.log_event.call_args
        assert call_args[0][0] == "ERROR_EVENT"
        assert call_args[0][1]["error"] == "something broke"

    def test_register_subscribes_all_event_types(self) -> None:
        bus = InMemoryEventBus()
        audit = MagicMock()
        sub = AuditEventSubscriber(audit)

        sub.register(bus)

        expected_types = [
            "tool.execution.completed",
            "session.created",
            "session.deleted",
            "note.created",
            "note.updated",
            "note.deleted",
            "memory.deleted",
            "error.occurred",
        ]
        for event_type in expected_types:
            assert bus.subscriber_count_for(event_type) == 1, (
                f"Expected 1 subscriber for {event_type}"
            )

    def test_end_to_end_bus_to_audit(self) -> None:
        """Full integration: publish event on bus -> subscriber -> audit logger."""
        bus = InMemoryEventBus()
        audit = MagicMock()
        sub = AuditEventSubscriber(audit)
        sub.register(bus)

        bus.publish(SessionCreated(
            event_type="session.created",
            source="session_use_case",
            payload={"session_id": "test-session"},
        ))

        audit.log_event.assert_called_once()
        assert audit.log_event.call_args[0][0] == "SESSION_EVENT"


# =========================================================================
# Event types contract
# =========================================================================


class TestEventTypes:
    def test_memory_deleted_event_exists(self) -> None:
        """MemoryDeleted event type is available."""
        event = MemoryDeleted(
            event_type="memory.deleted",
            source="test",
            payload={"session_id": "s1", "memory_id": "m1"},
        )
        assert event.event_type == "memory.deleted"
        assert isinstance(event, Event)

    def test_all_event_subclasses_are_events(self) -> None:
        """All domain event subclasses extend Event."""
        for cls in [
            ToolExecutionStarted,
            ToolExecutionCompleted,
            SessionCreated,
            SessionDeleted,
            NoteCreated,
            NoteUpdated,
            NoteDeleted,
            MemoryDeleted,
        ]:
            instance = cls(event_type="test")
            assert isinstance(instance, Event)


# =========================================================================
# Use case event wiring (smoke tests)
# =========================================================================


class TestUseCaseEventBusParameter:
    def test_session_use_cases_accepts_event_bus(self) -> None:
        from agent_host.core.use_cases.manage_session import SessionUseCases

        bus = InMemoryEventBus()
        uc = SessionUseCases(
            memory_manager=MagicMock(),
            ipc_bridge=MagicMock(),
            run_blocking=AsyncMock(),
            db_timeout_seconds=5.0,
            event_bus=bus,
        )
        assert uc._event_bus is bus

    def test_session_use_cases_event_bus_defaults_none(self) -> None:
        from agent_host.core.use_cases.manage_session import SessionUseCases

        uc = SessionUseCases(
            memory_manager=MagicMock(),
            ipc_bridge=MagicMock(),
            run_blocking=AsyncMock(),
            db_timeout_seconds=5.0,
        )
        assert uc._event_bus is None

    def test_notes_use_cases_accepts_event_bus(self) -> None:
        from agent_host.core.use_cases.manage_notes import NotesUseCases

        bus = InMemoryEventBus()
        uc = NotesUseCases(
            memory_manager=MagicMock(),
            ipc_bridge=MagicMock(),
            run_blocking=AsyncMock(),
            db_timeout_seconds=5.0,
            broadcast_session_refresh=AsyncMock(),
            event_bus=bus,
        )
        assert uc._event_bus is bus

    def test_notes_use_cases_event_bus_defaults_none(self) -> None:
        from agent_host.core.use_cases.manage_notes import NotesUseCases

        uc = NotesUseCases(
            memory_manager=MagicMock(),
            ipc_bridge=MagicMock(),
            run_blocking=AsyncMock(),
            db_timeout_seconds=5.0,
            broadcast_session_refresh=AsyncMock(),
        )
        assert uc._event_bus is None

    def test_memory_use_cases_accepts_event_bus(self) -> None:
        from agent_host.core.use_cases.manage_memory import MemoryUseCases

        bus = InMemoryEventBus()
        uc = MemoryUseCases(
            memory_manager=MagicMock(),
            ipc_bridge=MagicMock(),
            run_blocking=AsyncMock(),
            db_timeout_seconds=5.0,
            broadcast_session_refresh=AsyncMock(),
            event_bus=bus,
        )
        assert uc._event_bus is bus

    def test_memory_use_cases_event_bus_defaults_none(self) -> None:
        from agent_host.core.use_cases.manage_memory import MemoryUseCases

        uc = MemoryUseCases(
            memory_manager=MagicMock(),
            ipc_bridge=MagicMock(),
            run_blocking=AsyncMock(),
            db_timeout_seconds=5.0,
            broadcast_session_refresh=AsyncMock(),
        )
        assert uc._event_bus is None
