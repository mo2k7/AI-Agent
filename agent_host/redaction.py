"""Utilities to sanitize sensitive values before logging."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|token|secret|password|authorization|cookie|session[_-]?key|credential)",
    re.IGNORECASE,
)
_BEARER_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/\-]+=*\b", re.IGNORECASE)
_HEX_TOKEN_PATTERN = re.compile(r"\b[a-fA-F0-9]{64,}\b")
_BASE64ISH_PATTERN = re.compile(r"\b[A-Za-z0-9+/]{64,}={0,2}\b")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")


def _looks_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(key))


def _redact_text(value: str) -> str:
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    redacted = _HEX_TOKEN_PATTERN.sub("[REDACTED_HEX]", redacted)
    redacted = _BASE64ISH_PATTERN.sub("[REDACTED_TOKEN]", redacted)
    redacted = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted)
    redacted = _PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)
    return redacted


def redact_value(value: Any, *, parent_key: str | None = None) -> Any:
    """Recursively redact sensitive payloads for logging."""
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, inner in value.items():
            key_str = str(key)
            if _looks_sensitive_key(key_str):
                output[key_str] = "[REDACTED]"
            else:
                output[key_str] = redact_value(inner, parent_key=key_str)
        return output

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_value(item, parent_key=parent_key) for item in value]

    if isinstance(value, bytes):
        return _redact_text(value.decode("utf-8", errors="replace"))

    if isinstance(value, str):
        if parent_key and _looks_sensitive_key(parent_key):
            return "[REDACTED]"
        return _redact_text(value)

    return value
