"""Regression coverage for IPC lifecycle, cancellation, session switching, and tool flow."""

from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from types import SimpleNamespace
from typing import AsyncIterator

import pytest

from agent_host import main as main_module
from agent_host.config import Config
from agent_host.ipc.protocol import ErrorMessage
from tests.unit.websocket_test_harness import connect_line_transport, reserve_tcp_port

TEST_IPC_AUTH_TOKEN = "test-ipc-auth-token"


@pytest.fixture
def anyio_backend() -> str:
    """Pin async tests to asyncio since IPC runtime uses asyncio APIs directly."""
    return "asyncio"


class _DummyReloadManager:
    """Minimal hot-reload stub for IPC runtime tests."""

    version = 1

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def on_reload(self, _callback) -> None:
        return None

    def reload_modules(self, trigger: str):
        return SimpleNamespace(success=True, error=None, trigger=trigger)


def _patch_reload_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_host.ipc.hot_reload as hot_reload_module

    monkeypatch.setattr(
        hot_reload_module,
        "init_reload_manager",
        lambda **_kwargs: _DummyReloadManager(),
    )


async def _connect_transport(endpoint_url: str, timeout_seconds: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        try:
            return await connect_line_transport(endpoint_url)
        except OSError:
            await asyncio.sleep(0.02)
    raise TimeoutError(f"WebSocket endpoint did not become ready in time: {endpoint_url}")


async def _authenticate_socket(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    token: str = TEST_IPC_AUTH_TOKEN,
    timeout_seconds: float = 5.0,
) -> None:
    request_id = f"req-auth-{uuid.uuid4().hex[:8]}"
    await _send_request(
        writer,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "auth.hello",
            "params": {
                "protocol_version": "2.0.0",
                "client_name": "pytest",
                "client_pid": 99999,
                "auth_token": token,
            },
        },
    )
    result = await _read_result_for_request(reader, request_id, timeout_seconds=timeout_seconds)
    content = result["result"]["content"]
    payload = json.loads(content) if isinstance(content, str) else content
    assert payload["authenticated"] is True
    assert payload["protocol_version"] == "2.0.0"


@asynccontextmanager
async def _running_server(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    gemini_client_cls: type,
    *,
    search_root: Path | None = None,
) -> AsyncIterator[tuple[asyncio.StreamReader, asyncio.StreamWriter, Path]]:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"r" * 32).decode("ascii"),
    )
    monkeypatch.setenv("AI_AGENT_IPC_AUTH_TOKEN", TEST_IPC_AUTH_TOKEN)
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

    monkeypatch.setattr(main_module, "GeminiClient", _EmbeddingReadyGeminiClient)
    _patch_reload_manager(monkeypatch)

    workspace = search_root or (tmp_path / "workspace")
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
        try:
            await _authenticate_socket(reader, writer)
            yield reader, writer, workspace
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(server_task, timeout=5.0)


async def _send_request(
    writer: asyncio.StreamWriter,
    payload: dict[str, object],
) -> None:
    writer.write((json.dumps(payload) + "\n").encode("utf-8"))
    await writer.drain()


async def _read_until_complete(
    reader: asyncio.StreamReader,
    request_id: str,
    *,
    timeout_seconds: float = 8.0,
) -> list[dict[str, object]]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    messages: list[dict[str, object]] = []
    while asyncio.get_running_loop().time() < deadline:
        remaining = deadline - asyncio.get_running_loop().time()
        line = await asyncio.wait_for(reader.readline(), timeout=max(0.05, remaining))
        if not line:
            break
        message = json.loads(line.decode("utf-8"))
        if message.get("id") != request_id:
            continue
        messages.append(message)
        if message.get("type") == "status" and message.get("status") == "complete":
            return messages
    raise AssertionError(f"Timed out waiting for completion of request {request_id}")


async def _read_result_for_request(
    reader: asyncio.StreamReader,
    request_id: str,
    *,
    timeout_seconds: float = 5.0,
) -> dict[str, object]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        remaining = deadline - asyncio.get_running_loop().time()
        line = await asyncio.wait_for(reader.readline(), timeout=max(0.05, remaining))
        if not line:
            break
        message = json.loads(line.decode("utf-8"))
        if message.get("id") != request_id:
            continue
        if message.get("type") == "error":
            raise AssertionError(f"Expected result for {request_id}, got error: {message}")
        if message.get("type") == "result":
            return message
    raise AssertionError(f"Timed out waiting for result message {request_id}")


async def _create_session_via_socket(
    reader,
    writer,
) -> str:
    """Create a session via socket RPC and return the session_id."""
    request_id = f"req-create-session-{uuid.uuid4().hex[:8]}"
    await _send_request(
        writer,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "session.create",
            "params": {"memory_mode": "off"},
        },
    )
    result = await _read_result_for_request(reader, request_id)
    content = result["result"]["content"]
    data = json.loads(content) if isinstance(content, str) else content
    return str(data["session_id"])


