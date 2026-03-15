#!/usr/bin/env python3
"""Replay deterministic RPC sequences and optionally bisect failing steps."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from websockets.asyncio.client import connect

PROTOCOL_VERSION = "2.0.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a captured JSON-RPC failure sequence")
    parser.add_argument("--replay", required=True, help="Path to replay JSON file")
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("AI_AGENT_BACKEND_URL", "ws://127.0.0.1:8765"),
        help="WebSocket backend URL",
    )
    parser.add_argument(
        "--auth-token",
        default=os.environ.get("AI_AGENT_IPC_AUTH_TOKEN", ""),
        help="Auth token used for auth.hello",
    )
    parser.add_argument("--bisect", action="store_true", help="Find minimal failing prefix")
    parser.add_argument("--timeout", type=float, default=2.0, help="Per-read timeout seconds")
    return parser.parse_args()


async def _read_message(websocket, timeout: float) -> dict[str, Any]:
    raw = await asyncio.wait_for(websocket.recv(), timeout=timeout)
    if raw is None:
        raise RuntimeError("backend closed connection")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


async def _authenticate(websocket, *, auth_token: str, timeout: float) -> None:
    if not auth_token:
        return
    request_id = "replay-auth"
    await websocket.send(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "auth.hello",
                "params": {
                    "client_name": "repro_replay",
                    "client_pid": os.getpid(),
                    "protocol_version": PROTOCOL_VERSION,
                    "auth_token": auth_token,
                },
            }
        )
    )
    message = await _read_message(websocket, timeout)
    if message.get("id") != request_id or message.get("type") != "result":
        raise RuntimeError(f"auth.hello failed: {message}")


async def _run_steps(
    *,
    backend_url: str,
    auth_token: str,
    steps: list[dict[str, Any]],
    timeout: float,
) -> tuple[bool, str]:
    websocket = None
    try:
        for step in steps:
            action = str(step.get("action", "")).strip()
            if action == "open":
                if websocket is not None:
                    await websocket.close()
                websocket = await asyncio.wait_for(connect(backend_url, max_size=16 * 1_048_576), timeout=timeout)
                await _authenticate(websocket, auth_token=auth_token, timeout=timeout)
                continue
            if action == "close":
                if websocket is not None:
                    await websocket.close()
                    websocket = None
                continue
            if websocket is None:
                return False, f"action '{action}' requires open connection"
            if action == "send":
                await websocket.send(json.dumps(step.get("payload")))
                continue
            if action == "send_batch":
                payload = step.get("payload")
                if not isinstance(payload, list):
                    return False, "send_batch payload must be list"
                for entry in payload:
                    await websocket.send(json.dumps(entry))
                continue
            if action == "send_raw":
                await websocket.send(str(step.get("payload", "")))
                continue
            if action == "expect":
                expected_type = step.get("type")
                expected_id = step.get("id")
                message = await _read_message(websocket, timeout)
                if expected_type == "error_or_disconnect":
                    if message.get("type") != "error":
                        return False, f"expected error_or_disconnect, got {message}"
                else:
                    if expected_type and message.get("type") != expected_type:
                        return False, f"expected type={expected_type}, got {message.get('type')}"
                    if expected_id and message.get("id") != expected_id:
                        return False, f"expected id={expected_id}, got {message.get('id')}"
                continue
            if action == "expect_many":
                ids_raw = step.get("ids")
                if not isinstance(ids_raw, list):
                    return False, "expect_many requires ids list"
                expected_ids = {str(item) for item in ids_raw}
                seen: set[str] = set()
                deadline = asyncio.get_running_loop().time() + timeout * max(2, len(expected_ids))
                while expected_ids - seen and asyncio.get_running_loop().time() < deadline:
                    message = await _read_message(websocket, timeout)
                    response_id = message.get("id")
                    if isinstance(response_id, str):
                        seen.add(response_id)
                if expected_ids - seen:
                    return False, f"missing ids: {sorted(expected_ids - seen)}"
                continue
            return False, f"unknown action: {action}"
        return True, "ok"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        if websocket is not None:
            await websocket.close()


async def _bisect_failing_prefix(
    *,
    backend_url: str,
    auth_token: str,
    steps: list[dict[str, Any]],
    timeout: float,
) -> tuple[int, str]:
    failing_index = len(steps)
    failing_reason = "full sequence passed"
    for idx in range(1, len(steps) + 1):
        ok, reason = await _run_steps(
            backend_url=backend_url,
            auth_token=auth_token,
            steps=steps[:idx],
            timeout=timeout,
        )
        if not ok:
            failing_index = idx
            failing_reason = reason
            break
    return failing_index, failing_reason


async def _main() -> int:
    args = parse_args()
    replay_path = Path(args.replay)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    steps = replay.get("steps", [])
    if not isinstance(steps, list):
        raise RuntimeError("Replay file is missing a valid steps list")

    ok, reason = await _run_steps(
        backend_url=args.backend_url,
        auth_token=args.auth_token,
        steps=steps,
        timeout=args.timeout,
    )
    summary: dict[str, Any] = {
        "replay": str(replay_path),
        "backend_url": args.backend_url,
        "ok": ok,
        "reason": reason,
    }

    if args.bisect:
        index, bisect_reason = await _bisect_failing_prefix(
            backend_url=args.backend_url,
            auth_token=args.auth_token,
            steps=steps,
            timeout=args.timeout,
        )
        summary["bisect_first_failing_step"] = index
        summary["bisect_reason"] = bisect_reason

    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
