"""Focused runtime tests for IPC error correlation and cancellation flows."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from agent_host import main as main_module
from agent_host.config import Config
from agent_host.ipc.protocol import ErrorMessage, IncomingRequest
from agent_host.ipc.server import IPCServer
from tests.unit.websocket_test_harness import connect_line_transport, reserve_tcp_port

TEST_IPC_AUTH_TOKEN = "test-ipc-auth-token"


@pytest.fixture
def anyio_backend() -> str:
    """Pin async tests to asyncio since IPC runtime uses asyncio APIs directly."""
    return "asyncio"


@pytest.fixture(autouse=True)
def _stub_plan_mode_nlp_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main_module,
        "_preload_plan_mode_nlp_classifier",
        lambda _logger: "pytest-stub-model",
    )


def _embedding_ready_gemini_client(gemini_client_cls: type) -> type:
    class _EmbeddingReadyGeminiClient(gemini_client_cls):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            if not hasattr(self, "_client"):
                self._client = SimpleNamespace(
                    models=SimpleNamespace(
                        embed_content=lambda **_kwargs: SimpleNamespace(
                            embeddings=[SimpleNamespace(values=[0.1] * 8)]
                        )
                    )
                )
            configured_model = kwargs.get("model_name")
            if not hasattr(self, "model_name"):
                self.model_name = configured_model or "gemini-test"

        def resolve_text_model(self, requested_model: str | None = None) -> str:
            if requested_model:
                return requested_model
            configured = getattr(self, "model_name", None)
            if isinstance(configured, str) and configured.strip():
                return configured
            return "gemini-test"

        def resolve_image_model(
            self,
            requested_model: str | None = None,
            *,
            require_generation: bool = False,
        ) -> str:
            del require_generation
            return self.resolve_text_model(requested_model)

        def send_continuation(self, **kwargs: object) -> dict[str, object]:
            base_impl = getattr(gemini_client_cls, "send_continuation", None)
            if callable(base_impl):
                return base_impl(self, **kwargs)
            prompt_impl = getattr(gemini_client_cls, "send_prompt_with_tools", None)
            if callable(prompt_impl):
                return prompt_impl(self, **kwargs)
            return {"text": ""}

    return _EmbeddingReadyGeminiClient


def test_live_web_audit_instruction_requires_browse_or_ready_prefix() -> None:
    instruction = main_module._build_live_web_audit_instruction(
        root_prompt="What are the newest model rankings right now?",
        draft_response="Based on early 2025, model X leads.",
    )

    assert "browse_web" in instruction
    assert main_module._FINAL_ANSWER_READY_PREFIX in instruction
    assert "Do not describe this audit step to the user." in instruction


class _DummyClient:
    """Minimal client stub for directly testing IPCServer message handling."""

    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(json.loads(data.decode("utf-8")))


@pytest.mark.anyio
async def test_handle_message_parse_error_falls_back_to_global_id() -> None:
    """Malformed JSON parse errors should use the global fallback request id."""
    server = IPCServer()
    client = _DummyClient()

    malformed_payload = '{"jsonrpc":"2.0","id":"req-parse-1","method":"prompt",'
    await server._handle_message("client-1", client, malformed_payload)

    assert len(client.sent) == 1
    response = client.sent[0]
    assert response["id"] == "global"
    assert response["type"] == "error"
    assert response["error"]["code"] == ErrorMessage.PARSE_ERROR


@pytest.mark.anyio
async def test_handle_message_invalid_request_rejects_non_string_method() -> None:
    server = IPCServer()
    client = _DummyClient()

    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "req-invalid-method-type",
            "method": {"name": "prompt"},
            "params": {},
        }
    )
    await server._handle_message("client-invalid-method", client, payload)

    assert len(client.sent) == 1
    response = client.sent[0]
    assert response["id"] == "req-invalid-method-type"
    assert response["type"] == "error"
    assert response["error"]["code"] == ErrorMessage.INVALID_REQUEST
    assert "method" in str(response["error"]["message"]).lower()


@pytest.mark.anyio
async def test_handle_message_invalid_request_rejects_non_object_payload() -> None:
    server = IPCServer()
    client = _DummyClient()

    await server._handle_message("client-invalid-shape", client, '["not","an","object"]')

    assert len(client.sent) == 1
    response = client.sent[0]
    assert response["id"] == "global"
    assert response["type"] == "error"
    assert response["error"]["code"] == ErrorMessage.INVALID_REQUEST


@pytest.mark.anyio
async def test_handle_message_internal_error_includes_request_id() -> None:
    """Internal handler failures should return an error mapped to the request id."""
    server = IPCServer()
    client = _DummyClient()

    async def broken_handler(*_args: object) -> None:
        raise RuntimeError("boom")

    server.register_handler("explode", broken_handler)
    message = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "req-internal-1",
            "method": "explode",
            "params": {},
        }
    )

    await server._handle_message("client-2", client, message)

    assert len(client.sent) == 1
    response = client.sent[0]
    assert response["id"] == "req-internal-1"
    assert response["type"] == "error"
    assert response["error"]["code"] == ErrorMessage.INTERNAL_ERROR
    assert "boom" in response["error"]["message"]


@pytest.mark.anyio
async def test_handle_message_internal_error_falls_back_when_exception_is_empty() -> None:
    """Internal handler failures with empty exception text should still be descriptive."""
    server = IPCServer()
    client = _DummyClient()

    async def broken_handler(*_args: object) -> None:
        raise RuntimeError()

    server.register_handler("explode_empty", broken_handler)
    message = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "req-internal-empty-1",
            "method": "explode_empty",
            "params": {},
        }
    )

    await server._handle_message("client-3", client, message)

    assert len(client.sent) == 1
    response = client.sent[0]
    assert response["id"] == "req-internal-empty-1"
    assert response["type"] == "error"
    assert response["error"]["code"] == ErrorMessage.INTERNAL_ERROR
    message_text = response["error"]["message"]
    assert isinstance(message_text, str)
    assert message_text.strip()
    assert "RuntimeError" in message_text


def test_trace_message_write_failure_is_non_fatal(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_AGENT_DEBUG_PROTOCOL_TRACE", "1")
    server = IPCServer()
    # Force write failure: assigning a directory path causes open("a") to fail.
    server._trace_enabled = True
    server._trace_path = tmp_path

    server._trace_message(
        "in",
        "client-trace",
        b'{"jsonrpc":"2.0","id":"req-trace-1","method":"prompt","params":{"correlation_id":"c-1"}}',
    )


def test_build_ssl_context_allows_plain_ws_when_tls_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AI_AGENT_REQUIRE_TLS", raising=False)
    monkeypatch.delenv("AI_AGENT_TLS_CERT", raising=False)
    monkeypatch.delenv("AI_AGENT_TLS_KEY", raising=False)

    server = IPCServer()

    assert server._build_ssl_context() is None


def test_build_ssl_context_refuses_plain_ws_when_tls_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_AGENT_REQUIRE_TLS", "1")
    monkeypatch.delenv("AI_AGENT_TLS_CERT", raising=False)
    monkeypatch.delenv("AI_AGENT_TLS_KEY", raising=False)

    server = IPCServer()

    with pytest.raises(RuntimeError, match="AI_AGENT_REQUIRE_TLS"):
        server._build_ssl_context()


async def _connect_transport(endpoint_url: str, timeout_seconds: float = 10.0):
    """Connect to the WebSocket endpoint once the server is ready."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        try:
            return await connect_line_transport(endpoint_url)
        except OSError:
            await asyncio.sleep(0.02)
    raise TimeoutError(f"WebSocket endpoint did not become ready in time: {endpoint_url}")