@pytest.mark.anyio
async def test_rejects_duplicate_inflight_request_ids(monkeypatch, tmp_path: Path) -> None:
    """A second prompt with the same request id should be rejected while first is in-flight."""

    class _SlowGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, str]:
            time.sleep(1.2)
            return {"text": "slow response"}

    async with _running_server(monkeypatch, tmp_path, _SlowGeminiClient) as (reader, writer, _):
        session_id = await _create_session_via_socket(reader, writer)
        prompt_id = "req-duplicate-1"
        cancel_id = "req-cancel-duplicate-1"

        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": prompt_id,
                "method": "prompt",
                "params": {"prompt": "first", "model": "gemini-3-flash-preview", "session_id": session_id},
            },
        )
        await asyncio.sleep(0.05)
        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": prompt_id,
                "method": "prompt",
                "params": {"prompt": "duplicate", "model": "gemini-3-flash-preview", "session_id": session_id},
            },
        )
        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": cancel_id,
                "method": "cancel",
                "params": {"request_id": prompt_id},
            },
        )

        saw_duplicate_rejection = False
        saw_cancel_ack = False
        saw_prompt_cancelled = False
        saw_prompt_complete = False

        deadline = asyncio.get_running_loop().time() + 8.0
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            line = await asyncio.wait_for(reader.readline(), timeout=max(0.05, remaining))
            if not line:
                break

            message = json.loads(line.decode("utf-8"))
            if message.get("id") == prompt_id and message.get("type") == "error":
                error = message.get("error", {})
                if (
                    error.get("code") == ErrorMessage.INVALID_REQUEST
                    and "already in progress" in str(error.get("message", "")).lower()
                ):
                    saw_duplicate_rejection = True
                if error.get("code") == -32800:
                    saw_prompt_cancelled = True

            if message.get("id") == cancel_id and message.get("type") == "result":
                saw_cancel_ack = True

            if (
                message.get("id") == prompt_id
                and message.get("type") == "status"
                and message.get("status") == "complete"
            ):
                saw_prompt_complete = True

            if (
                saw_duplicate_rejection
                and saw_cancel_ack
                and saw_prompt_cancelled
                and saw_prompt_complete
            ):
                break

        assert saw_duplicate_rejection, "Duplicate request id was not rejected."
        assert saw_cancel_ack, "Cancel request did not return acknowledgement."
        assert saw_prompt_cancelled, "Cancelled prompt did not emit cancellation error."
        assert saw_prompt_complete, "Cancelled prompt did not emit terminal complete status."


@pytest.mark.anyio
async def test_cancel_without_request_id_cancels_all_client_prompts(monkeypatch, tmp_path: Path) -> None:
    """Cancel without target id should cancel every active prompt for that client."""

    class _SlowGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, str]:
            time.sleep(1.2)
            return {"text": "slow response"}

    async with _running_server(monkeypatch, tmp_path, _SlowGeminiClient) as (reader, writer, _):
        session_id = await _create_session_via_socket(reader, writer)
        prompt_ids = ("req-cancel-all-a", "req-cancel-all-b")
        cancel_id = "req-cancel-all"

        for prompt_id in prompt_ids:
            await _send_request(
                writer,
                {
                    "jsonrpc": "2.0",
                    "id": prompt_id,
                    "method": "prompt",
                    "params": {"prompt": prompt_id, "model": "gemini-3-flash-preview", "session_id": session_id},
                },
            )

        await asyncio.sleep(0.05)
        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": cancel_id,
                "method": "cancel",
                "params": {},
            },
        )

        cancel_result_mentions_two = False
        cancelled_prompts: set[str] = set()
        completed_prompts: set[str] = set()

        deadline = asyncio.get_running_loop().time() + 8.0
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            line = await asyncio.wait_for(reader.readline(), timeout=max(0.05, remaining))
            if not line:
                break

            message = json.loads(line.decode("utf-8"))
            request_id = message.get("id")
            message_type = message.get("type")

            if request_id == cancel_id and message_type == "result":
                content = str(message.get("result", {}).get("content", ""))
                if "2 active request(s)" in content:
                    cancel_result_mentions_two = True

            if request_id in prompt_ids and message_type == "error":
                if message.get("error", {}).get("code") == -32800:
                    cancelled_prompts.add(str(request_id))

            if request_id in prompt_ids and message_type == "status":
                if message.get("status") == "complete":
                    completed_prompts.add(str(request_id))

            if (
                cancel_result_mentions_two
                and cancelled_prompts == set(prompt_ids)
                and completed_prompts == set(prompt_ids)
            ):
                break

        assert cancel_result_mentions_two, "Cancel-all acknowledgement did not include both prompts."
        assert cancelled_prompts == set(prompt_ids), "Not all active prompts were cancelled."
        assert completed_prompts == set(prompt_ids), "Not all cancelled prompts emitted complete status."


