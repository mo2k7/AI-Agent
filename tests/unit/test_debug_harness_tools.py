"""Tests for live debug harness helper scripts."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest


def _load_script_module(script_name: str, module_name: str) -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_build_worker_plan_is_deterministic_for_same_seed() -> None:
    module = _load_script_module("stress_rpc.py", "stress_rpc_for_test_plan")
    scenarios = ["ping_valid", "unknown_method", "session_create_valid"]
    plan_a = module.build_worker_plan(seed=1234, operations=12, scenarios=scenarios)
    plan_b = module.build_worker_plan(seed=1234, operations=12, scenarios=scenarios)
    plan_c = module.build_worker_plan(seed=9999, operations=12, scenarios=scenarios)

    assert plan_a == plan_b
    assert plan_a != plan_c


@pytest.mark.anyio
async def test_stress_harness_smoke_with_fake_backend(tmp_path: Path) -> None:
    module = _load_script_module("stress_rpc.py", "stress_rpc_for_test_smoke")
    socket_path = Path(f"/tmp/ai-agent-stress-smoke-{uuid.uuid4().hex[:8]}.sock")

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                raw = line.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    response = {
                        "jsonrpc": "2.0",
                        "id": "global",
                        "type": "error",
                        "error": {"code": -32700, "message": "Parse error"},
                    }
                    writer.write((json.dumps(response) + "\n").encode("utf-8"))
                    await writer.drain()
                    continue

                request_id = payload.get("id", "global")
                method = payload.get("method")
                if method == "ping":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "type": "result",
                        "result": {"content": "pong"},
                    }
                elif method == "session.create":
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "type": "result",
                        "result": {
                            "content": json.dumps(
                                {
                                    "session_id": "session-smoke",
                                    "title": "smoke",
                                    "memory_mode": "on",
                                    "created_at": 0.0,
                                }
                            )
                        },
                    }
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "type": "error",
                        "error": {"code": -32601, "message": f"Method not found: {method}"},
                    }
                writer.write((json.dumps(response) + "\n").encode("utf-8"))
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, path=str(socket_path))
    try:
        harness = module.StressHarness(
            socket_path=str(socket_path),
            duration=1,
            concurrency=2,
            seed=42,
            run_dir=tmp_path / "artifacts",
            scenarios=["ping_valid", "unknown_method", "session_create_valid"],
            ops_per_worker=4,
        )
        report = await harness.run()
        assert report["total_operations"] == 8
        assert report["failed_operations"] == 0
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)
