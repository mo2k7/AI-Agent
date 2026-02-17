"""Security regression tests for audit logging behavior."""

from __future__ import annotations

import json
import stat
from pathlib import Path

from agent_host.audit_logger import AuditLogger


def test_log_event_redacts_sensitive_payloads(tmp_path: Path) -> None:
    log_path = tmp_path / "audit" / "events.jsonl"
    logger = AuditLogger(log_path)

    logger.log_event(
        "TEST",
        {
            "api_key": "super-secret",
            "prompt": "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
            "safe": "ok",
        },
    )

    event = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert event["data"]["api_key"] == "[REDACTED]"
    assert event["data"]["prompt"] == "Bearer [REDACTED]"
    assert event["data"]["safe"] == "ok"


def test_log_file_permissions_are_owner_only(tmp_path: Path) -> None:
    log_path = tmp_path / "audit" / "events.jsonl"
    logger = AuditLogger(log_path)
    logger.log_event("TEST", {"safe": "ok"})

    mode = stat.S_IMODE(log_path.stat().st_mode)
    assert mode & 0o077 == 0
