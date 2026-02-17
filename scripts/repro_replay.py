#!/usr/bin/env python3
"""Replay deterministic RPC sequences and optionally bisect failing steps."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a captured JSON-RPC failure sequence")
    parser.add_argument("--replay", required=True, help="Path to replay JSON file")
    parser.add_argument("--socket-path", required=True, help="Unix socket path")
    parser.add_argument("--bisect", action="store_true", help="Find minimal failing prefix")
    parser.add_argument("--timeout", type=float, default=2.0, help="Per-read timeout seconds")
    return parser.parse_args()


async def _read_message(reader: asyncio.StreamReader, timeout: float) -> dict[str, Any]:
    raw = await asyncio.wait_for(reader.readline(), timeout=timeout)
    if not raw:
        raise RuntimeError("backend closed connection")
    return json.loads(raw.decode("utf-8"))


async def _run_steps(
    *,
    socket_path: str,
    steps: list[dict[str, Any]],
    timeout: float,
) -> tuple[bool, str]:
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    try:
        for step in steps:
            action = str(step.get("action", "")).strip()
            if action == "open":
                if writer is not None:
                    writer.close()
                    await writer.wait_closed()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(socket_path),
                    timeout=timeout,
                )
                continue
            if action == "close":
                if writer is not None:
                    writer.close()
                    await writer.wait_closed()
                    reader = None
                    writer = None
                continue
            if writer is None or reader is None:
                return False, f"action '{action}' requires open connection"
            if action == "send":
                payload = step.get("payload")
                writer.write((json.dumps(payload) + "\n").encode("utf-8"))
                await writer.drain()
                continue
            if action == "send_batch":
                payload = step.get("payload")
                if not isinstance(payload, list):
                    return False, "send_batch payload must be list"
                for entry in payload:
                    writer.write((json.dumps(entry) + "\n").encode("utf-8"))
                await writer.drain()
                continue
            if action == "send_raw":
                payload = str(step.get("payload", ""))
                newline = bool(step.get("newline", False))
                writer.write(payload.encode("utf-8"))
                if newline:
                    writer.write(b"\n")
                await writer.drain()
                continue
            if action == "expect":
                expected_type = step.get("type")
                expected_id = step.get("id")
                message = await _read_message(reader, timeout)
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
                    message = await _read_message(reader, timeout)
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
        if writer is not None:
            writer.close()
            await writer.wait_closed()


async def _bisect_failing_prefix(
    *,
    socket_path: str,
    steps: list[dict[str, Any]],
    timeout: float,
) -> tuple[int, str]:
    failing_index = len(steps)
    failing_reason = "full sequence passed"
    for idx in range(1, len(steps) + 1):
        ok, reason = await _run_steps(socket_path=socket_path, steps=steps[:idx], timeout=timeout)
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

    ok, reason = await _run_steps(socket_path=args.socket_path, steps=steps, timeout=args.timeout)
    summary: dict[str, Any] = {
        "replay": str(replay_path),
        "socket_path": args.socket_path,
        "ok": ok,
        "reason": reason,
    }

    if args.bisect:
        index, bisect_reason = await _bisect_failing_prefix(
            socket_path=args.socket_path,
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