async def _authenticate_socket(
    reader,
    writer,
    *,
    token: str = TEST_IPC_AUTH_TOKEN,
    timeout_seconds: float = 5.0,
) -> None:
    request_id = f"req-auth-{uuid.uuid4().hex[:8]}"
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "auth.hello",
        "params": {
            "protocol_version": "2.0.0",
            "client_name": "pytest",
            "client_pid": 99999,
            "auth_token": token,
        },
    }
    writer.write((json.dumps(payload) + "\n").encode("utf-8"))
    await writer.drain()

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        remaining = deadline - asyncio.get_running_loop().time()
        line = await asyncio.wait_for(reader.readline(), timeout=max(0.05, remaining))
        if not line:
            break
        msg = json.loads(line.decode("utf-8"))
        if msg.get("id") == request_id and msg.get("type") == "result":
            content = msg.get("result", {}).get("content", "{}")
            data = json.loads(content) if isinstance(content, str) else content
            assert data.get("authenticated") is True
            assert data.get("protocol_version") == "2.0.0"
            return
        if msg.get("id") == request_id and msg.get("type") == "error":
            raise AssertionError(f"IPC auth failed: {msg}")
    raise AssertionError("Timed out waiting for auth.hello result")


async def _create_session_via_socket(
    reader,
    writer,
    *,
    timeout_seconds: float = 5.0,
) -> str:
    """Create a session via socket RPC and return the session_id."""
    request_id = f"req-create-session-{uuid.uuid4().hex[:8]}"
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "session.create",
        "params": {"memory_mode": "off"},
    }
    writer.write((json.dumps(payload) + "\n").encode("utf-8"))
    await writer.drain()

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        remaining = deadline - asyncio.get_running_loop().time()
        line = await asyncio.wait_for(reader.readline(), timeout=max(0.05, remaining))
        if not line:
            break
        msg = json.loads(line.decode("utf-8"))
        if msg.get("id") == request_id and msg.get("type") == "result":
            content = msg.get("result", {}).get("content", "{}")
            data = json.loads(content) if isinstance(content, str) else content
            return str(data["session_id"])
    raise AssertionError("Failed to create test session via socket")


