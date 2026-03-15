"""Tests for AuditLogger encryption support (Upgrade F).

The logger accepts ``encrypt: bool | None`` in ``__init__``.  When True each
JSONL line is encrypted via ``CryptoBox.encrypt_text(line, aad=b"audit-log-entry")``.
The conftest ``patch_memory_keychain`` fixture patches ``_load_from_keychain``
to return ``b"k" * 32``, so ``get_or_create_master_key()`` works without a
real Keychain entry.
"""

import json
from pathlib import Path

from agent_host.audit_logger import AuditLogger, EventType


# ---------------------------------------------------------------------------
# 1. Unencrypted writes plaintext
# ---------------------------------------------------------------------------


def test_unencrypted_writes_plaintext(tmp_path: Path):
    """An unencrypted logger writes valid JSON lines directly."""
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path, encrypt=False)
    logger.log_event(EventType.STARTUP, {"version": "1.0"})

    raw_line = log_path.read_text(encoding="utf-8").strip().split("\n")[0]
    event = json.loads(raw_line)  # must not raise
    assert event["event"] == "STARTUP"
    assert event["data"]["version"] == "1.0"


# ---------------------------------------------------------------------------
# 2. Encrypted writes ciphertext (JSON blob with nonce + ciphertext)
# ---------------------------------------------------------------------------


def test_encrypted_writes_ciphertext(tmp_path: Path):
    """An encrypted logger writes an EncryptedBlob JSON, not raw event JSON."""
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path, encrypt=True)
    logger.log_event(EventType.STARTUP, {"version": "1.0"})

    raw_line = log_path.read_text(encoding="utf-8").strip().split("\n")[0]
    blob = json.loads(raw_line)
    # CryptoBox.encrypt_text returns JSON with "nonce" and "ciphertext"
    assert "nonce" in blob
    assert "ciphertext" in blob
    # It should NOT contain the plaintext event key
    assert "event" not in blob


# ---------------------------------------------------------------------------
# 3. Encrypted round-trip via read_events
# ---------------------------------------------------------------------------


def test_encrypted_round_trip(tmp_path: Path):
    """Encrypted events can be written and read back via ``read_events()``."""
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path, encrypt=True)
    logger.log_event(EventType.STARTUP, {"version": "1.0"})
    logger.log_event(EventType.SHUTDOWN, {"reason": "test"})

    events = logger.read_events()
    assert len(events) == 2
    assert events[0]["event"] == "STARTUP"
    assert events[0]["data"]["version"] == "1.0"
    assert events[1]["event"] == "SHUTDOWN"
    assert events[1]["data"]["reason"] == "test"


# ---------------------------------------------------------------------------
# 4. Environment variable enables encryption
# ---------------------------------------------------------------------------


def test_encrypt_env_var_enables_encryption(tmp_path: Path, monkeypatch):
    """``AI_AGENT_AUDIT_ENCRYPT=true`` enables encryption without explicit param."""
    monkeypatch.setenv("AI_AGENT_AUDIT_ENCRYPT", "true")
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path)  # no explicit encrypt=
    logger.log_event(EventType.STARTUP, {"version": "1.0"})

    raw_line = log_path.read_text(encoding="utf-8").strip().split("\n")[0]
    blob = json.loads(raw_line)
    assert "nonce" in blob
    assert "ciphertext" in blob


# ---------------------------------------------------------------------------
# 5. decrypt_audit CLI round-trip
# ---------------------------------------------------------------------------


def test_decrypt_cli_round_trip(tmp_path: Path, capsys):
    """The ``decrypt_audit`` CLI tool decrypts an encrypted log to stdout."""
    from agent_host.tools.decrypt_audit import main as decrypt_main

    log_path = tmp_path / "audit.log"
    al = AuditLogger(log_path, encrypt=True)
    al.log_event(EventType.STARTUP, {"version": "1.0"})

    decrypt_main([str(log_path)])

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line]
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "STARTUP"
    assert event["data"]["version"] == "1.0"


# ---------------------------------------------------------------------------
# 6. read_events with type filter
# ---------------------------------------------------------------------------


def test_read_events_with_filter(tmp_path: Path):
    """``read_events(event_type)`` returns only matching events."""
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path, encrypt=True)
    logger.log_event(EventType.TOOL_CALL, {"tool": "search_files", "args": {}})
    logger.log_event(EventType.ERROR, {"error_type": "timeout", "message": "oops"})
    logger.log_event(EventType.TOOL_CALL, {"tool": "read_file", "args": {}})

    tool_events = logger.read_events(EventType.TOOL_CALL)
    assert len(tool_events) == 2
    assert all(e["event"] == "TOOL_CALL" for e in tool_events)


# ---------------------------------------------------------------------------
# 7. Unencrypted logger reads plaintext events
# ---------------------------------------------------------------------------


def test_unencrypted_logger_reads_plaintext(tmp_path: Path):
    """An unencrypted logger can write and read back events via ``read_events()``."""
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path, encrypt=False)
    logger.log_event(EventType.API_REQUEST, {"url": "https://example.com"})

    events = logger.read_events()
    assert len(events) == 1
    assert events[0]["event"] == "API_REQUEST"
    assert events[0]["data"]["url"] == "https://example.com"
