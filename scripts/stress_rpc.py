#!/usr/bin/env python3
"""Deterministic JSON-RPC stress harness for the Unix socket backend."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import random
import string
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ScenarioResult:
    name: str
    success: bool
    error: str | None
    elapsed_ms: float
    sequence: list[dict[str, Any]]


class StressHarness:
    def __init__(
        self,
        *,
        socket_path: str,
        duration: int,
        concurrency: int,
        seed: int,
        run_dir: Path,
        scenarios: list[str] | None = None,
        ops_per_worker: int | None = None,
    ) -> None:
        self.socket_path = socket_path
        self.duration = max(1, duration)
        self.concurrency = max(1, concurrency)
        self.seed = seed
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.ops_per_worker = max(1, ops_per_worker if ops_per_worker is not None else self.duration * 2)
        self.events_path = self.run_dir / "stress_events.jsonl"
        self.report_path = self.run_dir / "stress_report.json"
        self._request_counter = 0
        self._counter_lock = asyncio.Lock()
        self.results: list[ScenarioResult] = []
        self.scenario_names = scenarios or [
            "ping_valid",
            "session_create_valid",
            "unknown_method",
            "malformed_json",
            "partial_frame_disconnect",
            "huge_payload",
            "out_of_order_ids",
            "duplicate_ids",
            "disconnect_mid_request",
        ]

    async def run(self) -> dict[str, Any]:
        started = time.time()
        plan_rng = random.Random(self.seed)
        worker_tasks = []
        for worker_idx in range(self.concurrency):
            worker_seed = plan_rng.randint(0, 2**31 - 1) ^ worker_idx
            plan = build_worker_plan(
                seed=worker_seed,
                operations=self.ops_per_worker,
                scenarios=self.scenario_names,
            )
            worker_tasks.append(
                asyncio.create_task(
                    self._worker(
                        worker_idx=worker_idx,
                        plan=plan,
                    )
                )
            )

        await asyncio.gather(*worker_tasks)

        ended = time.time()
        failures = [r for r in self.results if not r.success]
        successes = [r for r in self.results if r.success]
        per_scenario: dict[str, dict[str, int]] = {}
        for entry in self.results:
            bucket = per_scenario.setdefault(entry.name, {"pass": 0, "fail": 0})
            key = "pass" if entry.success else "fail"
            bucket[key] += 1

        report: dict[str, Any] = {
            "started_at": started,
            "ended_at": ended,
            "duration_seconds": round(ended - started, 3),
            "seed": self.seed,
            "socket_path": self.socket_path,
            "concurrency": self.concurrency,
            "operations_per_worker": self.ops_per_worker,
            "total_operations": len(self.results),
            "successful_operations": len(successes),
            "failed_operations": len(failures),
            "per_scenario": per_scenario,
            "failures": [
                {
                    "scenario": f.name,
                    "error": f.error,
                    "elapsed_ms": round(f.elapsed_ms, 3),
                    "sequence": f.sequence,
                }
                for f in failures[:50]
            ],
            "first_failure_sequence": failures[0].sequence if failures else [],
        }
        self.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    async def _worker(self, *, worker_idx: int, plan: list[str]) -> None:
        rng = random.Random(self.seed ^ worker_idx)
        for op_idx, scenario in enumerate(plan):
            started = time.perf_counter()
            sequence: list[dict[str, Any]] = []
            error: str | None = None
            success = False
            try:
                success, sequence = await self._run_scenario(
                    scenario=scenario,
                    worker_idx=worker_idx,
                    op_idx=op_idx,
                    rng=rng,
                )
            except Exception as exc:  # pragma: no cover - defensive
                error = f"{type(exc).__name__}: {exc}"
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if error is None and not success:
                error = "scenario assertion failed"
            result = ScenarioResult(
                name=scenario,
                success=success,
                error=error,
                elapsed_ms=elapsed_ms,
                sequence=sequence,
            )
            self.results.append(result)
            self._append_event(
                {
                    "worker": worker_idx,
                    "op_index": op_idx,
                    "scenario": scenario,
                    "success": success,
                    "error": error,
                    "elapsed_ms": round(elapsed_ms, 3),
                    "sequence": sequence,
                }
            )

    async def _next_request_id(self, prefix: str) -> str:
        async with self._counter_lock:
            self._request_counter += 1
            idx = self._request_counter
        return f"{prefix}-{idx}"

    async def _run_scenario(
        self,
        *,
        scenario: str,
        worker_idx: int,
        op_idx: int,
        rng: random.Random,
    ) -> tuple[bool, list[dict[str, Any]]]:
        if scenario == "ping_valid":
            return await self._scenario_ping_valid()
        if scenario == "session_create_valid":
            return await self._scenario_session_create_valid()
        if scenario == "unknown_method":
            return await self._scenario_unknown_method()
        if scenario == "malformed_json":
            return await self._scenario_malformed_json(worker_idx=worker_idx, op_idx=op_idx)
        if scenario == "partial_frame_disconnect":
            return await self._scenario_partial_frame_disconnect(worker_idx=worker_idx, op_idx=op_idx)
        if scenario == "huge_payload":
            return await self._scenario_huge_payload(rng=rng)
        if scenario == "out_of_order_ids":
            return await self._scenario_out_of_order_ids()
        if scenario == "duplicate_ids":
            return await self._scenario_duplicate_ids()
        if scenario == "disconnect_mid_request":
            return await self._scenario_disconnect_mid_request(worker_idx=worker_idx, op_idx=op_idx)
        return False, [{"action": "error", "message": f"unknown scenario {scenario}"}]

    async def _open(self, *, timeout: float = 2.0, retries: int = 3) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        last_error: Exception | None = None
        for attempt in range(max(1, retries)):
            try:
                return await asyncio.wait_for(
                    asyncio.open_unix_connection(self.socket_path),
                    timeout=timeout,
                )
            except (TimeoutError, ConnectionRefusedError, FileNotFoundError, OSError) as exc:
                last_error = exc
                if attempt >= retries - 1:
                    break
                await asyncio.sleep(0.05 * (attempt + 1))
        if last_error is None:  # pragma: no cover - defensive
            raise RuntimeError("socket connection failed without an explicit error")
        raise last_error

    async def _close_writer(self, writer: asyncio.StreamWriter) -> None:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()

    async def _read_message(self, reader: asyncio.StreamReader, timeout: float = 2.0) -> dict[str, Any]:
        raw = await asyncio.wait_for(reader.readline(), timeout=timeout)
        if not raw:
            raise RuntimeError("backend closed connection")
        return json.loads(raw.decode("utf-8"))

    async def _scenario_ping_valid(self) -> tuple[bool, list[dict[str, Any]]]:
        request_id = await self._next_request_id("ping")
        request = {"jsonrpc": "2.0", "id": request_id, "method": "ping"}
        sequence: list[dict[str, Any]] = [
            {"action": "open"},
            {"action": "send", "payload": request},
            {"action": "expect", "type": "result", "id": request_id},
            {"action": "close"},
        ]
        reader, writer = await self._open(timeout=4.0, retries=4)
        try:
            writer.write((json.dumps(request) + "\n").encode("utf-8"))
            await writer.drain()
            message = await self._read_message(reader, timeout=4.0)
            ok = message.get("id") == request_id and message.get("type") == "result"
            return ok, sequence
        finally:
            await self._close_writer(writer)

    async def _scenario_session_create_valid(self) -> tuple[bool, list[dict[str, Any]]]:
        request_id = await self._next_request_id("session-create")
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "session.create",
            "params": {"memory_mode": "ephemeral"},
        }
        sequence: list[dict[str, Any]] = [
            {"action": "open"},
            {"action": "send", "payload": request},
            {"action": "expect", "type": "result", "id": request_id},
            {"action": "close"},
        ]
        reader, writer = await self._open(timeout=4.0, retries=4)
        try:
            writer.write((json.dumps(request) + "\n").encode("utf-8"))
            await writer.drain()
            message = await self._read_message(reader, timeout=4.0)
            if message.get("id") != request_id or message.get("type") != "result":
                return False, sequence
            content = (
                message.get("result", {}).get("content")
                if isinstance(message.get("result"), dict)
                else None
            )
            if not isinstance(content, str):
                return False, sequence
            payload = json.loads(content)
            return isinstance(payload.get("session_id"), str), sequence
        finally:
            await self._close_writer(writer)

    async def _scenario_unknown_method(self) -> tuple[bool, list[dict[str, Any]]]:
        request_id = await self._next_request_id("unknown")
        request = {"jsonrpc": "2.0", "id": request_id, "method": "method.does_not_exist"}
        sequence: list[dict[str, Any]] = [
            {"action": "open"},
            {"action": "send", "payload": request},
            {"action": "expect", "type": "error", "id": request_id},
            {"action": "close"},
        ]
        reader, writer = await self._open()
        try:
            writer.write((json.dumps(request) + "\n").encode("utf-8"))
            await writer.drain()
            message = await self._read_message(reader)
            return (
                message.get("id") == request_id
                and message.get("type") == "error"
                and isinstance(message.get("error"), dict)
            ), sequence
        finally:
            await self._close_writer(writer)

    async def _scenario_malformed_json(self, *, worker_idx: int, op_idx: int) -> tuple[bool, list[dict[str, Any]]]:
        malformed = f'{{"jsonrpc":"2.0","id":"malformed-{worker_idx}-{op_idx}","method":'
        sequence: list[dict[str, Any]] = [
            {"action": "open"},
            {"action": "send_raw", "payload": malformed, "newline": True},
            {"action": "expect", "type": "error"},
            {"action": "close"},
        ]
        reader, writer = await self._open()
        try:
            writer.write((malformed + "\n").encode("utf-8"))
            await writer.drain()
            message = await self._read_message(reader)
            return message.get("type") == "error", sequence
        finally:
            await self._close_writer(writer)

    async def _scenario_partial_frame_disconnect(
        self,
        *,
        worker_idx: int,
        op_idx: int,
    ) -> tuple[bool, list[dict[str, Any]]]:
        request = {
            "jsonrpc": "2.0",
            "id": f"partial-{worker_idx}-{op_idx}",
            "method": "ping",
        }
        raw = json.dumps(request)
        cut = max(1, len(raw) // 2)
        sequence: list[dict[str, Any]] = [
            {"action": "open"},
            {"action": "send_raw", "payload": raw[:cut], "newline": False},
            {"action": "close"},
        ]
        _reader, writer = await self._open()
        writer.write(raw[:cut].encode("utf-8"))
        await writer.drain()
        await self._close_writer(writer)
        # Backend should remain healthy after partial frame close.
        ping_ok, _ = await self._scenario_ping_valid()
        return ping_ok, sequence

    async def _scenario_huge_payload(self, *, rng: random.Random) -> tuple[bool, list[dict[str, Any]]]:
        request_id = await self._next_request_id("huge")
        payload = "".join(rng.choice(string.ascii_letters) for _ in range(1_200_000))
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "method.huge_payload",
            "params": {"blob": payload},
        }
        sequence: list[dict[str, Any]] = [
            {"action": "open"},
            {"action": "send", "payload": {"jsonrpc": "2.0", "id": request_id, "method": "method.huge_payload", "params": {"blob_len": len(payload)}}},
            {"action": "expect", "type": "error_or_disconnect"},
            {"action": "close"},
        ]
        reader, writer = await self._open()
        try:
            try:
                writer.write((json.dumps(request) + "\n").encode("utf-8"))
                await writer.drain()
            except (BrokenPipeError, ConnectionResetError):
                # Accept immediate disconnects as success: backend rejected oversized payload.
                return True, sequence
            try:
                message = await self._read_message(reader, timeout=2.0)
                return message.get("type") == "error", sequence
            except Exception:
                return True, sequence
        finally:
            await self._close_writer(writer)

    async def _scenario_out_of_order_ids(self) -> tuple[bool, list[dict[str, Any]]]:
        base = await self._next_request_id("ooo")
        ids = [f"{base}-3", f"{base}-1", f"{base}-2"]
        requests = [{"jsonrpc": "2.0", "id": req_id, "method": "ping"} for req_id in ids]
        sequence: list[dict[str, Any]] = [
            {"action": "open"},
            {"action": "send_batch", "payload": requests},
            {"action": "expect_many", "ids": ids},
            {"action": "close"},
        ]
        reader, writer = await self._open()
        try:
            for request in requests:
                writer.write((json.dumps(request) + "\n").encode("utf-8"))
            await writer.drain()
            got_ids: set[str] = set()
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and len(got_ids) < len(ids):
                message = await self._read_message(reader, timeout=max(0.1, deadline - time.monotonic()))
                req_id = message.get("id")
                if isinstance(req_id, str):
                    got_ids.add(req_id)
            return got_ids.issuperset(set(ids)), sequence
        finally:
            await self._close_writer(writer)

    async def _scenario_duplicate_ids(self) -> tuple[bool, list[dict[str, Any]]]:
        request_id = await self._next_request_id("dup")
        request = {"jsonrpc": "2.0", "id": request_id, "method": "ping"}
        sequence: list[dict[str, Any]] = [
            {"action": "open"},
            {"action": "send", "payload": request},
            {"action": "send", "payload": request},
            {"action": "expect_many", "ids": [request_id]},
            {"action": "close"},
        ]
        reader, writer = await self._open()
        try:
            writer.write((json.dumps(request) + "\n").encode("utf-8"))
            writer.write((json.dumps(request) + "\n").encode("utf-8"))
            await writer.drain()
            got = 0
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                try:
                    message = await self._read_message(
                        reader,
                        timeout=max(0.1, deadline - time.monotonic()),
                    )
                except Exception:
                    break
                if message.get("id") == request_id and message.get("type") in {"result", "error"}:
                    got += 1
                if got >= 2:
                    break
            return got >= 1, sequence
        finally:
            await self._close_writer(writer)

    async def _scenario_disconnect_mid_request(
        self,
        *,
        worker_idx: int,
        op_idx: int,
    ) -> tuple[bool, list[dict[str, Any]]]:
        request = {
            "jsonrpc": "2.0",
            "id": f"disc-{worker_idx}-{op_idx}",
            "method": "session.list",
            "params": {"limit": 10},
        }
        raw = json.dumps(request) + "\n"
        cut = max(1, len(raw) // 3)
        sequence: list[dict[str, Any]] = [
            {"action": "open"},
            {"action": "send_raw", "payload": raw[:cut], "newline": False},
            {"action": "close"},
        ]
        _reader, writer = await self._open()
        writer.write(raw[:cut].encode("utf-8"))
        await writer.drain()
        await self._close_writer(writer)
        ping_ok, _ = await self._scenario_ping_valid()
        return ping_ok, sequence

    def _append_event(self, payload: dict[str, Any]) -> None:
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic JSON-RPC UDS stress harness")
    parser.add_argument("--socket-path", default=None, help="Unix socket path")
    parser.add_argument("--duration", type=int, default=30, help="Approximate run duration in seconds")
    parser.add_argument("--concurrency", type=int, default=20, help="Number of concurrent workers")
    parser.add_argument("--seed", type=int, default=1337, help="Deterministic random seed")
    parser.add_argument("--run-dir", default=None, help="Artifact run directory")
    parser.add_argument(
        "--scenarios",
        default="",
        help="Comma-separated scenario list override",
    )
    parser.add_argument(
        "--ops-per-worker",
        type=int,
        default=0,
        help="Explicit operation count per worker (0 = derived from duration)",
    )
    return parser.parse_args()


def build_worker_plan(*, seed: int, operations: int, scenarios: list[str]) -> list[str]:
    rng = random.Random(seed)
    return [scenarios[rng.randrange(0, len(scenarios))] for _ in range(max(1, operations))]


async def _main() -> int:
    args = parse_args()
    run_dir = Path(
        args.run_dir
        or Path.cwd() / "artifacts" / f"stress-{int(time.time())}"
    )
    socket_path = args.socket_path or str(Path("/tmp") / "ai-agent.sock")
    scenarios = [item.strip() for item in args.scenarios.split(",") if item.strip()]
    harness = StressHarness(
        socket_path=socket_path,
        duration=args.duration,
        concurrency=args.concurrency,
        seed=args.seed,
        run_dir=run_dir,
        scenarios=scenarios or None,
        ops_per_worker=args.ops_per_worker if args.ops_per_worker > 0 else None,
    )
    report = await harness.run()
    print(json.dumps({"stress_report": str(harness.report_path), "summary": report["failed_operations"]}, indent=2))
    return 1 if report["failed_operations"] > 0 else 0


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