@pytest.mark.anyio
async def test_run_server_cancel_cancels_inflight_prompt(monkeypatch) -> None:
    """A targeted cancel request should terminate a running prompt request."""

    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"0" * 32).decode("ascii"),
    )

    class _SlowGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, str]:
            # Simulate a slow SDK call so cancellation arrives mid-request.
            time.sleep(3.0)
            return {"text": "late response"}

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_SlowGeminiClient),
    )

    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            session_id = await _create_session_via_socket(reader, writer)
            prompt_id = "req-prompt-cancel-1"
            cancel_id = "req-cancel-1"

            prompt_request = {
                "jsonrpc": "2.0",
                "id": prompt_id,
                "method": "prompt",
                "params": {"prompt": "long running", "model": "gemini-3-flash-preview", "session_id": session_id},
            }
            writer.write((json.dumps(prompt_request) + "\n").encode("utf-8"))
            await writer.drain()

            # Give prompt handler a short head start so cancellation targets an in-flight task.
            await asyncio.sleep(0.05)

            cancel_request = {
                "jsonrpc": "2.0",
                "id": cancel_id,
                "method": "cancel",
                "params": {"request_id": prompt_id},
            }
            writer.write((json.dumps(cancel_request) + "\n").encode("utf-8"))
            await writer.drain()

            saw_cancel_result = False
            saw_prompt_cancel_error = False
            saw_prompt_complete = False
            saw_prompt_result = False

            deadline = asyncio.get_running_loop().time() + 6.0
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                line = await asyncio.wait_for(reader.readline(), timeout=remaining)
                if not line:
                    break

                message = json.loads(line.decode("utf-8"))
                if message.get("id") == cancel_id and message.get("type") == "result":
                    saw_cancel_result = True

                if message.get("id") == prompt_id and message.get("type") == "error":
                    assert message["error"]["code"] == -32800
                    assert "cancelled" in message["error"]["message"].lower()
                    saw_prompt_cancel_error = True

                if message.get("id") == prompt_id and message.get("type") == "result":
                    saw_prompt_result = True

                if (
                    message.get("id") == prompt_id
                    and message.get("type") == "status"
                    and message.get("status") == "complete"
                ):
                    saw_prompt_complete = True

                if saw_cancel_result and saw_prompt_cancel_error and saw_prompt_complete:
                    break

            assert saw_cancel_result, "Cancel request did not return a result message."
            assert saw_prompt_cancel_error, "Prompt request did not emit cancellation error."
            assert saw_prompt_complete, "Prompt request did not emit terminal complete status."
            assert not saw_prompt_result, "Cancelled prompt emitted an unexpected result message."
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_run_server_cancel_rejects_cross_client_request_id(monkeypatch, tmp_path: Path) -> None:
    """A client must not be able to cancel another client's in-flight request."""

    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"7" * 32).decode("ascii"),
    )

    class _SlowGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, str]:
            time.sleep(1.0)
            return {"text": "finished normally"}

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_SlowGeminiClient),
    )

    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader1, writer1 = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader1, writer1)
        reader2, writer2 = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader2, writer2)
        try:
            session_id = await _create_session_via_socket(reader1, writer1)
            prompt_id = "req-cross-client-prompt-1"
            prompt_request = {
                "jsonrpc": "2.0",
                "id": prompt_id,
                "method": "prompt",
                "params": {"prompt": "do work", "model": "gemini-3-flash-preview", "session_id": session_id},
            }
            writer1.write((json.dumps(prompt_request) + "\n").encode("utf-8"))
            await writer1.drain()
            await asyncio.sleep(0.05)

            cancel_id = "req-cross-client-cancel-1"
            cancel_request = {
                "jsonrpc": "2.0",
                "id": cancel_id,
                "method": "cancel",
                "params": {"request_id": prompt_id},
            }
            writer2.write((json.dumps(cancel_request) + "\n").encode("utf-8"))
            await writer2.drain()

            saw_cancel_denied = False
            saw_cancel_complete = False
            deadline = asyncio.get_running_loop().time() + 4.0
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                line = await asyncio.wait_for(reader2.readline(), timeout=remaining)
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))
                if message.get("id") != cancel_id:
                    continue
                if message.get("type") == "error":
                    assert message.get("error", {}).get("code") == ErrorMessage.INVALID_REQUEST
                    assert "not active for this client" in str(
                        message.get("error", {}).get("message", "")
                    ).lower()
                    saw_cancel_denied = True
                if (
                    message.get("type") == "status"
                    and message.get("status") == "complete"
                ):
                    saw_cancel_complete = True
                if saw_cancel_denied and saw_cancel_complete:
                    break

            assert saw_cancel_denied, "Cross-client cancellation should be rejected."
            assert saw_cancel_complete, "Cross-client cancellation should terminate cancel RPC."

            saw_prompt_result = False
            saw_prompt_complete = False
            saw_prompt_cancel_error = False
            deadline = asyncio.get_running_loop().time() + 6.0
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                line = await asyncio.wait_for(reader1.readline(), timeout=remaining)
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))
                if message.get("id") != prompt_id:
                    continue
                if message.get("type") == "error":
                    text = str(message.get("error", {}).get("message", "")).lower()
                    if "cancel" in text:
                        saw_prompt_cancel_error = True
                if message.get("type") == "result":
                    saw_prompt_result = True
                if (
                    message.get("type") == "status"
                    and message.get("status") == "complete"
                ):
                    saw_prompt_complete = True
                if saw_prompt_result and saw_prompt_complete:
                    break

            assert not saw_prompt_cancel_error, "Prompt should not be cancelled by another client."
            assert saw_prompt_result, "Prompt should finish normally for owning client."
            assert saw_prompt_complete, "Prompt should emit terminal complete status."
        finally:
            writer1.close()
            writer2.close()
            await writer1.wait_closed()
            await writer2.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_run_server_rejects_oversized_unterminated_request_buffer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Oversized newline-free payloads should be rejected to avoid buffer exhaustion."""

    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"8" * 32).decode("ascii"),
    )

    class _NoopGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, str]:
            return {"text": "unused"}

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_NoopGeminiClient),
    )
    import agent_host.ipc.hot_reload as hot_reload_module
    import agent_host.ipc.server as server_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )
    # Keep the cap low enough for the overflow test while allowing auth.hello to fit.
    monkeypatch.setattr(server_module.IPCServer, "MAX_INCOMING_BUFFER", 512)
    monkeypatch.setenv("AI_AGENT_IPC_AUTH_TOKEN", "a")

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer, token="a")
        try:
            writer.write(b"x" * 1024)
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=3.0)
            assert line == b""
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
@pytest.mark.parametrize("prompt_value", [123, ["hello"], "", "   "])
async def test_run_server_rejects_non_string_or_blank_prompt(monkeypatch, prompt_value: object) -> None:
    """Prompt requests must provide a non-empty string prompt."""

    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"2" * 32).decode("ascii"),
    )

    class _NoopGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, str]:
            return {"text": "should not run"}

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_NoopGeminiClient),
    )
    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            request_id = "req-prompt-validate-1"
            prompt_request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "prompt",
                "params": {"prompt": prompt_value, "model": "gemini-3-flash-preview"},
            }
            writer.write((json.dumps(prompt_request) + "\n").encode("utf-8"))
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=3.0)
            assert line
            message = json.loads(line.decode("utf-8"))
            assert message.get("id") == request_id
            assert message.get("type") == "error"
            assert message.get("error", {}).get("code") == ErrorMessage.INVALID_REQUEST
            assert "prompt" in str(message.get("error", {}).get("message", "")).lower()
            assert "non-empty string" in str(message.get("error", {}).get("message", "")).lower()
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_prompt_disconnect_mid_request_suppresses_post_disconnect_emissions(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """After client disconnect, prompt flow should avoid late result/status sends."""

    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"3" * 32).decode("ascii"),
    )

    class _FastGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, str]:
            return {"text": "ok"}

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    class _DummyStreamer:
        async def stream_words(self, _text: str) -> None:
            return None

    class _FakeServer:
        latest: "_FakeServer | None" = None

        def __init__(
            self,
            host: str = "127.0.0.1",
            port: int = 8765,
            max_clients: int = 5,
            **_kwargs: object,
        ) -> None:
            self.host = host
            self.port = port
            self.endpoint_url = f"ws://{host}:{port}"
            self.handlers: dict[str, object] = {}
            self._stop_event = asyncio.Event()
            _FakeServer.latest = self

        def register_handler(self, method: str, handler) -> None:
            self.handlers[method] = handler

        def set_disconnect_handler(self, _handler) -> None:
            return None

        def create_streaming_handler(self, _client, _request_id: str) -> _DummyStreamer:
            return _DummyStreamer()

        async def start(self) -> None:
            return None

        async def serve_forever(self) -> None:
            await self._stop_event.wait()

        async def stop(self) -> None:
            return None

        def release(self) -> None:
            self._stop_event.set()

    class _ToggleWriter:
        def __init__(self) -> None:
            self.closed = False

        def is_closing(self) -> bool:
            return self.closed

    class _DisconnectingClient:
        def __init__(self) -> None:
            self.address = "disconnecting-client"
            self.writer = _ToggleWriter()
            self.send_calls = 0
            self.sent: list[dict[str, object]] = []

        async def send(self, data: bytes) -> None:
            self.send_calls += 1
            self.sent.append(json.loads(data.decode("utf-8")))
            if self.send_calls == 1:
                # Simulate disconnect after first lifecycle message.
                self.writer.closed = True

    async def _wait_for_fake_server(timeout_seconds: float = 3.0) -> _FakeServer:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            latest = _FakeServer.latest
            if latest is not None and latest.handlers:
                return latest
            await asyncio.sleep(0.01)
        raise TimeoutError("Fake server did not initialize in time")

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_FastGeminiClient),
    )
    import agent_host.ipc.server as server_module

    monkeypatch.setattr(server_module, "IPCServer", _FakeServer)

    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
    )

    run_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=8765, verbose=False)
    )

    try:
        fake_server = await _wait_for_fake_server()

        # Create a session first (prompt now requires session_id).
        setup_client = _DummyClient()
        setup_client.address = "setup-client"  # type: ignore[attr-defined]
        create_req = IncomingRequest(
            id="req-create-session",
            method="session.create",
            params={"memory_mode": "off"},
        )
        await fake_server.handlers["session.create"](create_req, setup_client)
        created = json.loads(setup_client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created["session_id"])

        client = _DisconnectingClient()
        request = IncomingRequest(
            id="req-disconnect-mid-request",
            method="prompt",
            params={"prompt": "hello", "model": "gemini-3-flash-preview", "session_id": session_id},
        )

        await fake_server.handlers["prompt"](request, client)
        await asyncio.sleep(0.2)

        assert client.send_calls == 1
        assert client.sent[0].get("type") == "status"
        assert client.sent[0].get("status") == "thinking"
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_run_server_executes_tool_call_and_returns_result(monkeypatch, tmp_path: Path) -> None:
    """Validated tool calls should execute and return structured result payloads."""
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"1" * 32).decode("ascii"),
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    target_file = workspace / "python_notes.txt"
    target_file.write_text("hello")

    class _ToolGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {
                "function_call": {
                    "name": "search_files",
                    "args": {"query": "python", "limit": 5},
                }
            }

        def send_continuation(self, **_kwargs: object) -> dict[str, object]:
            return {"text": f"Found 1 matching file: {target_file}"}

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_ToolGeminiClient),
    )
    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
        allowed_roots=[workspace],
        automations_dir=tmp_path / "automations",
        enable_open_item=False,
        search_scan_limit=2000,
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            session_id = await _create_session_via_socket(reader, writer)
            request_id = "req-tool-exec-1"
            prompt_request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "prompt",
                "params": {"prompt": "find python files", "model": "gemini-3-flash-preview", "session_id": session_id},
            }
            writer.write((json.dumps(prompt_request) + "\n").encode("utf-8"))
            await writer.drain()

            saw_tool_success = False
            saw_result_with_output = False
            saw_complete = False

            deadline = asyncio.get_running_loop().time() + 6.0
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                line = await asyncio.wait_for(reader.readline(), timeout=remaining)
                if not line:
                    break

                message = json.loads(line.decode("utf-8"))
                if message.get("id") != request_id:
                    continue
                if message.get("type") == "tool_call":
                    tool = message.get("tool", {})
                    if tool.get("status") == "success":
                        saw_tool_success = True
                if message.get("type") == "result":
                    content = message.get("result", {}).get("content", "")
                    if isinstance(content, str) and "Found" in content and str(target_file) in content:
                        saw_result_with_output = True
                if message.get("type") == "status" and message.get("status") == "complete":
                    saw_complete = True
                if saw_tool_success and saw_result_with_output and saw_complete:
                    break

            assert saw_tool_success, "Expected successful tool_call notification."
            assert saw_result_with_output, "Expected tool execution content in result."
            assert saw_complete, "Expected terminal complete status."
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_run_server_audits_text_only_answer_and_forces_browse_before_finalizing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"b" * 32).decode("ascii"),
    )

    state = {"prompt_calls": 0, "continuation_calls": 0, "browse_calls": 0}

    class _AuditedBrowseGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            state["prompt_calls"] += 1
            return {"text": "Based on the early 2025 landscape, here is the ranking."}

        def send_continuation(self, **_kwargs: object) -> dict[str, object]:
            state["continuation_calls"] += 1
            if state["continuation_calls"] == 1:
                return {
                    "function_call": {
                        "name": "browse_web",
                        "args": {"search_query": "latest llm leaderboard", "timeout_seconds": 3},
                    }
                }
            return {"text": "Live lookup complete with current web sources."}

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_AuditedBrowseGeminiClient),
    )

    import agent_host.ipc.hot_reload as hot_reload_module
    import agent_host.tools.browse_web as browse_web_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    def _fake_browse_handle(_executor, _arguments):
        state["browse_calls"] += 1
        return {
            "ok": True,
            "title": "LLM rankings",
            "content": "Fresh web content",
            "final_url": "https://example.com/leaderboard",
            "effective_browse_profile": "standard",
            "policy_warnings": [],
        }

    monkeypatch.setattr(browse_web_module, "handle", _fake_browse_handle)

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
        automations_dir=tmp_path / "automations",
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            session_id = await _create_session_via_socket(reader, writer)
            request_id = "req-browse-audit-1"
            prompt_request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "prompt",
                "params": {
                    "prompt": "What are the latest LLM rankings right now?",
                    "model": "gemini-3-flash-preview",
                    "session_id": session_id,
                },
            }
            writer.write((json.dumps(prompt_request) + "\n").encode("utf-8"))
            await writer.drain()

            saw_live_web_status = False
            saw_browse_tool = False
            final_result = ""
            saw_complete = False

            deadline = asyncio.get_running_loop().time() + 8.0
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                line = await asyncio.wait_for(reader.readline(), timeout=remaining)
                if not line:
                    break

                message = json.loads(line.decode("utf-8"))
                if message.get("id") != request_id:
                    continue
                if message.get("type") == "status":
                    if message.get("detail") == "Verifying whether live web lookup is needed...":
                        saw_live_web_status = True
                    if message.get("status") == "calling_tool" and message.get("detail") == "browse_web":
                        saw_browse_tool = True
                    if message.get("status") == "complete":
                        saw_complete = True
                if message.get("type") == "result":
                    final_result = str(message.get("result", {}).get("content", ""))
                if saw_live_web_status and saw_browse_tool and final_result and saw_complete:
                    break

            assert saw_live_web_status, "Expected live web audit status before finalizing."
            assert saw_browse_tool, "Expected browse_web to be called after audit."
            assert final_result == "Live lookup complete with current web sources."
            assert "early 2025" not in final_result
            assert state["browse_calls"] == 1
            assert state["continuation_calls"] >= 2
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_run_server_executes_generate_image_tool_and_persists_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"g" * 32).decode("ascii"),
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    output_base = workspace / "generated" / "cat-image"
    expected_file = output_base.with_suffix(".png")
    state: dict[str, int] = {"generate_calls": 0}

    class _GenerateImageGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {
                "function_call": {
                    "name": "generate_image",
                    "args": {
                        "prompt": "A simple sketch of a cat.",
                        "quality_tier": "fast",
                        "number_of_images": 1,
                        "output_path": str(output_base),
                    },
                }
            }

        def send_continuation(self, **_kwargs: object) -> dict[str, object]:
            return {"text": "Image created successfully."}

        def generate_image(self, **kwargs: object) -> dict[str, object]:
            state["generate_calls"] += 1
            assert kwargs.get("prompt") == "A simple sketch of a cat."
            assert kwargs.get("number_of_images") == 1
            return {
                "model": "gemini-2.0-flash-exp-image-generation",
                "images": [
                    {
                        "bytes": b"\x89PNG\r\n\x1a\nfake",
                        "mime_type": "image/png",
                        "width": 0,
                        "height": 0,
                    }
                ],
                "text_responses": [],
            }

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_GenerateImageGeminiClient),
    )
    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
        image_output_root=tmp_path / "generated-images",
        allowed_roots=[workspace],
        automations_dir=tmp_path / "automations",
        enable_open_item=False,
        search_scan_limit=2000,
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            session_id = await _create_session_via_socket(reader, writer)
            request_id = "req-generate-image-success"
            prompt_request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "prompt",
                "params": {
                    "prompt": "Generate a cat sketch image",
                    "model": "gemini-3-flash-preview",
                    "session_id": session_id,
                },
            }
            writer.write((json.dumps(prompt_request) + "\n").encode("utf-8"))
            await writer.drain()

            saw_tool_success = False
            saw_result = False
            saw_complete = False

            deadline = asyncio.get_running_loop().time() + 8.0
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                line = await asyncio.wait_for(reader.readline(), timeout=max(0.05, remaining))
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))
                if message.get("id") != request_id:
                    continue

                if message.get("type") == "tool_call":
                    tool = message.get("tool", {})
                    if (
                        tool.get("name") == "generate_image"
                        and tool.get("status") == "success"
                    ):
                        saw_tool_success = True

                if message.get("type") == "result":
                    content = message.get("result", {}).get("content", "")
                    if isinstance(content, str) and "Image created successfully." in content:
                        saw_result = True

                if message.get("type") == "status" and message.get("status") == "complete":
                    saw_complete = True

                if saw_tool_success and saw_result and saw_complete:
                    break

            assert saw_tool_success, "Expected successful generate_image tool call."
            assert saw_result, "Expected final model response after generate_image execution."
            assert saw_complete, "Expected terminal complete status."
            assert state["generate_calls"] == 1
            assert expected_file.exists()
            assert expected_file.read_bytes() == b"\x89PNG\r\n\x1a\nfake"
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_run_server_generate_image_rejects_invalid_boolean_inputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"h" * 32).decode("ascii"),
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    state: dict[str, int] = {"generate_calls": 0}

    class _InvalidGenerateImageGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {
                "function_call": {
                    "name": "generate_image",
                    "args": {
                        "prompt": "A simple sketch of a cat.",
                        "enhance_prompt": "yes",
                    },
                }
            }

        def send_continuation(self, **_kwargs: object) -> dict[str, object]:
            return {"text": "Handled validation error."}

        def generate_image(self, **_kwargs: object) -> dict[str, object]:
            state["generate_calls"] += 1
            return {"model": "gemini-2.0-flash-exp-image-generation", "images": [], "text_responses": []}

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_InvalidGenerateImageGeminiClient),
    )
    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
        allowed_roots=[workspace],
        automations_dir=tmp_path / "automations",
        enable_open_item=False,
        search_scan_limit=2000,
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            session_id = await _create_session_via_socket(reader, writer)
            request_id = "req-generate-image-invalid"
            prompt_request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "prompt",
                "params": {
                    "prompt": "Generate a cat sketch image",
                    "model": "gemini-3-flash-preview",
                    "session_id": session_id,
                },
            }
            writer.write((json.dumps(prompt_request) + "\n").encode("utf-8"))
            await writer.drain()

            saw_failed_tool_card = False
            saw_complete = False

            deadline = asyncio.get_running_loop().time() + 8.0
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                line = await asyncio.wait_for(reader.readline(), timeout=max(0.05, remaining))
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))
                if message.get("id") != request_id:
                    continue

                if message.get("type") == "tool_call":
                    tool = message.get("tool", {})
                    if (
                        tool.get("name") == "generate_image"
                        and tool.get("status") == "failed"
                        and "validation failed" in str(tool.get("error", "")).lower()
                    ):
                        saw_failed_tool_card = True

                if message.get("type") == "status" and message.get("status") == "complete":
                    saw_complete = True

                if saw_complete:
                    break

            assert saw_failed_tool_card, "Expected failed validation card for generate_image."
            assert saw_complete, "Expected terminal complete status."
            assert state["generate_calls"] == 0
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_apply_ops_tool_waits_for_confirmation_before_execution(monkeypatch, tmp_path: Path) -> None:
    """Destructive apply_ops calls should pause at pending until tool.confirm arrives."""

    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"2" * 32).decode("ascii"),
    )

    class _ApplyOpsGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {
                "function_call": {
                    "name": "apply_ops",
                    "args": {"plan_id": "plan-missing"},
                }
            }

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_ApplyOpsGeminiClient),
    )
    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
        allowed_roots=[tmp_path / "workspace"],
        automations_dir=tmp_path / "automations",
        enable_open_item=False,
        search_scan_limit=2000,
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            session_id = await _create_session_via_socket(reader, writer)
            request_id = "req-confirm-tool-1"
            confirm_id = "req-confirm-tool-ack-1"
            writer.write(
                (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "prompt",
                            "params": {
                                "prompt": "please execute planned operations",
                                "model": "gemini-3-flash-preview",
                                "session_id": session_id,
                            },
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )
            await writer.drain()

            saw_pending = False
            saw_executing_before_confirm = False
            pending_deadline = asyncio.get_running_loop().time() + 4.0
            while asyncio.get_running_loop().time() < pending_deadline:
                line = await asyncio.wait_for(
                    reader.readline(),
                    timeout=max(0.05, pending_deadline - asyncio.get_running_loop().time()),
                )
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))
                if message.get("id") != request_id:
                    continue
                if message.get("type") != "tool_call":
                    continue
                tool = message.get("tool", {})
                if tool.get("status") == "pending":
                    saw_pending = True
                    break
                if tool.get("status") == "executing":
                    saw_executing_before_confirm = True

            assert saw_pending, "Expected pending tool_call before confirmation."
            assert not saw_executing_before_confirm, "Tool started executing before confirmation."

            writer.write(
                (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": confirm_id,
                            "method": "tool.confirm",
                            "params": {"request_id": request_id, "approved": True},
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )
            await writer.drain()

            saw_confirm_ack = False
            saw_executing_after_confirm = False
            saw_terminal = False
            deadline = asyncio.get_running_loop().time() + 6.0
            while asyncio.get_running_loop().time() < deadline:
                line = await asyncio.wait_for(
                    reader.readline(),
                    timeout=max(0.05, deadline - asyncio.get_running_loop().time()),
                )
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))

                if message.get("id") == confirm_id and message.get("type") == "result":
                    saw_confirm_ack = True

                if message.get("id") == request_id and message.get("type") == "tool_call":
                    tool = message.get("tool", {})
                    if tool.get("status") == "executing":
                        saw_executing_after_confirm = True
                if (
                    message.get("id") == request_id
                    and message.get("type") == "status"
                    and message.get("status") == "complete"
                ):
                    saw_terminal = True

                if saw_confirm_ack and saw_executing_after_confirm and saw_terminal:
                    break

            assert saw_confirm_ack, "Expected tool.confirm acknowledgement result."
            assert saw_executing_after_confirm, "Expected tool execution after approval."
            assert saw_terminal, "Expected terminal complete status."
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_apply_ops_tool_denied_confirmation_fails_without_execution(monkeypatch, tmp_path: Path) -> None:
    """Denied confirmations should terminate the request without tool execution."""

    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"3" * 32).decode("ascii"),
    )

    class _ApplyOpsGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {
                "function_call": {
                    "name": "apply_ops",
                    "args": {"plan_id": "plan-missing"},
                }
            }

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_ApplyOpsGeminiClient),
    )
    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
        allowed_roots=[tmp_path / "workspace"],
        automations_dir=tmp_path / "automations",
        enable_open_item=False,
        search_scan_limit=2000,
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            session_id = await _create_session_via_socket(reader, writer)
            request_id = "req-confirm-deny-1"
            confirm_id = "req-confirm-deny-ack-1"
            writer.write(
                (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "prompt",
                            "params": {
                                "prompt": "run dangerous plan",
                                "model": "gemini-3-flash-preview",
                                "session_id": session_id,
                            },
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )
            await writer.drain()

            # Wait for pending tool call first.
            pending_deadline = asyncio.get_running_loop().time() + 4.0
            saw_pending = False
            while asyncio.get_running_loop().time() < pending_deadline:
                line = await asyncio.wait_for(
                    reader.readline(),
                    timeout=max(0.05, pending_deadline - asyncio.get_running_loop().time()),
                )
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))
                if message.get("id") == request_id and message.get("type") == "tool_call":
                    if message.get("tool", {}).get("status") == "pending":
                        saw_pending = True
                        break
            assert saw_pending, "Expected pending apply_ops tool call."

            writer.write(
                (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": confirm_id,
                            "method": "tool.confirm",
                            "params": {"request_id": request_id, "approved": False},
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )
            await writer.drain()

            saw_executing = False
            saw_denied_error = False
            saw_complete = False
            deadline = asyncio.get_running_loop().time() + 6.0
            while asyncio.get_running_loop().time() < deadline:
                line = await asyncio.wait_for(
                    reader.readline(),
                    timeout=max(0.05, deadline - asyncio.get_running_loop().time()),
                )
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))
                if message.get("id") != request_id:
                    continue
                if message.get("type") == "tool_call":
                    if message.get("tool", {}).get("status") == "executing":
                        saw_executing = True
                if message.get("type") == "error":
                    text = str(message.get("error", {}).get("message", "")).lower()
                    if "denied" in text:
                        saw_denied_error = True
                if (
                    message.get("type") == "status"
                    and message.get("status") == "complete"
                ):
                    saw_complete = True
                if saw_denied_error and saw_complete:
                    break

            assert not saw_executing, "Denied confirmation should not execute the tool."
            assert saw_denied_error, "Expected denied error after confirmation denial."
            assert saw_complete, "Expected terminal complete status."
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_plan_ops_chains_to_apply_ops_via_send_continuation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Non-destructive plan_ops should chain into destructive apply_ops in one request."""

    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"4" * 32).decode("ascii"),
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    source_file = workspace / "source.txt"
    destination_file = workspace / "moved.txt"
    source_file.write_text("payload", encoding="utf-8")

    state: dict[str, object] = {"continuation_calls": 0}

    class _ChainedGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {
                "function_call": {
                    "name": "plan_ops",
                    "args": {
                        "ops": [
                            {
                                "op": "move",
                                "src": str(source_file),
                                "dest": str(destination_file),
                            }
                        ]
                    },
                }
            }

        def send_continuation(
            self,
            *,
            contents: list[object],
            **_kwargs: object,
        ) -> dict[str, object]:
            state["continuation_calls"] = int(state["continuation_calls"]) + 1

            plan_id: str | None = None
            for content in reversed(contents):
                parts = getattr(content, "parts", None)
                if not parts:
                    continue
                for part in parts:
                    function_response = getattr(part, "function_response", None)
                    if function_response is None or getattr(function_response, "name", None) != "plan_ops":
                        continue
                    response_payload = getattr(function_response, "response", None)
                    if not isinstance(response_payload, dict):
                        continue
                    output_payload = response_payload.get("output")
                    if isinstance(output_payload, dict):
                        candidate = output_payload.get("plan_id")
                        if isinstance(candidate, str) and candidate.strip():
                            plan_id = candidate
                            break
                if plan_id:
                    break

            assert isinstance(plan_id, str) and plan_id
            return {"function_call": {"name": "apply_ops", "args": {"plan_id": plan_id}}}

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_ChainedGeminiClient),
    )
    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
        allowed_roots=[workspace],
        automations_dir=tmp_path / "automations",
        enable_open_item=False,
        search_scan_limit=2000,
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            session_id = await _create_session_via_socket(reader, writer)
            request_id = "req-chain-plan-apply-1"
            confirm_id = "req-chain-plan-apply-confirm-1"
            writer.write(
                (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "prompt",
                            "params": {
                                "prompt": "move source.txt to moved.txt",
                                "model": "gemini-3-flash-preview",
                                "session_id": session_id,
                            },
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )
            await writer.drain()

            saw_plan_success = False
            saw_apply_pending = False
            saw_apply_executing = False
            saw_apply_success = False
            saw_confirm_ack = False
            saw_result = False
            saw_complete = False
            confirm_sent = False

            deadline = asyncio.get_running_loop().time() + 8.0
            while asyncio.get_running_loop().time() < deadline:
                line = await asyncio.wait_for(
                    reader.readline(),
                    timeout=max(0.05, deadline - asyncio.get_running_loop().time()),
                )
                if not line:
                    break

                message = json.loads(line.decode("utf-8"))
                if message.get("id") == request_id and message.get("type") == "tool_call":
                    tool = message.get("tool", {})
                    name = tool.get("name")
                    status = tool.get("status")
                    if name == "plan_ops" and status == "success":
                        saw_plan_success = True
                    if name == "apply_ops" and status == "pending":
                        saw_apply_pending = True
                        if not confirm_sent:
                            writer.write(
                                (
                                    json.dumps(
                                        {
                                            "jsonrpc": "2.0",
                                            "id": confirm_id,
                                            "method": "tool.confirm",
                                            "params": {"request_id": request_id, "approved": True},
                                        }
                                    )
                                    + "\n"
                                ).encode("utf-8")
                            )
                            await writer.drain()
                            confirm_sent = True
                    if name == "apply_ops" and status == "executing":
                        saw_apply_executing = True
                    if name == "apply_ops" and status == "success":
                        saw_apply_success = True

                if message.get("id") == confirm_id and message.get("type") == "result":
                    saw_confirm_ack = True

                if message.get("id") == request_id and message.get("type") == "result":
                    content = message.get("result", {}).get("content", "")
                    if isinstance(content, str) and "Operations Applied" in content:
                        saw_result = True

                if (
                    message.get("id") == request_id
                    and message.get("type") == "status"
                    and message.get("status") == "complete"
                ):
                    saw_complete = True

                if (
                    saw_plan_success
                    and saw_apply_pending
                    and saw_apply_executing
                    and saw_apply_success
                    and saw_confirm_ack
                    and saw_result
                    and saw_complete
                ):
                    break

            assert saw_plan_success, "Expected plan_ops success before apply_ops."
            assert saw_apply_pending, "Expected apply_ops pending confirmation state."
            assert saw_apply_executing, "Expected apply_ops execution after confirmation."
            assert saw_apply_success, "Expected apply_ops success notification."
            assert saw_confirm_ack, "Expected tool.confirm acknowledgement."
            assert saw_result, "Expected final operations-applied result content."
            assert saw_complete, "Expected terminal complete status."
            assert int(state["continuation_calls"]) >= 1, "Expected send_continuation to be used."
            assert destination_file.exists(), "Expected destination file after chained apply_ops."
            assert not source_file.exists(), "Expected source file moved by chained apply_ops."
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_plan_mode_rejects_apply_ops_without_prior_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Plan mode must reject apply_ops when no plan_ops has run in the same request."""

    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"9" * 32).decode("ascii"),
    )
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_CLARIFICATION_REQUIRED", "0")

    class _DirectApplyGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {"function_call": {"name": "apply_ops", "args": {"plan_id": "plan-missing"}}}

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_DirectApplyGeminiClient),
    )
    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
        allowed_roots=[workspace],
        automations_dir=tmp_path / "automations",
        enable_open_item=False,
        search_scan_limit=2000,
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            session_id = await _create_session_via_socket(reader, writer)
            request_id = "req-plan-mode-reject-1"
            writer.write(
                (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "prompt",
                            "params": {
                                "prompt": "apply operations immediately",
                                "model": "gemini-3-flash-preview",
                                "execution_mode": "plan",
                                "session_id": session_id,
                            },
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )
            await writer.drain()

            saw_error = False
            saw_complete = False
            deadline = asyncio.get_running_loop().time() + 10.0
            while asyncio.get_running_loop().time() < deadline:
                remaining = max(0.05, deadline - asyncio.get_running_loop().time())
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=remaining)
                except TimeoutError:
                    break
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))
                if message.get("id") != request_id:
                    continue
                if message.get("type") == "error":
                    saw_error = "planning-only" in str(
                        message.get("error", {}).get("message", "")
                    ).lower()
                if (
                    message.get("type") == "status"
                    and message.get("status") == "complete"
                ):
                    saw_complete = True
                # Tool call cards are intentionally hidden in Plan Mode
                # (BUG 13), so we only check the error + complete status.
                if saw_error and saw_complete:
                    break

            assert saw_error, "Expected plan-mode enforcement error."
            assert saw_complete, "Expected terminal complete status."
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_plan_mode_rejects_create_directory_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Plan mode should reject non-allowlisted tools, including create_directory."""

    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"a" * 32).decode("ascii"),
    )
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_CLARIFICATION_REQUIRED", "0")

    class _CreateDirectoryGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {
                "function_call": {
                    "name": "create_directory",
                    "args": {"path": "~/tmp_plan_mode_blocked"},
                }
            }

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_CreateDirectoryGeminiClient),
    )
    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
        allowed_roots=[workspace],
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            session_id = await _create_session_via_socket(reader, writer)
            request_id = "req-plan-mode-reject-create-dir-1"
            writer.write(
                (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "prompt",
                            "params": {
                                "prompt": "create a folder now",
                                "model": "gemini-3-flash-preview",
                                "execution_mode": "plan",
                                "session_id": session_id,
                            },
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )
            await writer.drain()

            saw_error = False
            saw_complete = False
            deadline = asyncio.get_running_loop().time() + 10.0
            while asyncio.get_running_loop().time() < deadline:
                remaining = max(0.05, deadline - asyncio.get_running_loop().time())
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=remaining)
                except TimeoutError:
                    break
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))
                if message.get("id") != request_id:
                    continue
                if message.get("type") == "error":
                    saw_error = "disabled in plan mode" in str(
                        message.get("error", {}).get("message", "")
                    ).lower()
                if (
                    message.get("type") == "status"
                    and message.get("status") == "complete"
                ):
                    saw_complete = True
                # Tool call cards are intentionally hidden in Plan Mode
                # (BUG 13), so we only check the error + complete status.
                if saw_error and saw_complete:
                    break

            assert saw_error, "Expected plan-mode allowlist enforcement error."
            assert saw_complete, "Expected terminal complete status."
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


