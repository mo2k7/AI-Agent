"""Tests for adapter wrappers verifying protocol conformance.

Each adapter must satisfy its corresponding port Protocol via
``isinstance()`` (runtime_checkable) and correctly delegate all
method calls to the underlying concrete implementation.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from agent_host.contracts.ports import (
    AuditPort,
    EventBus,
    IPCPort,
    LLMProvider,
    MemoryPort,
    NLPClassifierPort,
)
from agent_host.adapters.llm.gemini_adapter import GeminiAdapter
from agent_host.adapters.storage.memory_adapter import MemoryAdapter
from agent_host.adapters.audit.audit_adapter import AuditAdapter
from agent_host.adapters.nlp.spacy_adapter import SpacyNLPAdapter
from agent_host.adapters.ipc.websocket_adapter import WebSocketAdapter
from agent_host.adapters.event_bus.in_memory_bus import InMemoryEventBus


# =========================================================================
# GeminiAdapter → LLMProvider
# =========================================================================


class TestGeminiAdapter:
    def _make(self) -> tuple[GeminiAdapter, MagicMock]:
        mock = MagicMock()
        mock.model_name = "gemini-test"
        return GeminiAdapter(mock), mock

    def test_satisfies_protocol(self):
        adapter, _ = self._make()
        assert isinstance(adapter, LLMProvider)

    def test_send_prompt_with_tools_delegates(self):
        adapter, mock = self._make()
        mock.send_prompt_with_tools.return_value = {"text": "hello"}
        result = adapter.send_prompt_with_tools(
            "test prompt", [{"name": "tool"}],
            system_instruction="sys", model="gemini-2.5-flash",
        )
        assert result == {"text": "hello"}
        mock.send_prompt_with_tools.assert_called_once_with(
            "test prompt", [{"name": "tool"}],
            system_instruction="sys", model="gemini-2.5-flash",
            temperature=None, max_output_tokens=None, thinking_config=None,
        )

    def test_send_continuation_delegates(self):
        adapter, mock = self._make()
        mock.send_continuation.return_value = {"text": "cont"}
        result = adapter.send_continuation(
            [{"role": "user"}], [{"name": "tool"}],
            model="gemini-2.5-pro",
        )
        assert result == {"text": "cont"}
        mock.send_continuation.assert_called_once()

    def test_resolve_text_model_delegates(self):
        adapter, mock = self._make()
        mock.resolve_text_model.return_value = "gemini-2.5-flash"
        assert adapter.resolve_text_model("override") == "gemini-2.5-flash"
        mock.resolve_text_model.assert_called_once_with("override")

    def test_list_models_delegates(self):
        adapter, mock = self._make()
        mock.list_models.return_value = [{"name": "m1"}]
        result = adapter.list_models(filter_action="generateContent")
        assert result == [{"name": "m1"}]
        mock.list_models.assert_called_once_with(filter_action="generateContent")

    def test_resolve_image_model_delegates(self):
        adapter, mock = self._make()
        mock.resolve_image_model.return_value = "imagen-3"
        assert adapter.resolve_image_model(quality_tier="hd") == "imagen-3"

    def test_generate_image_delegates(self):
        adapter, mock = self._make()
        mock.generate_image.return_value = [{"data": b"img"}]
        result = adapter.generate_image(prompt="cat", num_images=2)
        assert len(result) == 1
        mock.generate_image.assert_called_once()

    def test_model_name_property(self):
        adapter, _ = self._make()
        assert adapter.model_name == "gemini-test"


# =========================================================================
# MemoryAdapter → MemoryPort
# =========================================================================


class TestMemoryAdapter:
    def _make(self) -> tuple[MemoryAdapter, MagicMock]:
        mock = MagicMock()
        return MemoryAdapter(mock), mock

    def test_satisfies_protocol(self):
        adapter, _ = self._make()
        assert isinstance(adapter, MemoryPort)

    def test_create_session_delegates(self):
        adapter, mock = self._make()
        mock.create_session.return_value = "session-1"
        result = adapter.create_session(title="Test", memory_mode="on")
        assert result == "session-1"
        mock.create_session.assert_called_once_with(title="Test", memory_mode="on")

    def test_get_session_delegates(self):
        adapter, mock = self._make()
        mock.get_session.return_value = None
        assert adapter.get_session("s1") is None
        mock.get_session.assert_called_once_with("s1")

    def test_list_sessions_delegates(self):
        adapter, mock = self._make()
        mock.list_sessions.return_value = []
        assert adapter.list_sessions(limit=10) == []
        mock.list_sessions.assert_called_once_with(limit=10)

    def test_prepare_prompt_context_delegates(self):
        adapter, mock = self._make()
        adapter.prepare_prompt_context(
            session_id="s1", prompt="hello", memory_mode="on", verbosity_level=2,
        )
        mock.prepare_prompt_context.assert_called_once_with(
            session_id="s1", prompt="hello", memory_mode="on", verbosity_level=2,
        )

    def test_record_interaction_delegates(self):
        adapter, mock = self._make()
        adapter.record_interaction(
            session_id="s1", memory_mode="on",
            user_prompt="hi", assistant_response="hello", model_name="test",
        )
        mock.record_interaction.assert_called_once()

    def test_create_note_delegates(self):
        adapter, mock = self._make()
        mock.create_note.return_value = {"note_id": "n1"}
        result = adapter.create_note("s1", content="note text", source="user")
        assert result == {"note_id": "n1"}

    def test_update_note_delegates(self):
        adapter, mock = self._make()
        adapter.update_note("s1", "n1", content="updated")
        mock.update_note.assert_called_once()

    def test_delete_note_delegates(self):
        adapter, mock = self._make()
        mock.delete_note.return_value = True
        assert adapter.delete_note("s1", "n1") is True


# =========================================================================
# AuditAdapter → AuditPort
# =========================================================================


class TestAuditAdapter:
    def _make(self) -> tuple[AuditAdapter, MagicMock]:
        mock = MagicMock()
        return AuditAdapter(mock), mock

    def test_satisfies_protocol(self):
        adapter, _ = self._make()
        assert isinstance(adapter, AuditPort)

    def test_log_event_delegates(self):
        adapter, mock = self._make()
        adapter.log_event("TOOL_CALL", {"tool": "search_files"})
        mock.log_event.assert_called_once_with("TOOL_CALL", {"tool": "search_files"})

    def test_log_error_delegates(self):
        adapter, mock = self._make()
        adapter.log_error("timeout", "request timed out", {"request_id": "r1"})
        mock.log_error.assert_called_once_with("timeout", "request timed out", {"request_id": "r1"})


# =========================================================================
# SpacyNLPAdapter → NLPClassifierPort
# =========================================================================


class TestSpacyNLPAdapter:
    def _make(self) -> tuple[SpacyNLPAdapter, MagicMock]:
        mock = MagicMock()
        return SpacyNLPAdapter(mock), mock

    def test_satisfies_protocol(self):
        adapter, _ = self._make()
        assert isinstance(adapter, NLPClassifierPort)

    def test_classify_delegates(self):
        adapter, mock = self._make()
        mock.classify.return_value = {"is_clarification_reply": True, "confidence": 0.9}
        result = adapter.classify(
            reply_prompt="yes", root_prompt="do X",
            pending_dimension="goal", question_count=1,
        )
        assert result["confidence"] == 0.9
        mock.classify.assert_called_once_with(
            reply_prompt="yes", root_prompt="do X",
            pending_dimension="goal", question_count=1,
        )


# =========================================================================
# WebSocketAdapter → IPCPort
# =========================================================================


class TestWebSocketAdapter:
    def _make(self) -> tuple[WebSocketAdapter, MagicMock]:
        mock = MagicMock()
        mock.register_handler = MagicMock()
        mock.broadcast = AsyncMock()
        mock.start = AsyncMock()
        mock.stop = AsyncMock()
        return WebSocketAdapter(mock), mock

    def test_satisfies_protocol(self):
        adapter, _ = self._make()
        assert isinstance(adapter, IPCPort)

    def test_register_handler_delegates(self):
        adapter, mock = self._make()
        handler = AsyncMock()
        adapter.register_handler("prompt", handler)
        mock.register_handler.assert_called_once_with("prompt", handler)

    @pytest.mark.anyio
    async def test_broadcast_delegates(self):
        adapter, mock = self._make()
        await adapter.broadcast(b"test message")
        mock.broadcast.assert_awaited_once_with(b"test message")

    @pytest.mark.anyio
    async def test_start_delegates(self):
        adapter, mock = self._make()
        await adapter.start()
        mock.start.assert_awaited_once()

    @pytest.mark.anyio
    async def test_stop_delegates(self):
        adapter, mock = self._make()
        await adapter.stop()
        mock.stop.assert_awaited_once()


# =========================================================================
# InMemoryEventBus → EventBus (already tested in test_event_bus.py,
# but verify protocol here for completeness)
# =========================================================================


class TestEventBusProtocol:
    def test_satisfies_protocol(self):
        bus = InMemoryEventBus()
        assert isinstance(bus, EventBus)
