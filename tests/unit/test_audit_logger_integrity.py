"""Integrity and retention tests for audit logger compliance controls."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from agent_host.audit_logger import AuditLogger, EventType


def test_audit_hash_chain_verifies(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path, encrypt=False)
    logger.log_event(EventType.STARTUP, {"v": 1})
    logger.log_event(EventType.TOOL_CALL, {"tool": "browse_web"})

    ok, reason = logger.verify_integrity_chain()
    assert ok is True
    assert reason == "ok"


def test_audit_hash_chain_detects_tamper(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path, encrypt=False)
    logger.log_event(EventType.STARTUP, {"v": 1})
    logger.log_event(EventType.TOOL_CALL, {"tool": "browse_web"})

    lines = log_path.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["data"]["tool"] = "tampered"
    lines[1] = json.dumps(second)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, reason = logger.verify_integrity_chain()
    assert ok is False
    assert "mismatch" in reason.lower()


def test_audit_prune_older_than_removes_old_events(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path, encrypt=False)
    logger.log_event(
        EventType.STARTUP,
        {"v": 1},
        timestamp=None,
    )

    # Inject a clearly old event directly to force pruning path.
    old_event = {
        "timestamp": "2000-01-01T00:00:00+00:00",
        "event": "TEST",
        "data": {"x": 1},
    }
    payload_for_hash = json.dumps(
        {
            "timestamp": old_event["timestamp"],
            "event": old_event["event"],
            "data": old_event["data"],
        },
        sort_keys=True,
    )
    old_event["integrity"] = {
        "version": "sha256-chain-v1",
        "prev_hash": "",
        "entry_hash": hashlib.sha256(("|" + payload_for_hash).encode("utf-8")).hexdigest(),
    }
    log_path.write_text(json.dumps(old_event) + "\n", encoding="utf-8")

    removed = logger.prune_older_than(days=30)
    assert removed == 1
