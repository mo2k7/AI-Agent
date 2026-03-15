"""Tests for live debug harness helper scripts."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from websockets.asyncio.server import serve


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
    backend_url_holder: dict[str, str] = {}

    async def handle(connection) -> None:
        async for raw in connection:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            raw = raw.strip()
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
                await connection.send(json.dumps(response))
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
            await connection.send(json.dumps(response))

    server = await serve(handle, "127.0.0.1", 0)
    sock = server.sockets[0]
    host, port = sock.getsockname()[:2]
    backend_url_holder["url"] = f"ws://{host}:{port}"
    try:
        harness = module.StressHarness(
            backend_url=backend_url_holder["url"],
            auth_token=None,
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
