"""Additional JSON-RPC framing and invalid-message hardening tests."""

from __future__ import annotations

import asyncio
import json
import socket
import uuid
from contextlib import suppress
from pathlib import Path

import pytest

from agent_host.ipc.server import IPCServer


class _DummyClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(json.loads(data.decode("utf-8")))


@pytest.mark.anyio
async def test_invalid_params_shape_does_not_crash_dispatch() -> None:
    server = IPCServer(socket_path="/tmp/pytest-ai-agent-invalid-params.sock")
    client = _DummyClient()

    # params is intentionally invalid (array instead of object).
    message = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "req-invalid-params-shape",
            "method": "method.unknown",
            "params": ["bad-shape"],
        }
    )

    await server._handle_message("client-test", client, message)

    assert len(client.sent) == 1
    payload = client.sent[0]
    assert payload["id"] == "req-invalid-params-shape"
    assert payload["type"] == "error"
    assert payload["error"]["code"] == -32601


@pytest.mark.anyio
async def test_oversized_unframed_payload_is_rejected(tmp_path: Path) -> None:
    socket_path = Path(f"/tmp/ai-agent-ipc-fuzz-{uuid.uuid4().hex[:8]}.sock")
    server = IPCServer(socket_path=str(socket_path))
    server_task = asyncio.create_task(server.serve_forever())

    try:
        deadline = asyncio.get_running_loop().time() + 5.0
        while not socket_path.exists() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)
        assert socket_path.exists()

        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        try:
            writer.write(b"a" * (IPCServer.MAX_INCOMING_BUFFER + 128))
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=3.0)
            assert line
            payload = json.loads(line.decode("utf-8"))
            assert payload["type"] == "error"
            assert payload["error"]["code"] == -32700
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await server.stop()
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await server_task


@pytest.mark.anyio
async def test_auth_required_rejects_non_auth_first_request() -> None:
    socket_path = Path(f"/tmp/ai-agent-ipc-auth-{uuid.uuid4().hex[:8]}.sock")
    server = IPCServer(
        socket_path=str(socket_path),
        require_auth=True,
        auth_token="secret-token",
    )
    server_task = asyncio.create_task(server.serve_forever())

    try:
        deadline = asyncio.get_running_loop().time() + 5.0
        while not socket_path.exists() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)
        assert socket_path.exists()

        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": "req-no-auth",
                "method": "ping",
                "params": {},
            }
            writer.write((json.dumps(payload) + "\n").encode("utf-8"))
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=3.0)
            assert line
            response = json.loads(line.decode("utf-8"))
            assert response["type"] == "error"
            assert response["error"]["code"] == -32010
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await server.stop()
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await server_task


@pytest.mark.anyio
async def test_auth_hello_rejects_invalid_token() -> None:
    socket_path = Path(f"/tmp/ai-agent-ipc-auth-mismatch-{uuid.uuid4().hex[:8]}.sock")
    server = IPCServer(
        socket_path=str(socket_path),
        require_auth=True,
        auth_token="secret-token",
    )
    server_task = asyncio.create_task(server.serve_forever())

    try:
        deadline = asyncio.get_running_loop().time() + 5.0
        while not socket_path.exists() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)
        assert socket_path.exists()

        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": "req-auth",
                "method": "auth.hello",
                "params": {
                    "protocol_version": "2.0.0",
                    "client_name": "pytest",
                    "client_pid": 123,
                    "auth_token": "wrong-token",
                },
            }
            writer.write((json.dumps(payload) + "\n").encode("utf-8"))
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=3.0)
            assert line
            response = json.loads(line.decode("utf-8"))
            assert response["type"] == "error"
            assert response["error"]["code"] == -32011
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await server.stop()
        server_task.cancel()
        with suppress(asyncio.CancelledError):
            await server_task


@pytest.mark.anyio
async def test_server_start_refuses_non_socket_unlink(tmp_path: Path) -> None:
    socket_path = tmp_path / "ipc.sock"
    socket_path.write_text("not-a-socket", encoding="utf-8")
    server = IPCServer(socket_path=str(socket_path))

    with pytest.raises(RuntimeError, match="Refusing to remove non-socket path"):
        await server.start()

    assert socket_path.exists()


@pytest.mark.anyio
async def test_server_start_replaces_stale_socket_file() -> None:
    socket_path = Path(f"/tmp/ai-agent-stale-{uuid.uuid4().hex[:8]}.sock")
    socket_path.unlink(missing_ok=True)
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        stale.bind(str(socket_path))
    finally:
        stale.close()
    assert socket_path.exists()

    server = IPCServer(socket_path=str(socket_path))
    await server.start()
    try:
        assert socket_path.exists()
    finally:
        await server.stop()

    assert not socket_path.exists()
