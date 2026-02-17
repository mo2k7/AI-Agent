"""Tests for log redaction utilities."""

from __future__ import annotations

from agent_host.redaction import redact_value


def test_redact_sensitive_keys_recursively() -> None:
    payload = {
        "api_key": "abcd1234",
        "nested": {
            "token": "secret-token",
            "safe": "ok",
        },
        "list": [
            {"password": "p@ssw0rd"},
            {"name": "demo"},
        ],
    }

    redacted = redact_value(payload)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "ok"
    assert redacted["list"][0]["password"] == "[REDACTED]"
    assert redacted["list"][1]["name"] == "demo"


def test_redact_bearer_and_token_like_strings() -> None:
    token = "Bearer super-sensitive-token"
    long_hex = "abc " + ("f" * 64)
    long_b64ish = "zz " + ("A" * 64)
    email = "contact me at user@example.com"
    phone = "call 415-555-1212"

    assert "[REDACTED]" in str(redact_value(token))
    assert "[REDACTED_HEX]" in str(redact_value(long_hex))
    assert (
        "[REDACTED_TOKEN]" in str(redact_value(long_b64ish))
        or "[REDACTED_HEX]" in str(redact_value(long_b64ish))
    )
    assert "[REDACTED_EMAIL]" in str(redact_value(email))
    assert "[REDACTED_PHONE]" in str(redact_value(phone))
