"""Tests verifying error boundaries at adapter seams.

Ensures that:
- Domain exceptions pass through unchanged (callers depend on them)
- Unknown/unexpected exceptions are wrapped in AdapterError
- No raw framework exceptions leak to callers
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_host.contracts.types.errors import AdapterError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock(**method_overrides: Exception) -> MagicMock:
    """Create a MagicMock whose specified methods raise the given exceptions."""
    mock = MagicMock()
    for method_name, exc in method_overrides.items():
        getattr(mock, method_name).side_effect = exc
    return mock


def _make_async_mock(**method_overrides: Exception) -> MagicMock:
    """Create a MagicMock whose specified async methods raise the given exceptions."""
    mock = MagicMock()
    for method_name, exc in method_overrides.items():
        setattr(mock, method_name, AsyncMock(side_effect=exc))
    return mock


# ===================================================================
# GeminiAdapter
# ===================================================================

class TestGeminiAdapterBoundary:
    """Error boundaries for GeminiAdapter."""

    @pytest.fixture()
    def _import_deps(self):
        from agent_host.adapters.llm.gemini_adapter import GeminiAdapter
        from agent_host.gemini_client import (
            GeminiAPIError,
            GeminiClientError,
            GeminiRateLimitError,
            GeminiServerError,
        )
        return GeminiAdapter, GeminiAPIError, GeminiClientError, GeminiRateLimitError, GeminiServerError

    # --- Domain exceptions pass through ---

    def test_gemini_api_error_passes_through(self, _import_deps):
        GeminiAdapter, GeminiAPIError, *_ = _import_deps
        mock = _make_mock(send_prompt_with_tools=GeminiAPIError("bad request", 400))
        adapter = GeminiAdapter(mock)
        with pytest.raises(GeminiAPIError, match="bad request"):
            adapter.send_prompt_with_tools("hi", [])

    def test_gemini_rate_limit_error_passes_through(self, _import_deps):
        GeminiAdapter, _, _, GeminiRateLimitError, _ = _import_deps
        mock = _make_mock(send_continuation=GeminiRateLimitError("rate limited", 429))
        adapter = GeminiAdapter(mock)
        with pytest.raises(GeminiRateLimitError):
            adapter.send_continuation([], [])

    def test_gemini_server_error_passes_through(self, _import_deps):
        GeminiAdapter, _, _, _, GeminiServerError = _import_deps
        mock = _make_mock(list_models=GeminiServerError("server down", 500))
        adapter = GeminiAdapter(mock)
        with pytest.raises(GeminiServerError):
            adapter.list_models()

    def test_gemini_client_error_passes_through(self, _import_deps):
        GeminiAdapter, _, GeminiClientError, *_ = _import_deps
        mock = _make_mock(resolve_text_model=GeminiClientError("config error"))
        adapter = GeminiAdapter(mock)
        with pytest.raises(GeminiClientError):
            adapter.resolve_text_model()

    # --- Unknown exceptions wrapped ---

    def test_unknown_exception_wrapped_send_prompt(self, _import_deps):
        GeminiAdapter, *_ = _import_deps
        original = RuntimeError("segfault in native lib")
        mock = _make_mock(send_prompt_with_tools=original)
        adapter = GeminiAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            adapter.send_prompt_with_tools("hi", [])
        assert exc_info.value.source == "gemini"
        assert exc_info.value.cause is original
        assert "send_prompt_with_tools" in str(exc_info.value)

    def test_unknown_exception_wrapped_send_continuation(self, _import_deps):
        GeminiAdapter, *_ = _import_deps
        original = TypeError("bad type")
        mock = _make_mock(send_continuation=original)
        adapter = GeminiAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            adapter.send_continuation([], [])
        assert exc_info.value.cause is original

    def test_unknown_exception_wrapped_resolve_text_model(self, _import_deps):
        GeminiAdapter, *_ = _import_deps
        mock = _make_mock(resolve_text_model=KeyError("missing"))
        adapter = GeminiAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.resolve_text_model()

    def test_unknown_exception_wrapped_list_models(self, _import_deps):
        GeminiAdapter, *_ = _import_deps
        mock = _make_mock(list_models=IOError("network gone"))
        adapter = GeminiAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.list_models()

    def test_unknown_exception_wrapped_resolve_image_model(self, _import_deps):
        GeminiAdapter, *_ = _import_deps
        mock = _make_mock(resolve_image_model=AttributeError("oops"))
        adapter = GeminiAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.resolve_image_model()

    def test_unknown_exception_wrapped_generate_image(self, _import_deps):
        GeminiAdapter, *_ = _import_deps
        mock = _make_mock(generate_image=MemoryError("oom"))
        adapter = GeminiAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.generate_image(prompt="a cat")

    # --- Cause preserved ---

    def test_adapter_error_preserves_cause(self, _import_deps):
        GeminiAdapter, *_ = _import_deps
        original = RuntimeError("underlying boom")
        mock = _make_mock(generate_image=original)
        adapter = GeminiAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            adapter.generate_image(prompt="test")
        assert exc_info.value.cause is original
        assert exc_info.value.__cause__ is original  # PEP 3134 chain

    # --- model_name property has no boundary (simple attribute) ---

    def test_model_name_no_boundary(self, _import_deps):
        GeminiAdapter, *_ = _import_deps
        mock = MagicMock()
        mock.model_name = "gemini-2.5-flash"
        adapter = GeminiAdapter(mock)
        assert adapter.model_name == "gemini-2.5-flash"


# ===================================================================
# MemoryAdapter
# ===================================================================

class TestMemoryAdapterBoundary:
    """Error boundaries for MemoryAdapter."""

    @pytest.fixture()
    def _import_deps(self):
        from agent_host.adapters.storage.memory_adapter import MemoryAdapter
        from agent_host.memory.store import MemoryStoreError
        return MemoryAdapter, MemoryStoreError

    # --- Domain exceptions pass through ---

    def test_memory_store_error_passes_through(self, _import_deps):
        MemoryAdapter, MemoryStoreError = _import_deps
        mock = _make_mock(get_session=MemoryStoreError("corrupt db"))
        adapter = MemoryAdapter(mock)
        with pytest.raises(MemoryStoreError, match="corrupt db"):
            adapter.get_session("sess-1")

    def test_value_error_passes_through(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        mock = _make_mock(create_session=ValueError("bad title"))
        adapter = MemoryAdapter(mock)
        with pytest.raises(ValueError, match="bad title"):
            adapter.create_session(title="")

    # --- Unknown exceptions wrapped ---

    def test_unknown_exception_wrapped_create_session(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        original = RuntimeError("disk full")
        mock = _make_mock(create_session=original)
        adapter = MemoryAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            adapter.create_session()
        assert exc_info.value.source == "memory"
        assert exc_info.value.cause is original

    def test_unknown_exception_wrapped_get_session(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        mock = _make_mock(get_session=PermissionError("access denied"))
        adapter = MemoryAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.get_session("s1")

    def test_unknown_exception_wrapped_ensure_session(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        mock = _make_mock(ensure_session=TypeError("bad arg"))
        adapter = MemoryAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.ensure_session("s1", memory_mode="full")

    def test_unknown_exception_wrapped_list_sessions(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        mock = _make_mock(list_sessions=RuntimeError("timeout"))
        adapter = MemoryAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.list_sessions()

    def test_unknown_exception_wrapped_list_sessions_since(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        mock = _make_mock(list_sessions_since=RuntimeError("fail"))
        adapter = MemoryAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.list_sessions_since(0)

    def test_unknown_exception_wrapped_prepare_prompt_context(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        mock = _make_mock(prepare_prompt_context=RuntimeError("boom"))
        adapter = MemoryAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.prepare_prompt_context(
                session_id="s1", prompt="hi", memory_mode="full"
            )

    def test_unknown_exception_wrapped_record_interaction(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        mock = _make_mock(record_interaction=OSError("disk"))
        adapter = MemoryAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.record_interaction(
                session_id="s1",
                memory_mode="full",
                user_prompt="hi",
                assistant_response="hello",
                model_name="gemini",
            )

    def test_unknown_exception_wrapped_create_note(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        mock = _make_mock(create_note=RuntimeError("fail"))
        adapter = MemoryAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.create_note("s1", content="note text")

    def test_unknown_exception_wrapped_update_note(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        mock = _make_mock(update_note=RuntimeError("fail"))
        adapter = MemoryAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.update_note("s1", "n1", content="updated")

    def test_unknown_exception_wrapped_delete_note(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        mock = _make_mock(delete_note=RuntimeError("fail"))
        adapter = MemoryAdapter(mock)
        with pytest.raises(AdapterError):
            adapter.delete_note("s1", "n1")

    # --- Cause preserved ---

    def test_adapter_error_preserves_cause(self, _import_deps):
        MemoryAdapter, _ = _import_deps
        original = RuntimeError("the root cause")
        mock = _make_mock(delete_note=original)
        adapter = MemoryAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            adapter.delete_note("s1", "n1")
        assert exc_info.value.cause is original
        assert exc_info.value.__cause__ is original


# ===================================================================
# AuditAdapter
# ===================================================================

class TestAuditAdapterBoundary:
    """Error boundaries for AuditAdapter."""

    @pytest.fixture()
    def _import_deps(self):
        from agent_host.adapters.audit.audit_adapter import AuditAdapter
        from agent_host.audit_logger import AuditLogError
        return AuditAdapter, AuditLogError

    # --- Domain exceptions pass through ---

    def test_audit_log_error_passes_through(self, _import_deps):
        AuditAdapter, AuditLogError = _import_deps
        mock = _make_mock(log_event=AuditLogError("write failed"))
        adapter = AuditAdapter(mock)
        with pytest.raises(AuditLogError, match="write failed"):
            adapter.log_event("tool_call", {"tool": "search"})

    def test_audit_log_error_passes_through_log_error(self, _import_deps):
        AuditAdapter, AuditLogError = _import_deps
        mock = _make_mock(log_error=AuditLogError("permission denied"))
        adapter = AuditAdapter(mock)
        with pytest.raises(AuditLogError):
            adapter.log_error("crash", "bad thing happened")

    # --- Unknown exceptions wrapped ---

    def test_unknown_exception_wrapped_log_event(self, _import_deps):
        AuditAdapter, _ = _import_deps
        original = RuntimeError("disk full")
        mock = _make_mock(log_event=original)
        adapter = AuditAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            adapter.log_event("test", {})
        assert exc_info.value.source == "audit"
        assert exc_info.value.cause is original

    def test_unknown_exception_wrapped_log_error(self, _import_deps):
        AuditAdapter, _ = _import_deps
        original = IOError("flush failed")
        mock = _make_mock(log_error=original)
        adapter = AuditAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            adapter.log_error("err", "msg")
        assert exc_info.value.cause is original

    # --- Cause preserved ---

    def test_adapter_error_preserves_cause(self, _import_deps):
        AuditAdapter, _ = _import_deps
        original = RuntimeError("root")
        mock = _make_mock(log_event=original)
        adapter = AuditAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            adapter.log_event("ev", {})
        assert exc_info.value.cause is original
        assert exc_info.value.__cause__ is original


# ===================================================================
# SpacyNLPAdapter
# ===================================================================

class TestSpacyNLPAdapterBoundary:
    """Error boundaries for SpacyNLPAdapter."""

    @pytest.fixture()
    def _import_deps(self):
        from agent_host.adapters.nlp.spacy_adapter import SpacyNLPAdapter
        return SpacyNLPAdapter

    def _call_classify(self, adapter):
        return adapter.classify(
            reply_prompt="yes",
            root_prompt="plan something",
            pending_dimension="goal",
            question_count=1,
        )

    # --- No domain exceptions for spaCy — everything wraps ---

    def test_any_exception_wrapped_in_adapter_error(self, _import_deps):
        SpacyNLPAdapter = _import_deps
        original = RuntimeError("spacy model not loaded")
        mock = _make_mock(classify=original)
        adapter = SpacyNLPAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            self._call_classify(adapter)
        assert exc_info.value.source == "spacy_nlp"
        assert exc_info.value.cause is original

    def test_value_error_wrapped(self, _import_deps):
        SpacyNLPAdapter = _import_deps
        mock = _make_mock(classify=ValueError("bad input"))
        adapter = SpacyNLPAdapter(mock)
        with pytest.raises(AdapterError):
            self._call_classify(adapter)

    def test_os_error_wrapped(self, _import_deps):
        SpacyNLPAdapter = _import_deps
        mock = _make_mock(classify=OSError("model file missing"))
        adapter = SpacyNLPAdapter(mock)
        with pytest.raises(AdapterError):
            self._call_classify(adapter)

    # --- Cause preserved ---

    def test_adapter_error_preserves_cause(self, _import_deps):
        SpacyNLPAdapter = _import_deps
        original = TypeError("unexpected None")
        mock = _make_mock(classify=original)
        adapter = SpacyNLPAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            self._call_classify(adapter)
        assert exc_info.value.cause is original
        assert exc_info.value.__cause__ is original


# ===================================================================
# WebSocketAdapter
# ===================================================================

class TestWebSocketAdapterBoundary:
    """Error boundaries for WebSocketAdapter."""

    @pytest.fixture()
    def _import_deps(self):
        from agent_host.adapters.ipc.websocket_adapter import WebSocketAdapter
        return WebSocketAdapter

    # --- Domain exceptions pass through ---

    def test_connection_error_passes_through_register(self, _import_deps):
        WebSocketAdapter = _import_deps
        mock = _make_mock(register_handler=ConnectionError("refused"))
        adapter = WebSocketAdapter(mock)
        with pytest.raises(ConnectionError):
            adapter.register_handler("test.method", AsyncMock())

    @pytest.mark.anyio
    async def test_connection_error_passes_through_broadcast(self, _import_deps):
        WebSocketAdapter = _import_deps
        mock = _make_async_mock(broadcast=ConnectionError("reset"))
        adapter = WebSocketAdapter(mock)
        with pytest.raises(ConnectionError):
            await adapter.broadcast(b"hello")

    @pytest.mark.anyio
    async def test_os_error_passes_through_start(self, _import_deps):
        WebSocketAdapter = _import_deps
        mock = _make_async_mock(start=OSError("address in use"))
        adapter = WebSocketAdapter(mock)
        with pytest.raises(OSError):
            await adapter.start()

    @pytest.mark.anyio
    async def test_os_error_passes_through_stop(self, _import_deps):
        WebSocketAdapter = _import_deps
        mock = _make_async_mock(stop=OSError("not connected"))
        adapter = WebSocketAdapter(mock)
        with pytest.raises(OSError):
            await adapter.stop()

    # --- Unknown exceptions wrapped ---

    def test_unknown_exception_wrapped_register_handler(self, _import_deps):
        WebSocketAdapter = _import_deps
        original = RuntimeError("unexpected")
        mock = _make_mock(register_handler=original)
        adapter = WebSocketAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            adapter.register_handler("test", AsyncMock())
        assert exc_info.value.source == "websocket"
        assert exc_info.value.cause is original

    @pytest.mark.anyio
    async def test_unknown_exception_wrapped_broadcast(self, _import_deps):
        WebSocketAdapter = _import_deps
        original = RuntimeError("serialization failed")
        mock = _make_async_mock(broadcast=original)
        adapter = WebSocketAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            await adapter.broadcast(b"data")
        assert exc_info.value.cause is original

    @pytest.mark.anyio
    async def test_unknown_exception_wrapped_start(self, _import_deps):
        WebSocketAdapter = _import_deps
        original = TypeError("bad config")
        mock = _make_async_mock(start=original)
        adapter = WebSocketAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            await adapter.start()
        assert exc_info.value.cause is original

    @pytest.mark.anyio
    async def test_unknown_exception_wrapped_stop(self, _import_deps):
        WebSocketAdapter = _import_deps
        original = RuntimeError("shutdown failed")
        mock = _make_async_mock(stop=original)
        adapter = WebSocketAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            await adapter.stop()
        assert exc_info.value.cause is original

    # --- Cause preserved ---

    @pytest.mark.anyio
    async def test_adapter_error_preserves_cause(self, _import_deps):
        WebSocketAdapter = _import_deps
        original = RuntimeError("root cause")
        mock = _make_async_mock(broadcast=original)
        adapter = WebSocketAdapter(mock)
        with pytest.raises(AdapterError) as exc_info:
            await adapter.broadcast(b"msg")
        assert exc_info.value.cause is original
        assert exc_info.value.__cause__ is original