@pytest.mark.anyio
async def test_malformed_prompt_params_type_returns_invalid_request(monkeypatch, tmp_path: Path) -> None:
    """Prompt params with wrong JSON type should fail cleanly as invalid request."""

    class _FastGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, str]:
            return {"text": "unused"}

    async with _running_server(monkeypatch, tmp_path, _FastGeminiClient) as (reader, writer, _):
        request_id = "req-malformed-params-1"
        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "prompt",
                "params": ["this-should-be-an-object"],
            },
        )

        line = await asyncio.wait_for(reader.readline(), timeout=3.0)
        assert line
        message = json.loads(line.decode("utf-8"))
        assert message["id"] == request_id
        assert message["type"] == "error"
        assert message["error"]["code"] == ErrorMessage.INVALID_REQUEST
        assert "missing 'prompt' parameter" in message["error"]["message"].lower()


@pytest.mark.anyio
async def test_rapid_session_switching_keeps_histories_isolated(monkeypatch, tmp_path: Path) -> None:
    """Back-to-back prompts across sessions should preserve per-session transcript boundaries."""

    class _FastGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, str]:
            return {"text": "ok"}

    async with _running_server(monkeypatch, tmp_path, _FastGeminiClient) as (reader, writer, _):
        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": "req-create-a",
                "method": "session.create",
                "params": {"title": "session-switch-alpha", "memory_mode": "on"},
            },
        )
        create_a = await _read_result_for_request(reader, "req-create-a")
        session_a = json.loads(str(create_a["result"]["content"]))["session_id"]

        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": "req-create-b",
                "method": "session.create",
                "params": {"title": "session-switch-beta", "memory_mode": "on"},
            },
        )
        create_b = await _read_result_for_request(reader, "req-create-b")
        session_b = json.loads(str(create_b["result"]["content"]))["session_id"]

        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": "req-session-a",
                "method": "prompt",
                "params": {
                    "prompt": "prompt for alpha",
                    "model": "gemini-3-flash-preview",
                    "session_id": session_a,
                    "memory_mode": "on",
                },
            },
        )
        await _read_until_complete(reader, "req-session-a")

        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": "req-session-b",
                "method": "prompt",
                "params": {
                    "prompt": "prompt for beta",
                    "model": "gemini-3-flash-preview",
                    "session_id": session_b,
                    "memory_mode": "on",
                },
            },
        )
        await _read_until_complete(reader, "req-session-b")

        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": "req-history-a",
                "method": "session.history",
                "params": {"session_id": session_a, "limit": 20},
            },
        )
        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": "req-history-b",
                "method": "session.history",
                "params": {"session_id": session_b, "limit": 20},
            },
        )

        history_a_msg = await _read_result_for_request(reader, "req-history-a")
        history_b_msg = await _read_result_for_request(reader, "req-history-b")

        history_a = json.loads(str(history_a_msg["result"]["content"]))
        history_b = json.loads(str(history_b_msg["result"]["content"]))

        history_a_texts = [str(item.get("content", "")) for item in history_a]
        history_b_texts = [str(item.get("content", "")) for item in history_b]

        assert "prompt for alpha" in history_a_texts
        assert "prompt for alpha" not in history_b_texts
        assert "prompt for beta" in history_b_texts
        assert "prompt for beta" not in history_a_texts


