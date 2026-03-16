"""Regression coverage for session/memory IPC behaviors in main handlers."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_host import main as main_module
from agent_host.adapters.modes.plan import state_machine as plan_mode_module
from agent_host.config import Config
from agent_host.core import orchestrator as orchestrator_module
from agent_host.ipc.protocol import IncomingRequest
from agent_host.memory.manager import MemoryManager


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _stub_plan_mode_nlp_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main_module,
        "_preload_plan_mode_nlp_classifier",
        lambda _logger: "pytest-stub-model",
    )


class _DummyGeminiClient:
    def __init__(self, **_kwargs: object) -> None:
        pass

    def resolve_text_model(self, requested_model: str | None = None) -> str:
        return requested_model or "gemini-test"

    def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
        return {"text": "unused"}


def _continuation_ready_client(client_cls: type) -> type:
    """Ensure test doubles provide the strict continuation API expected by runtime."""
    if not getattr(client_cls, "_strict_runtime_ready", False):
        original_init = getattr(client_cls, "__init__", None)

        def _wrapped_init(self, **kwargs: object) -> None:
            if callable(original_init):
                original_init(self, **kwargs)
            if not hasattr(self, "model_name"):
                self.model_name = kwargs.get("model_name") or "gemini-test"
            if not hasattr(self, "_client"):
                self._client = SimpleNamespace(
                    models=SimpleNamespace(
                        embed_content=lambda **_kwargs: SimpleNamespace(
                            embeddings=[SimpleNamespace(values=[0.1] * 8)]
                        )
                    )
                )

        setattr(client_cls, "__init__", _wrapped_init)
        if not hasattr(client_cls, "resolve_text_model"):
            setattr(
                client_cls,
                "resolve_text_model",
                lambda self, requested_model=None: requested_model or getattr(self, "model_name", "gemini-test"),
            )
        if not hasattr(client_cls, "resolve_image_model"):
            setattr(
                client_cls,
                "resolve_image_model",
                lambda self, requested_model=None: requested_model or getattr(self, "model_name", "gemini-test"),
            )
        if not hasattr(client_cls, "_supports_native_deep_think"):
            setattr(
                client_cls,
                "_supports_native_deep_think",
                staticmethod(lambda model_name: "thinking" in model_name or "deep-think" in model_name),
            )
        setattr(client_cls, "_strict_runtime_ready", True)

    existing = getattr(client_cls, "send_continuation", None)
    if callable(existing):
        return client_cls

    def _send_continuation(self, **kwargs: object) -> dict[str, object]:
        prompt_impl = getattr(type(self), "send_prompt_with_tools", None)
        if callable(prompt_impl):
            had_counter = hasattr(type(self), "send_prompt_calls")
            before_calls = getattr(type(self), "send_prompt_calls", None)
            response = prompt_impl(self, **kwargs)
            if had_counter and isinstance(before_calls, int):
                setattr(type(self), "send_prompt_calls", before_calls)
            return response
        return {"text": "continuation response"}

    setattr(client_cls, "send_continuation", _send_continuation)
    return client_cls


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


class _DummyClient:
    _counter = 0

    def __init__(self) -> None:
        type(self)._counter += 1
        self.address = f"dummy-client-{type(self)._counter}"
        self.sent: list[dict[str, object]] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(json.loads(data.decode("utf-8")))


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
        self.broadcast_messages: list[dict[str, object]] = []
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

    async def broadcast(self, data: bytes) -> None:
        self.broadcast_messages.append(json.loads(data.decode("utf-8")))

    def release(self) -> None:
        self._stop_event.set()
        if _FakeServer.latest is self:
            _FakeServer.latest = None


async def _wait_for_fake_server(timeout_seconds: float = 10.0) -> _FakeServer:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        latest = _FakeServer.latest
        if latest is not None and latest.handlers and not latest._stop_event.is_set():
            return latest
        await asyncio.sleep(0.01)
    raise TimeoutError("Fake server did not initialize in time")


async def _wait_for_request_complete(
    client: _DummyClient,
    request_id: str,
    timeout_seconds: float = 3.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if any(
            message.get("id") == request_id
            and message.get("type") == "status"
            and message.get("status") == "complete"
            for message in client.sent
        ):
            return
        await asyncio.sleep(0.01)
    raise TimeoutError(f"Request did not complete in time: {request_id}")


async def _create_test_session(fake_server: _FakeServer, client: _DummyClient) -> str:
    """Create a session via session.create RPC and return its session_id."""
    create_req = IncomingRequest(
        id="req-create-test-session",
        method="session.create",
        params={"memory_mode": "off"},
    )
    await fake_server.handlers["session.create"](create_req, client)
    created = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
    session_id = str(created["session_id"])
    client.sent.clear()
    return session_id


def _latest_lifecycle_event(fake_server: _FakeServer, *, domain: str, action: str) -> dict[str, object]:
    assert fake_server.broadcast_messages, "Expected at least one broadcast message."
    for system_message in reversed(fake_server.broadcast_messages):
        if system_message.get("type") != "system":
            continue
        system_payload = system_message.get("system", {})
        if not isinstance(system_payload, dict):
            continue
        if system_payload.get("event") != "lifecycle":
            continue
        if system_payload.get("domain") != domain:
            continue
        if system_payload.get("action") != action:
            continue
        payload = system_payload.get("payload", {})
        assert isinstance(payload, dict)
        return payload
    raise AssertionError(f"Missing lifecycle event domain={domain} action={action}")


@pytest.mark.anyio
async def test_session_history_unknown_session_returns_invalid_request_no_side_effects(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"h" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        fake_server = await _wait_for_fake_server(timeout_seconds=10.0)
        assert "session.history" in fake_server.handlers
        assert "session.list" in fake_server.handlers

        client = _DummyClient()
        history_request = IncomingRequest(
            id="req-history-1",
            method="session.history",
            params={"session_id": "new-history-session"},
        )
        await fake_server.handlers["session.history"](history_request, client)

        assert len(client.sent) == 1
        assert client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "unknown session_id" in str(client.sent[0].get("error", {}).get("message", "")).lower()

        client.sent.clear()
        list_request = IncomingRequest(
            id="req-list-1",
            method="session.list",
            params={"limit": 100},
        )
        await fake_server.handlers["session.list"](list_request, client)

        assert len(client.sent) == 1
        assert client.sent[0].get("type") == "result"
        sessions = json.loads(client.sent[0].get("result", {}).get("content", "[]"))
        assert all(row.get("session_id") != "new-history-session" for row in sessions)
        assert not (tmp_path / "memory" / "sessions" / "new-history-session.db").exists()
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_session_history_omitted_memory_mode_does_not_mutate_existing_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"m" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        fake_server = await _wait_for_fake_server(timeout_seconds=10.0)
        client = _DummyClient()

        create_request = IncomingRequest(
            id="req-create-1",
            method="session.create",
            params={"memory_mode": "off"},
        )
        await fake_server.handlers["session.create"](create_request, client)
        created = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created["session_id"])
        assert created["memory_mode"] == "off"

        client.sent.clear()
        history_request = IncomingRequest(
            id="req-history-keep-mode",
            method="session.history",
            params={"session_id": session_id},
        )
        await fake_server.handlers["session.history"](history_request, client)
        assert client.sent and client.sent[0].get("type") == "result"

        client.sent.clear()
        list_request = IncomingRequest(
            id="req-list-after-history",
            method="session.list",
            params={"limit": 20},
        )
        await fake_server.handlers["session.list"](list_request, client)
        sessions = json.loads(client.sent[0].get("result", {}).get("content", "[]"))
        matching = [row for row in sessions if row.get("session_id") == session_id]
        assert matching
        assert matching[0].get("memory_mode") == "off"
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_session_history_rejects_memory_mode_and_does_not_mutate_session_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"n" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        fake_server = await _wait_for_fake_server(timeout_seconds=10.0)
        client = _DummyClient()

        create_request = IncomingRequest(
            id="req-create-explicit",
            method="session.create",
            params={"memory_mode": "off"},
        )
        await fake_server.handlers["session.create"](create_request, client)
        created = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created["session_id"])

        client.sent.clear()
        history_request = IncomingRequest(
            id="req-history-explicit-mode",
            method="session.history",
            params={"session_id": session_id, "memory_mode": "on"},
        )
        await fake_server.handlers["session.history"](history_request, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "no longer accepts memory_mode" in str(
            client.sent[0].get("error", {}).get("message", "")
        ).lower()

        client.sent.clear()
        list_request = IncomingRequest(
            id="req-list-explicit-mode",
            method="session.list",
            params={"limit": 20},
        )
        await fake_server.handlers["session.list"](list_request, client)
        sessions = json.loads(client.sent[0].get("result", {}).get("content", "[]"))
        matching = [row for row in sessions if row.get("session_id") == session_id]
        assert matching
        assert matching[0].get("memory_mode") == "off"
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_session_history_page_returns_latest_and_older_pages(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"p" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        fake_server = await _wait_for_fake_server(timeout_seconds=10.0)
        assert "session.history_page" in fake_server.handlers
        client = _DummyClient()

        create_request = IncomingRequest(
            id="req-create-paged",
            method="session.create",
            params={"memory_mode": "on"},
        )
        await fake_server.handlers["session.create"](create_request, client)
        created = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created["session_id"])

        memory_manager = MemoryManager(tmp_path / "memory")
        for index in range(10):
            memory_manager.store.append_message(session_id, role="user", content=f"row-{index}")

        client.sent.clear()
        latest_request = IncomingRequest(
            id="req-history-page-latest",
            method="session.history_page",
            params={"session_id": session_id, "direction": "latest", "limit": 4},
        )
        await fake_server.handlers["session.history_page"](latest_request, client)
        latest_payload = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        latest_rows = latest_payload.get("messages", [])
        assert [row.get("turn_index") for row in latest_rows] == [6, 7, 8, 9]
        assert latest_payload.get("has_older") is True
        assert latest_payload.get("oldest_turn_index") == 6
        assert latest_payload.get("newest_turn_index") == 9

        client.sent.clear()
        older_request = IncomingRequest(
            id="req-history-page-older",
            method="session.history_page",
            params={
                "session_id": session_id,
                "direction": "older",
                "anchor_turn_index": 6,
                "limit": 4,
            },
        )
        await fake_server.handlers["session.history_page"](older_request, client)
        older_payload = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        older_rows = older_payload.get("messages", [])
        assert [row.get("turn_index") for row in older_rows] == [2, 3, 4, 5]
        assert older_payload.get("has_older") is True
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_memory_unknown_session_returns_invalid_request_without_db_creation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"p" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        fake_server = await _wait_for_fake_server(timeout_seconds=10.0)
        client = _DummyClient()
        assert "memory.list" in fake_server.handlers
        assert "memory.delete" in fake_server.handlers

        list_request = IncomingRequest(
            id="req-memory-list-unknown",
            method="memory.list",
            params={"session_id": "unknown-memory-session"},
        )
        await fake_server.handlers["memory.list"](list_request, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600

        client.sent.clear()
        delete_request = IncomingRequest(
            id="req-memory-delete-unknown",
            method="memory.delete",
            params={"session_id": "unknown-memory-session", "memory_id": "m1"},
        )
        await fake_server.handlers["memory.delete"](delete_request, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert not (tmp_path / "memory" / "sessions" / "unknown-memory-session.db").exists()
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_session_set_mode_registered_and_updates_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"q" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        fake_server = await _wait_for_fake_server(timeout_seconds=10.0)
        client = _DummyClient()
        assert "session.set_mode" in fake_server.handlers

        create_request = IncomingRequest(
            id="req-create-mode",
            method="session.create",
            params={"memory_mode": "off"},
        )
        await fake_server.handlers["session.create"](create_request, client)
        created = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created["session_id"])

        client.sent.clear()
        set_mode_request = IncomingRequest(
            id="req-set-mode-1",
            method="session.set_mode",
            params={"session_id": session_id, "memory_mode": "ephemeral"},
        )
        await fake_server.handlers["session.set_mode"](set_mode_request, client)
        assert client.sent and client.sent[0].get("type") == "result"
        payload = json.loads(client.sent[0].get("result", {}).get("content", "{}"))
        assert payload.get("memory_mode") == "ephemeral"

        client.sent.clear()
        bad_mode_request = IncomingRequest(
            id="req-set-mode-2",
            method="session.set_mode",
            params={"session_id": session_id, "memory_mode": "invalid-mode"},
        )
        await fake_server.handlers["session.set_mode"](bad_mode_request, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600

        client.sent.clear()
        unknown_request = IncomingRequest(
            id="req-set-mode-3",
            method="session.set_mode",
            params={"session_id": "missing-session", "memory_mode": "on"},
        )
        await fake_server.handlers["session.set_mode"](unknown_request, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_session_mutation_handlers_emit_lifecycle_system_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"q" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        fake_server = await _wait_for_fake_server(timeout_seconds=10.0)
        client = _DummyClient()

        create_request = IncomingRequest(
            id="req-session-event-create",
            method="session.create",
            params={"memory_mode": "off"},
        )
        await fake_server.handlers["session.create"](create_request, client)
        created = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created["session_id"])
        payload = _latest_lifecycle_event(fake_server, domain="session", action="created")
        created_session = payload.get("session", {})
        assert isinstance(created_session, dict)
        assert created_session.get("session_id") == session_id

        rename_request = IncomingRequest(
            id="req-session-event-rename",
            method="session.rename",
            params={"session_id": session_id, "title": "Renamed Session"},
        )
        await fake_server.handlers["session.rename"](rename_request, client)
        payload = _latest_lifecycle_event(fake_server, domain="session", action="updated")
        updated_session = payload.get("session", {})
        assert isinstance(updated_session, dict)
        assert updated_session.get("title") == "Renamed Session"

        set_mode_request = IncomingRequest(
            id="req-session-event-mode",
            method="session.set_mode",
            params={"session_id": session_id, "memory_mode": "ephemeral"},
        )
        await fake_server.handlers["session.set_mode"](set_mode_request, client)
        payload = _latest_lifecycle_event(fake_server, domain="session", action="updated")
        mode_session = payload.get("session", {})
        assert isinstance(mode_session, dict)
        assert mode_session.get("memory_mode") == "ephemeral"

        delete_request = IncomingRequest(
            id="req-session-event-delete",
            method="session.delete",
            params={"session_id": session_id},
        )
        await fake_server.handlers["session.delete"](delete_request, client)
        payload = _latest_lifecycle_event(fake_server, domain="session", action="deleted")
        deleted_session = payload.get("session", {})
        assert isinstance(deleted_session, dict)
        assert deleted_session.get("session_id") == session_id
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_notes_and_memory_mutations_emit_lifecycle_system_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"n" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
    monkeypatch.setattr(
        main_module.MemoryManager,
        "delete_memory",
        lambda _self, _session_id, _memory_id: True,
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
        fake_server = await _wait_for_fake_server(timeout_seconds=10.0)
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)

        note_create = IncomingRequest(
            id="req-note-event-create",
            method="notes.create",
            params={"session_id": session_id, "content": "first note"},
        )
        await fake_server.handlers["notes.create"](note_create, client)
        created_note = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        note_id = str(created_note["note_id"])
        payload = _latest_lifecycle_event(fake_server, domain="notes", action="created")
        assert payload.get("session_id") == session_id
        payload_note = payload.get("note", {})
        assert isinstance(payload_note, dict)
        assert payload_note.get("note_id") == note_id

        note_update = IncomingRequest(
            id="req-note-event-update",
            method="notes.update",
            params={"session_id": session_id, "note_id": note_id, "content": "updated note"},
        )
        await fake_server.handlers["notes.update"](note_update, client)
        payload = _latest_lifecycle_event(fake_server, domain="notes", action="updated")
        assert payload.get("session_id") == session_id
        payload_note = payload.get("note", {})
        assert isinstance(payload_note, dict)
        assert payload_note.get("content") == "updated note"

        note_delete = IncomingRequest(
            id="req-note-event-delete",
            method="notes.delete",
            params={"session_id": session_id, "note_id": note_id},
        )
        await fake_server.handlers["notes.delete"](note_delete, client)
        payload = _latest_lifecycle_event(fake_server, domain="notes", action="deleted")
        assert payload.get("session_id") == session_id
        assert payload.get("note_id") == note_id

        memory_delete = IncomingRequest(
            id="req-memory-event-delete",
            method="memory.delete",
            params={"session_id": session_id, "memory_id": "memory-1"},
        )
        await fake_server.handlers["memory.delete"](memory_delete, client)
        payload = _latest_lifecycle_event(fake_server, domain="memory", action="deleted")
        assert payload.get("session_id") == session_id
        assert payload.get("memory_id") == "memory-1"
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_record_interaction_emits_session_activity_event(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"m" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        fake_server = await _wait_for_fake_server(timeout_seconds=10.0)
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)
        start_index = len(fake_server.broadcast_messages)

        prompt_request = IncomingRequest(
            id="req-prompt-session-activity",
            method="prompt",
            params={"prompt": "hello", "session_id": session_id},
        )
        await fake_server.handlers["prompt"](prompt_request, client)
        await _wait_for_request_complete(client, "req-prompt-session-activity")

        post_messages = fake_server.broadcast_messages[start_index:]
        assert post_messages, "Expected lifecycle broadcasts after prompt."
        assert any(
            message.get("type") == "system"
            and isinstance(message.get("system"), dict)
            and message["system"].get("event") == "lifecycle"
            and message["system"].get("domain") == "session"
            and message["system"].get("action") == "activity"
            and isinstance(message["system"].get("payload"), dict)
            and isinstance(message["system"]["payload"].get("session"), dict)
            and message["system"]["payload"]["session"].get("session_id") == session_id
            for message in post_messages
        )
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_omitted_memory_mode_uses_existing_session_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"r" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        fake_server = await _wait_for_fake_server(timeout_seconds=10.0)
        client = _DummyClient()

        create_request = IncomingRequest(
            id="req-create-off-mode",
            method="session.create",
            params={"memory_mode": "off"},
        )
        await fake_server.handlers["session.create"](create_request, client)
        created = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created["session_id"])
        assert created["memory_mode"] == "off"

        client.sent.clear()
        prompt_request = IncomingRequest(
            id="req-prompt-keep-off-mode",
            method="prompt",
            params={"prompt": "hello", "session_id": session_id},
        )
        await fake_server.handlers["prompt"](prompt_request, client)
        await _wait_for_request_complete(client, "req-prompt-keep-off-mode")
        assert not any(
            message.get("id") == "req-prompt-keep-off-mode"
            and message.get("type") == "error"
            for message in client.sent
        )

        client.sent.clear()
        list_request = IncomingRequest(
            id="req-list-mode-after-prompt",
            method="session.list",
            params={"limit": 20},
        )
        await fake_server.handlers["session.list"](list_request, client)
        sessions = json.loads(client.sent[0].get("result", {}).get("content", "[]"))
        matching = [row for row in sessions if row.get("session_id") == session_id]
        assert matching
        assert matching[0].get("memory_mode") == "off"
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_rejects_invalid_memory_mode_and_unknown_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"s" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        client = _DummyClient()

        create_request = IncomingRequest(
            id="req-create-valid",
            method="session.create",
            params={"memory_mode": "on"},
        )
        await fake_server.handlers["session.create"](create_request, client)
        created = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created["session_id"])

        client.sent.clear()
        invalid_mode_prompt = IncomingRequest(
            id="req-prompt-invalid-mode",
            method="prompt",
            params={
                "prompt": "hello",
                "session_id": session_id,
                "memory_mode": "invalid-mode",
            },
        )
        await fake_server.handlers["prompt"](invalid_mode_prompt, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "invalid memory_mode" in str(client.sent[0].get("error", {}).get("message", "")).lower()

        client.sent.clear()
        unknown_session_prompt = IncomingRequest(
            id="req-prompt-unknown-session",
            method="prompt",
            params={
                "prompt": "hello",
                "session_id": "missing-session",
            },
        )
        await fake_server.handlers["prompt"](unknown_session_prompt, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "unknown session_id" in str(client.sent[0].get("error", {}).get("message", "")).lower()
        assert not (tmp_path / "memory" / "sessions" / "missing-session.db").exists()

        client.sent.clear()
        malformed_session_prompt = IncomingRequest(
            id="req-prompt-bad-session",
            method="prompt",
            params={
                "prompt": "hello",
                "session_id": "!!!",
            },
        )
        await fake_server.handlers["prompt"](malformed_session_prompt, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "invalid session_id" in str(client.sent[0].get("error", {}).get("message", "")).lower()
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_rejects_invalid_verbosity_value(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"v" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)

        invalid_verbosity_prompt = IncomingRequest(
            id="req-prompt-invalid-verbosity",
            method="prompt",
            params={
                "prompt": "hello",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "verbosity": "verbose",
            },
        )
        await fake_server.handlers["prompt"](invalid_verbosity_prompt, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "invalid verbosity" in str(client.sent[0].get("error", {}).get("message", "")).lower()
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_rejects_invalid_execution_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"e" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)
        invalid_mode_prompt = IncomingRequest(
            id="req-prompt-invalid-execution-mode",
            method="prompt",
            params={
                "prompt": "hello",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "execution_mode": "guided",
            },
        )
        await fake_server.handlers["prompt"](invalid_mode_prompt, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "invalid execution_mode" in str(
            client.sent[0].get("error", {}).get("message", "")
        ).lower()
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_teacher_mode_auto_captures_note(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"t" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)
        request_id = "req-prompt-teacher-mode"
        teacher_prompt = IncomingRequest(
            id=request_id,
            method="prompt",
            params={
                "prompt": "teach me photosynthesis",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "execution_mode": "teacher",
            },
        )
        await fake_server.handlers["prompt"](teacher_prompt, client)
        await _wait_for_request_complete(client, request_id)

        request_messages = [message for message in client.sent if message.get("id") == request_id]
        assert not any(message.get("type") == "error" for message in request_messages)
        # Teacher mode auto-capture calls memory_manager.create_note() directly
        # (not via tool executor), so verify via the status message it sends
        # after successful note creation: "Teacher note saved (id=...)"
        assert any(
            message.get("type") == "status"
            and "teacher note saved" in str(message.get("detail", "")).lower()
            for message in request_messages
        ) or any(
            message.get("type") == "status"
            and "study notes" in str(message.get("detail", "")).lower()
            for message in request_messages
        ), f"Expected teacher note capture status message, got: {[m for m in request_messages if m.get('type') == 'status']}"
        assert any(message.get("type") == "result" for message in request_messages)
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_teacher_mode_no_text_returns_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"u" * 32).decode("ascii"),
    )

    class _NoTextGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {}

    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_NoTextGeminiClient))
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
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)
        request_id = "req-prompt-teacher-mode-no-text"
        teacher_prompt = IncomingRequest(
            id=request_id,
            method="prompt",
            params={
                "prompt": "teach me calculus limits",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "execution_mode": "teacher",
            },
        )
        await fake_server.handlers["prompt"](teacher_prompt, client)
        await _wait_for_request_complete(client, request_id)

        error_messages = [
            str(message.get("error", {}).get("message", "")).lower()
            for message in client.sent
            if message.get("id") == request_id and message.get("type") == "error"
        ]
        assert any(
            "teacher mode could not produce a valid teaching response" in message
            for message in error_messages
        )
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_rejects_non_boolean_deep_think(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"k" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)
        invalid_prompt = IncomingRequest(
            id="req-prompt-invalid-deep-think",
            method="prompt",
            params={
                "prompt": "hello",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "deep_think": "true",
            },
        )
        await fake_server.handlers["prompt"](invalid_prompt, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "invalid deep_think" in str(
            client.sent[0].get("error", {}).get("message", "")
        ).lower()
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_rejects_deep_think_for_unsupported_model(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"l" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)
        invalid_prompt = IncomingRequest(
            id="req-prompt-unsupported-deep-think-model",
            method="prompt",
            params={
                "prompt": "hello",
                "model": "gemini-2.0-flash-exp",
                "session_id": session_id,
                "deep_think": True,
            },
        )
        await fake_server.handlers["prompt"](invalid_prompt, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        message = str(client.sent[0].get("error", {}).get("message", "")).lower()
        assert "deep-think mode requires" in message
        assert "gemini 3 or gemini 2.5" in message
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_rejects_invalid_presentation_and_stream_animation_modes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"p" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)

        invalid_presentation_prompt = IncomingRequest(
            id="req-prompt-invalid-presentation-style",
            method="prompt",
            params={
                "prompt": "hello",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "presentation_style": "modern_pretty",
            },
        )
        await fake_server.handlers["prompt"](invalid_presentation_prompt, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "invalid presentation_style" in str(
            client.sent[0].get("error", {}).get("message", "")
        ).lower()

        client.sent.clear()
        invalid_stream_animation_prompt = IncomingRequest(
            id="req-prompt-invalid-stream-animation",
            method="prompt",
            params={
                "prompt": "hello",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "stream_animation": "fancy_cursor",
            },
        )
        await fake_server.handlers["prompt"](invalid_stream_animation_prompt, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "invalid stream_animation" in str(
            client.sent[0].get("error", {}).get("message", "")
        ).lower()
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_validates_input_paths_and_plan_mode_statuses(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"p" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        allowed_roots=[tmp_path],
    )

    run_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=8765, verbose=False)
    )

    try:
        fake_server = await _wait_for_fake_server()
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)

        invalid_paths_prompt = IncomingRequest(
            id="req-prompt-invalid-input-paths",
            method="prompt",
            params={
                "prompt": "hello",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "input_paths": "not-a-list",
            },
        )
        await fake_server.handlers["prompt"](invalid_paths_prompt, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert "invalid input_paths" in str(
            client.sent[0].get("error", {}).get("message", "")
        ).lower()

        dropped = tmp_path / "incoming.txt"
        dropped.write_text("payload")
        client.sent.clear()
        valid_prompt = IncomingRequest(
            id="req-prompt-plan-mode-valid-input-paths",
            method="prompt",
            params={
                "prompt": "organize this file",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "execution_mode": "plan",
                "input_paths": [str(dropped)],
            },
        )
        await fake_server.handlers["prompt"](valid_prompt, client)
        await _wait_for_request_complete(client, "req-prompt-plan-mode-valid-input-paths")

        statuses = [
            message.get("status")
            for message in client.sent
            if message.get("id") == "req-prompt-plan-mode-valid-input-paths"
            and message.get("type") == "status"
        ]
        assert "planning" in statuses
        assert "complete" in statuses
        assert not any(
            message.get("id") == "req-prompt-plan-mode-valid-input-paths"
            and message.get("type") == "error"
            for message in client.sent
        )
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_plan_mode_discovery_allowed_after_planner_bootstrap(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Verify that discovery tools succeed in Plan Mode because the planner
    bootstrap (which runs before the tool chain loop) marks the planner as
    already used.  No discovery budget enforcement should fire."""
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"q" * 32).decode("ascii"),
    )
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_DISCOVERY_BEFORE_PLANNER", "1")

    state: dict[str, int] = {"continuation_calls": 0}

    class _DiscoveryAfterBootstrapGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {"function_call": {"name": "search_files", "args": {"query": "invoice"}}}

        def send_continuation(self, **_kwargs: object) -> dict[str, object]:
            state["continuation_calls"] += 1
            if state["continuation_calls"] <= 2:
                return {"function_call": {"name": "read_text", "args": {"path": "~/ignored.txt"}}}
            return {"text": "Plan complete."}

    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DiscoveryAfterBootstrapGeminiClient))
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
        allowed_roots=[tmp_path],
    )

    run_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=8765, verbose=False)
    )

    try:
        fake_server = await _wait_for_fake_server()
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)

        request_id = "req-prompt-plan-mode-discovery-budget"
        prompt_request = IncomingRequest(
            id=request_id,
            method="prompt",
            params={
                "prompt": "I need to organize files into folders, target completion in 2 weeks, focus on invoices",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "execution_mode": "plan",
            },
        )
        await fake_server.handlers["prompt"](prompt_request, client)
        await _wait_for_request_complete(client, request_id)

        request_messages = [message for message in client.sent if message.get("id") == request_id]

        # Planner bootstrap marks planner as used before the tool chain loop,
        # so discovery tools should proceed without budget enforcement errors.
        assert not any(
            message.get("type") == "error"
            and "requires unified planning"
            in str(message.get("error", {}).get("message", "")).lower()
            for message in request_messages
        )
        assert any(
            message.get("type") == "status" and message.get("status") == "complete"
            for message in request_messages
        )
        assert state["continuation_calls"] >= 1
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_plan_mode_allows_discovery_after_planner_tool_runs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"s" * 32).decode("ascii"),
    )
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_DISCOVERY_BEFORE_PLANNER", "0")
    from agent_host.adapters.modes.plan import state_machine as plan_sm
    monkeypatch.setattr(plan_sm, "_PLAN_MODE_PLANNER_TOOLS", {"search_files"})

    readable_file = tmp_path / "allowed-read-after-planner.txt"
    readable_file.write_text("ok", encoding="utf-8")
    state: dict[str, int] = {"continuation_calls": 0}

    class _PlannerThenDiscoveryGeminiClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            return {"function_call": {"name": "search_files", "args": {"query": "invoice"}}}

        def send_continuation(self, **_kwargs: object) -> dict[str, object]:
            state["continuation_calls"] += 1
            if state["continuation_calls"] == 1:
                return {
                    "function_call": {
                        "name": "read_text",
                        "args": {"path": str(readable_file)},
                    }
                }
            return {"text": "Plan complete."}

    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_PlannerThenDiscoveryGeminiClient))
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
        allowed_roots=[tmp_path],
    )

    run_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=8765, verbose=False)
    )

    try:
        fake_server = await _wait_for_fake_server()
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)

        request_id = "req-prompt-plan-mode-post-planner-discovery"
        prompt_request = IncomingRequest(
            id=request_id,
            method="prompt",
            params={
                "prompt": "I need to organize files into folders, target completion in 2 weeks, focus on invoices",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "execution_mode": "plan",
            },
        )
        await fake_server.handlers["prompt"](prompt_request, client)
        await _wait_for_request_complete(client, request_id)

        request_messages = [message for message in client.sent if message.get("id") == request_id]

        # Plan mode hides tool call success cards.  Verify that discovery
        # after the planner ran does NOT trigger a budget enforcement error —
        # that is the meaningful behavioural invariant for this test.
        assert not any(
            message.get("type") == "error"
            and "requires unified planning"
            in str(message.get("error", {}).get("message", "")).lower()
            for message in request_messages
        )
        assert state["continuation_calls"] >= 1
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_plan_mode_requests_clarification_before_planning(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"r" * 32).decode("ascii"),
    )
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_CLARIFICATION_REQUIRED", "true")

    class _CountingGeminiClient:
        send_prompt_calls = 0

        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            type(self).send_prompt_calls += 1
            return {"text": "unexpected"}

    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_CountingGeminiClient))
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
        allowed_roots=[tmp_path],
    )

    run_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=8765, verbose=False)
    )

    try:
        fake_server = await _wait_for_fake_server()
        client = _DummyClient()
        session_id = await _create_test_session(fake_server, client)

        request_id = "req-prompt-plan-mode-clarification"
        prompt_request = IncomingRequest(
            id=request_id,
            method="prompt",
            params={
                "prompt": "Create a study plan for machine learning.",
                "model": "gemini-3-flash-preview",
                "session_id": session_id,
                "execution_mode": "plan",
            },
        )
        await fake_server.handlers["prompt"](prompt_request, client)
        await _wait_for_request_complete(client, request_id)

        request_messages = [message for message in client.sent if message.get("id") == request_id]
        statuses = [m.get("status") for m in request_messages if m.get("type") == "status"]
        assert "planning" in statuses
        assert "complete" in statuses
        assert not any(m.get("type") == "error" for m in request_messages)

        result_messages = [m for m in request_messages if m.get("type") == "result"]
        assert result_messages
        content = str(result_messages[-1].get("result", {}).get("content", ""))
        lowered = content.lower()
        assert "quick clarification" in lowered
        assert "q1." in lowered
        assert "a)" in lowered
        assert _CountingGeminiClient.send_prompt_calls == 0
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_plan_mode_clarification_reply_advances_to_planning(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"z" * 32).decode("ascii"),
    )
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_CLARIFICATION_REQUIRED", "true")

    class _CountingGeminiClient:
        send_prompt_calls = 0

        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            type(self).send_prompt_calls += 1
            return {"text": "Tailored plan ready based on your answers."}

    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_CountingGeminiClient))
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
        allowed_roots=[tmp_path],
    )

    run_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=8765, verbose=False)
    )

    try:
        fake_server = await _wait_for_fake_server()
        client = _DummyClient()

        create_request = IncomingRequest(
            id="req-create-plan-followup",
            method="session.create",
            params={"memory_mode": "on"},
        )
        await fake_server.handlers["session.create"](create_request, client)
        created = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created["session_id"])

        request_id_1 = "req-prompt-plan-clarify-1"
        prompt_request_1 = IncomingRequest(
            id=request_id_1,
            method="prompt",
            params={
                "prompt": "Create a study plan for machine learning.",
                "model": "gemini-3-flash-preview",
                "execution_mode": "plan",
                "session_id": session_id,
            },
        )
        await fake_server.handlers["prompt"](prompt_request_1, client)
        await _wait_for_request_complete(client, request_id_1)

        request_messages_1 = [message for message in client.sent if message.get("id") == request_id_1]
        result_messages_1 = [m for m in request_messages_1 if m.get("type") == "result"]
        assert result_messages_1
        content_1 = str(result_messages_1[-1].get("result", {}).get("content", ""))
        assert "quick clarification" in content_1.lower()
        assert _CountingGeminiClient.send_prompt_calls == 0

        request_id_2 = "req-prompt-plan-clarify-2"
        prompt_request_2 = IncomingRequest(
            id=request_id_2,
            method="prompt",
            params={
                "prompt": "Q1:B",
                "model": "gemini-3-flash-preview",
                "execution_mode": "plan",
                "session_id": session_id,
            },
        )
        await fake_server.handlers["prompt"](prompt_request_2, client)
        await _wait_for_request_complete(client, request_id_2)

        request_messages_2 = [message for message in client.sent if message.get("id") == request_id_2]
        result_messages_2 = [m for m in request_messages_2 if m.get("type") == "result"]
        assert result_messages_2
        content_2 = str(result_messages_2[-1].get("result", {}).get("content", ""))
        lowered_2 = content_2.lower()
        assert "quick clarification" not in lowered_2
        assert "plan mode (planning only)" in lowered_2
        assert "tailored plan ready" in lowered_2
        assert _CountingGeminiClient.send_prompt_calls == 1
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_prompt_plan_mode_clarification_reply_does_not_loop_when_model_reasks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"m" * 32).decode("ascii"),
    )
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_CLARIFICATION_REQUIRED", "true")

    class _LoopingClarificationGeminiClient:
        send_prompt_calls = 0
        continuation_calls = 0

        def __init__(self, **_kwargs: object) -> None:
            pass

        def send_prompt_with_tools(self, **_kwargs: object) -> dict[str, object]:
            type(self).send_prompt_calls += 1
            return {
                "text": (
                    "To ensure the plan is tailored, please answer the following clarification questions:\n"
                    "- What timeline works best?\n"
                    "- What baseline should I assume?\n"
                )
            }

        def send_continuation(self, **_kwargs: object) -> dict[str, object]:
            type(self).continuation_calls += 1
            return {
                "text": (
                    "Tailored final plan:\n"
                    "1. Week 1-2 setup and inventory.\n"
                    "2. Week 3-4 safe organization with verification checkpoints.\n"
                    "3. Week 5-6 rollback validation and final cleanup."
                )
            }

    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_LoopingClarificationGeminiClient))
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
        allowed_roots=[tmp_path],
    )

    run_task = asyncio.create_task(
        main_module.run_server(config=config, host="127.0.0.1", port=8765, verbose=False)
    )

    try:
        fake_server = await _wait_for_fake_server(timeout_seconds=10.0)
        client = _DummyClient()

        create_request = IncomingRequest(
            id="req-create-plan-loop-guard",
            method="session.create",
            params={"memory_mode": "on"},
        )
        await fake_server.handlers["session.create"](create_request, client)
        created = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created["session_id"])

        request_id_1 = "req-plan-loop-guard-1"
        prompt_request_1 = IncomingRequest(
            id=request_id_1,
            method="prompt",
            params={
                "prompt": "Create a practical study plan for machine learning.",
                "model": "gemini-3-flash-preview",
                "execution_mode": "plan",
                "session_id": session_id,
            },
        )
        await fake_server.handlers["prompt"](prompt_request_1, client)
        await _wait_for_request_complete(client, request_id_1)

        result_messages_1 = [
            m for m in client.sent if m.get("id") == request_id_1 and m.get("type") == "result"
        ]
        assert result_messages_1
        content_1 = str(result_messages_1[-1].get("result", {}).get("content", ""))
        assert "quick clarification" in content_1.lower()

        request_id_2 = "req-plan-loop-guard-2"
        prompt_request_2 = IncomingRequest(
            id=request_id_2,
            method="prompt",
            params={
                "prompt": "Q1:B, Q2:C, Q3:B, Q4:D",
                "model": "gemini-3-flash-preview",
                "execution_mode": "plan",
                "session_id": session_id,
            },
        )
        await fake_server.handlers["prompt"](prompt_request_2, client)
        await _wait_for_request_complete(client, request_id_2)

        result_messages_2 = [
            m for m in client.sent if m.get("id") == request_id_2 and m.get("type") == "result"
        ]
        assert result_messages_2
        content_2 = str(result_messages_2[-1].get("result", {}).get("content", ""))
        lowered_2 = content_2.lower()
        assert "tailored final plan" in lowered_2
        assert "quick clarification" not in lowered_2
        assert _LoopingClarificationGeminiClient.send_prompt_calls == 1
        assert _LoopingClarificationGeminiClient.continuation_calls >= 1
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_session_create_and_history_reject_invalid_memory_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"t" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        client = _DummyClient()

        bad_create_request = IncomingRequest(
            id="req-create-invalid-mode",
            method="session.create",
            params={"memory_mode": "bad-mode"},
        )
        await fake_server.handlers["session.create"](bad_create_request, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600

        client.sent.clear()
        create_request = IncomingRequest(
            id="req-create-valid-mode",
            method="session.create",
            params={"memory_mode": "off"},
        )
        await fake_server.handlers["session.create"](create_request, client)
        created = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created["session_id"])

        client.sent.clear()
        bad_history_request = IncomingRequest(
            id="req-history-invalid-mode",
            method="session.history",
            params={"session_id": session_id, "memory_mode": "bad-mode"},
        )
        await fake_server.handlers["session.history"](bad_history_request, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "no longer accepts memory_mode" in str(
            client.sent[0].get("error", {}).get("message", "")
        ).lower()
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


# ---------------------------------------------------------------------------
# _is_plan_mode_followup unit tests
# ---------------------------------------------------------------------------

def test_is_plan_mode_followup_affirmatives():
    """Short affirmative replies are follow-ups when a plan exists."""
    fn = plan_mode_module._is_plan_mode_followup
    for phrase in ("yes", "Yes!", "ok", "sure", "go ahead", "proceed", "do it", "let's go"):
        assert fn(phrase, session_has_plan=True), f"Expected followup for: {phrase!r}"


def test_is_plan_mode_followup_negatives():
    """Negative/hold replies are also follow-ups (not new plans)."""
    fn = plan_mode_module._is_plan_mode_followup
    for phrase in ("no", "wait", "hold", "cancel", "revise", "adjust"):
        assert fn(phrase, session_has_plan=True), f"Expected followup for: {phrase!r}"


def test_is_plan_mode_followup_questions():
    """Short conversational questions are follow-ups."""
    fn = plan_mode_module._is_plan_mode_followup
    assert fn("what about duplicates?", session_has_plan=True)
    assert fn("can you also handle PDFs?", session_has_plan=True)


def test_is_plan_mode_followup_no_plan():
    """Without an existing plan, nothing is a follow-up."""
    fn = plan_mode_module._is_plan_mode_followup
    assert not fn("yes", session_has_plan=False)
    assert not fn("go ahead", session_has_plan=False)


def test_is_plan_mode_followup_new_planning_request():
    """A prompt with goal signals is a new planning request, not a follow-up."""
    fn = plan_mode_module._is_plan_mode_followup
    assert not fn("reorganize my photos by date into yearly folders", session_has_plan=True)
    assert not fn("plan to migrate all documents to cloud storage", session_has_plan=True)


def test_is_plan_mode_execution_approval_affirmatives():
    """Affirmative approvals are detected for auto-execute."""
    fn = plan_mode_module._is_plan_mode_execution_approval
    for phrase in ("yes", "Yes!", "ok", "sure", "go ahead", "proceed", "do it",
                   "let's go", "sounds good", "perfect", "great", "approved", "confirmed"):
        assert fn(phrase), f"Expected approval for: {phrase!r}"


def test_is_plan_mode_execution_approval_non_approvals():
    """Non-approval follow-ups should not trigger auto-execute."""
    fn = plan_mode_module._is_plan_mode_execution_approval
    for phrase in ("what about duplicates?", "can you also handle PDFs?",
                   "no", "wait", "revise the plan", "actually change step 2"):
        assert not fn(phrase), f"Should NOT be approval: {phrase!r}"


@pytest.mark.anyio
async def test_notes_update_rejects_non_boolean_is_pinned(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"z" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        client = _DummyClient()

        create_session = IncomingRequest(
            id="req-create-note-update-bool",
            method="session.create",
            params={"memory_mode": "on"},
        )
        await fake_server.handlers["session.create"](create_session, client)
        created_session = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        session_id = str(created_session["session_id"])

        create_note = IncomingRequest(
            id="req-create-note-update-bool-note",
            method="notes.create",
            params={"session_id": session_id, "content": "hello"},
        )
        await fake_server.handlers["notes.create"](create_note, client)
        created_note = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
        note_id = str(created_note["note_id"])

        client.sent.clear()
        update_note = IncomingRequest(
            id="req-update-note-invalid-bool",
            method="notes.update",
            params={
                "session_id": session_id,
                "note_id": note_id,
                "is_pinned": "false",
            },
        )
        await fake_server.handlers["notes.update"](update_note, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "invalid is_pinned" in str(
            client.sent[0].get("error", {}).get("message", "")
        ).lower()
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_notes_delete_rejects_unknown_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"1" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        client = _DummyClient()
        delete_note = IncomingRequest(
            id="req-delete-note-unknown-session",
            method="notes.delete",
            params={"session_id": "unknown-session", "note_id": "note-1"},
        )
        await fake_server.handlers["notes.delete"](delete_note, client)
        assert client.sent and client.sent[0].get("type") == "error"
        assert client.sent[0].get("error", {}).get("code") == -32600
        assert "unknown session" in str(
            client.sent[0].get("error", {}).get("message", "")
        ).lower()
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS


@pytest.mark.anyio
async def test_session_list_limit_zero_returns_all_saved_sessions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(
        "AI_AGENT_MEMORY_MASTER_KEY_B64",
        base64.b64encode(b"2" * 32).decode("ascii"),
    )
    monkeypatch.setattr(main_module, "GeminiClient", _continuation_ready_client(_DummyGeminiClient))
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
        client = _DummyClient()
        created_session_ids: list[str] = []

        for index in range(3):
            request = IncomingRequest(
                id=f"req-create-session-{index}",
                method="session.create",
                params={"title": f"Session {index}", "memory_mode": "ephemeral"},
            )
            await fake_server.handlers["session.create"](request, client)
            payload = json.loads(client.sent[-1].get("result", {}).get("content", "{}"))
            created_session_ids.append(str(payload["session_id"]))

        client.sent.clear()
        list_request = IncomingRequest(
            id="req-list-all-sessions",
            method="session.list",
            params={"limit": 0},
        )
        await fake_server.handlers["session.list"](list_request, client)

        assert client.sent and client.sent[0].get("type") == "result"
        sessions = json.loads(client.sent[0].get("result", {}).get("content", "[]"))
        returned_ids = {str(row.get("session_id")) for row in sessions}
        assert set(created_session_ids).issubset(returned_ids)
    finally:
        latest = _FakeServer.latest
        if latest is not None:
            latest.release()
        result = await asyncio.wait_for(run_task, timeout=5.0)
        assert result == main_module.EXIT_SUCCESS
