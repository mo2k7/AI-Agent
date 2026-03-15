#!/usr/bin/env python3
"""Capture a minimal replay artifact from a stress report failure."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture replay file from stress_report.json")
    parser.add_argument("--report", required=True, help="Path to stress_report.json")
    parser.add_argument("--run-dir", required=True, help="Artifacts run directory")
    parser.add_argument(
        "--failure-index",
        type=int,
        default=0,
        help="Failure index from stress report failures list",
    )
    return parser.parse_args()


def _normalize_sequence(sequence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for step in sequence:
        action = str(step.get("action", "")).strip()
        if not action:
            continue
        payload: dict[str, Any] = {"action": action}
        if "payload" in step:
            payload["payload"] = step["payload"]
        if "newline" in step:
            payload["newline"] = bool(step["newline"])
        if "type" in step:
            payload["type"] = step["type"]
        if "id" in step:
            payload["id"] = step["id"]
        if "ids" in step:
            payload["ids"] = step["ids"]
        normalized.append(payload)
    return normalized


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    failures = report.get("failures", [])
    if not isinstance(failures, list) or not failures:
        print("No failures found in stress report; nothing to capture.")
        return 0

    index = max(0, min(args.failure_index, len(failures) - 1))
    failure = failures[index]
    sequence = failure.get("sequence", [])
    if not isinstance(sequence, list):
        sequence = []

    replay = {
        "captured_at": time.time(),
        "source_report": str(report_path),
        "backend_url": report.get("backend_url"),
        "seed": report.get("seed"),
        "scenario": failure.get("scenario"),
        "error": failure.get("error"),
        "steps": _normalize_sequence(sequence),
    }

    replay_path = run_dir / f"replay_{index:02d}.json"
    replay_path.write_text(json.dumps(replay, indent=2), encoding="utf-8")

    repro_path = run_dir / "REPRO.txt"
    repro_cmd = (
        f"poetry run python scripts/repro_replay.py "
        f"--replay {replay_path} --backend-url {report.get('backend_url', 'ws://127.0.0.1:8765')} "
        f"--auth-token \"$AI_AGENT_IPC_AUTH_TOKEN\" --bisect"
    )
    repro_path.write_text(repro_cmd + "\n", encoding="utf-8")

    print(json.dumps({"replay": str(replay_path), "repro_cmd_file": str(repro_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