@pytest.mark.anyio
async def test_tool_chain_depth_limit_returns_last_non_terminal_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Repeated non-destructive tool calls should stop cleanly at configured depth."""

    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"5" * 32).decode("ascii"),
    )
    monkeypatch.setenv("AI_AGENT_MAX_TOOL_CHAIN_DEPTH", "2")

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "sample.txt"
    target.write_text("hello", encoding="utf-8")

    state: dict[str, int] = {"continuation_calls": 0}

    class _LoopingGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {"function_call": {"name": "get_metadata", "args": {"paths": [str(target)]}}}

        def send_continuation(self, **_kwargs: object) -> dict[str, object]:
            state["continuation_calls"] += 1
            return {"function_call": {"name": "get_metadata", "args": {"paths": [str(target)]}}}

    class _DummyReloadManager:
        version = 1

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def on_reload(self, _callback) -> None:
            return None

        def reload_modules(self, trigger: str):
            return SimpleNamespace(success=True, error=None, trigger=trigger)

    monkeypatch.setattr(
        main_module,
        "GeminiClient",
        _embedding_ready_gemini_client(_LoopingGeminiClient),
    )
    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )

    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    config = Config(
        gemini_api_key="test-key",
        schemas_dir=Path(__file__).resolve().parents[2] / "schemas",
        memory_root=tmp_path / "memory",
        allowed_roots=[workspace],
        automations_dir=tmp_path / "automations",
        enable_open_item=False,
        search_scan_limit=2000,
    )

    server_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=port, verbose=False)
    )

    try:
        reader, writer = await _connect_transport(endpoint_url)
        await _authenticate_socket(reader, writer)
        try:
            session_id = await _create_session_via_socket(reader, writer)
            request_id = "req-depth-limit-1"
            writer.write(
                (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "prompt",
                            "params": {"prompt": "loop metadata", "model": "gemini-3-flash-preview", "session_id": session_id},
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )
            await writer.drain()

            saw_result = False
            saw_complete = False
            saw_depth_text = False

            deadline = asyncio.get_running_loop().time() + 8.0
            while asyncio.get_running_loop().time() < deadline:
                line = await asyncio.wait_for(
                    reader.readline(),
                    timeout=max(0.05, deadline - asyncio.get_running_loop().time()),
                )
                if not line:
                    break
                message = json.loads(line.decode("utf-8"))
                if message.get("id") != request_id:
                    continue

                if message.get("type") == "result":
                    saw_result = True
                    content = message.get("result", {}).get("content", "")
                    if isinstance(content, str) and "tool-chain depth limit (2)" in content:
                        saw_depth_text = True

                if message.get("type") == "status" and message.get("status") == "complete":
                    saw_complete = True

                if saw_result and saw_complete:
                    break

            assert saw_result, "Expected fallback result when chain depth limit is reached."
            assert saw_depth_text, "Expected depth-limit marker in fallback result content."
            assert saw_complete, "Expected terminal complete status."
            assert state["continuation_calls"] == 1, "Expected exactly one continuation call at depth=2."
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)
