from __future__ import annotations

import asyncio
import socket

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


def reserve_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class WebSocketLineReader:
    def __init__(self, websocket) -> None:
        self._websocket = websocket

    async def readline(self) -> bytes:
        try:
            raw = await self._websocket.recv()
        except ConnectionClosed:
            return b""
        if isinstance(raw, bytes):
            return raw + (b"" if raw.endswith(b"\n") else b"\n")
        encoded = raw.encode("utf-8")
        return encoded + (b"" if encoded.endswith(b"\n") else b"\n")


class WebSocketLineWriter:
    def __init__(self, websocket) -> None:
        self._websocket = websocket
        self._buffer = bytearray()
        self._close_task: asyncio.Task[None] | None = None

    def write(self, data: bytes) -> None:
        self._buffer.extend(data)

    async def drain(self) -> None:
        if not self._buffer:
            return
        payload = bytes(self._buffer)
        self._buffer.clear()

        if b"\n" in payload:
            frames = payload.splitlines()
            for frame in frames:
                if not frame:
                    continue
                await self._send_frame(frame)
            return

        await self._send_frame(payload)

    async def _send_frame(self, payload: bytes) -> None:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            await self._websocket.send(payload)
            return
        await self._websocket.send(text)

    def close(self) -> None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._websocket.close())

    async def wait_closed(self) -> None:
        if self._close_task is None:
            self.close()
        assert self._close_task is not None
        await self._close_task


async def connect_line_transport(endpoint_url: str) -> tuple[WebSocketLineReader, WebSocketLineWriter]:
    websocket = await connect(endpoint_url, max_size=16 * 1_048_576)
    return WebSocketLineReader(websocket), WebSocketLineWriter(websocket)
