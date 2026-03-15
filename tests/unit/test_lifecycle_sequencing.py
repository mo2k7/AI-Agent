"""Tests for SystemMessage lifecycle event structure and seq injection.

Upgrade C — monotonic event sequencing: the ``_lifecycle_seq`` counter lives
inside ``run_server()`` and is not directly importable, but the mechanism
relies on ``SystemMessage.system`` being a mutable dict that survives
serialization.  These four tests verify exactly that contract.
"""

import json

from agent_host.ipc.protocol import SystemMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_event() -> SystemMessage:
    """Return a typical session lifecycle event."""
    return SystemMessage.session_event(
        "test-request-id",
        action="created",
        session={"session_id": "s1", "title": "Test"},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_system_message_system_dict_is_mutable():
    """``msg.system`` is a plain dict and accepts arbitrary extra keys."""
    msg = _make_session_event()
    assert isinstance(msg.system, dict)
    msg.system["seq"] = 42
    assert msg.system["seq"] == 42


def test_seq_field_in_serialized_output():
    """After injecting ``seq``, the key survives ``to_bytes()`` round-trip."""
    msg = _make_session_event()
    msg.system["seq"] = 7
    raw = msg.to_bytes().decode("utf-8")
    parsed = json.loads(raw)
    assert "seq" in parsed["system"]


def test_session_event_has_correct_structure():
    """``session_event`` populates the expected lifecycle envelope."""
    msg = SystemMessage.session_event(
        "id1",
        action="created",
        session={"session_id": "s1"},
    )
    assert msg.system["event"] == "lifecycle"
    assert msg.system["domain"] == "session"
    assert msg.system["action"] == "created"
    assert msg.system["payload"]["session"]["session_id"] == "s1"


def test_seq_is_integer_in_serialized_form():
    """``seq`` must remain an ``int`` through JSON serialization."""
    msg = _make_session_event()
    msg.system["seq"] = 99
    raw = msg.to_bytes().decode("utf-8")
    parsed = json.loads(raw)
    assert parsed["system"]["seq"] == 99
    assert isinstance(parsed["system"]["seq"], int)