@pytest.mark.anyio
async def test_tool_validation_failure_feeds_error_back_to_model(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Schema-invalid tool calls should produce a failed tool notification and feed
    the validation error back to the model as a function response so it can
    self-correct."""

    class _InvalidToolGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {"function_call": {"name": "search_files", "args": {}}}

        def send_continuation(self, **_kwargs: object) -> dict[str, object]:
            return {"text": "Validation failed for search_files: query is required."}

    async with _running_server(monkeypatch, tmp_path, _InvalidToolGeminiClient) as (
        reader,
        writer,
        _,
    ):
        session_id = await _create_session_via_socket(reader, writer)
        request_id = "req-tool-validation-fail"
        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "prompt",
                "params": {"prompt": "find files", "model": "gemini-3-flash-preview", "session_id": session_id},
            },
        )

        messages = await _read_until_complete(reader, request_id)
        saw_calling_tool = False
        saw_failed_tool_notification = False
        saw_result_with_error = False

        for message in messages:
            if (
                message.get("type") == "status"
                and message.get("status") == "calling_tool"
                and message.get("detail") == "search_files"
            ):
                saw_calling_tool = True

            if message.get("type") == "tool_call":
                tool_payload = message.get("tool", {})
                if (
                    isinstance(tool_payload, dict)
                    and tool_payload.get("name") == "search_files"
                    and tool_payload.get("status") == "failed"
                ):
                    saw_failed_tool_notification = True

            if message.get("type") == "result":
                result_payload = message.get("result", {})
                content = str(result_payload.get("content", "")).lower()
                if "validation failed" in content:
                    saw_result_with_error = True

        assert saw_calling_tool, "Missing calling_tool status."
        assert saw_failed_tool_notification, "Missing failed tool_call notification."
        assert saw_result_with_error, (
            "Validation error should be fed back as a result, not terminate the request."
        )


@pytest.mark.anyio
async def test_tool_success_result_includes_tool_calls_payload_for_ui(monkeypatch, tmp_path: Path) -> None:
    """Successful tool execution should include result.content and result.tool_calls for UI parity."""

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    matched_file = workspace / "python_regression_note.txt"
    matched_file.write_text("hello")

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
            return {
                "text": f"Found 1 matching file: {matched_file}",
            }

    async with _running_server(
        monkeypatch,
        tmp_path,
        _ToolGeminiClient,
        search_root=workspace,
    ) as (reader, writer, _):
        session_id = await _create_session_via_socket(reader, writer)
        request_id = "req-tool-success-ui-payload"
        await _send_request(
            writer,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "prompt",
                "params": {"prompt": "find python files", "model": "gemini-3-flash-preview", "session_id": session_id},
            },
        )

        messages = await _read_until_complete(reader, request_id)
        result_messages = [msg for msg in messages if msg.get("type") == "result"]
        assert result_messages, "Expected a result payload."
        result_payload = result_messages[-1].get("result", {})
        assert isinstance(result_payload, dict)

        content = str(result_payload.get("content", ""))
        assert "Found" in content
        assert str(matched_file) in content

        tool_calls = result_payload.get("tool_calls", [])
        assert isinstance(tool_calls, list)
        assert tool_calls
        first_tool_call = tool_calls[0]
        assert isinstance(first_tool_call, dict)
        assert first_tool_call.get("name") == "search_files"
        assert first_tool_call.get("arguments") == {"query": "python", "limit": 5}


@pytest.mark.anyio
async def test_invalid_utf8_payload_returns_parse_error(monkeypatch, tmp_path: Path) -> None:
    """Malformed transport bytes should emit parse_error instead of crashing handler loop."""

    class _FastGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, str]:
            return {"text": "unused"}

    async with _running_server(monkeypatch, tmp_path, _FastGeminiClient) as (reader, writer, _):
        writer.write(b"\xff\xfe\xfa\n")
        await writer.drain()

        line = await asyncio.wait_for(reader.readline(), timeout=3.0)
        assert line
        message = json.loads(line.decode("utf-8"))
        assert message["id"] == "global"
        assert message["type"] == "error"
        assert message["error"]["code"] == ErrorMessage.PARSE_ERROR
        assert "invalid utf-8" in message["error"]["message"].lower()


@pytest.mark.anyio
async def test_rapid_repeated_sends_complete_all_requests(monkeypatch, tmp_path: Path) -> None:
    """Rapid prompt submissions with unique ids should each reach result + complete."""

    class _FastGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, str]:
            return {"text": "ok"}

    async with _running_server(monkeypatch, tmp_path, _FastGeminiClient) as (reader, writer, _):
        session_id = await _create_session_via_socket(reader, writer)
        request_ids = [f"req-rapid-{index}" for index in range(12)]
        for request_id in request_ids:
            await _send_request(
                writer,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "prompt",
                    "params": {"prompt": request_id, "model": "gemini-3-flash-preview", "session_id": session_id},
                },
            )

        saw_result: set[str] = set()
        saw_complete: set[str] = set()
        deadline = asyncio.get_running_loop().time() + 12.0

        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            line = await asyncio.wait_for(reader.readline(), timeout=max(0.05, remaining))
            if not line:
                break

            message = json.loads(line.decode("utf-8"))
            request_id = message.get("id")
            if request_id not in request_ids:
                continue

            if message.get("type") == "result":
                saw_result.add(str(request_id))

            if message.get("type") == "status" and message.get("status") == "complete":
                saw_complete.add(str(request_id))

            if len(saw_result) == len(request_ids) and len(saw_complete) == len(request_ids):
                break

        assert saw_result == set(request_ids), "Some rapid-fire requests never produced results."
        assert saw_complete == set(request_ids), "Some rapid-fire requests never completed."
