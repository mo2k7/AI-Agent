"""Additional JSON-RPC framing and invalid-message hardening tests."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path

import pytest

from agent_host.ipc.server import IPCServer
from tests.unit.websocket_test_harness import connect_line_transport, reserve_tcp_port


class _DummyClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(json.loads(data.decode("utf-8")))


@pytest.mark.anyio
async def test_invalid_params_shape_does_not_crash_dispatch() -> None:
    server = IPCServer()
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
    del tmp_path
    port = reserve_tcp_port()
    endpoint_url = f"ws://127.0.0.1:{port}"
    server = IPCServer(host="127.0.0.1", port=port)
    server_task = asyncio.create_task(server.serve_forever())

    try:
        reader, writer = await _connect_transport(endpoint_url)
        try:
            writer.write(b"a" * (IPCServer.MAX_INCOMING_BUFFER + 128))
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=3.0)
            assert line == b""
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
    server = IPCServer(
        host="127.0.0.1",
        port=reserve_tcp_port(),
        require_auth=True,
        auth_token="secret-token",
    )
    server_task = asyncio.create_task(server.serve_forever())

    try:
        reader, writer = await _connect_transport(server.endpoint_url)
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
    server = IPCServer(
        host="127.0.0.1",
        port=reserve_tcp_port(),
        require_auth=True,
        auth_token="secret-token",
    )
    server_task = asyncio.create_task(server.serve_forever())

    try:
        reader, writer = await _connect_transport(server.endpoint_url)
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
async def test_server_start_binds_ephemeral_port_and_stop_clears_running_state(tmp_path: Path) -> None:
    del tmp_path
    server = IPCServer(host="127.0.0.1", port=0)
    await server.start()
    try:
        assert server.is_running is True
        assert server.endpoint_url.startswith("ws://127.0.0.1:")
    finally:
        await server.stop()

    assert server.is_running is False


async def _connect_transport(endpoint_url: str, timeout_seconds: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        try:
            return await connect_line_transport(endpoint_url)
        except OSError:
            await asyncio.sleep(0.02)
    raise TimeoutError(f"WebSocket endpoint did not become ready in time: {endpoint_url}")
