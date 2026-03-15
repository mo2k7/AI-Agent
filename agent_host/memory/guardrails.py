"""Security guardrails for memory ingestion and retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+all\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
    re.compile(r"exfiltrat(e|ion)", re.IGNORECASE),
    re.compile(r"bypass\s+security", re.IGNORECASE),
    re.compile(r"run\s+(shell|terminal|command)", re.IGNORECASE),
]

SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY-----"),
    re.compile(r"password\s*[:=]", re.IGNORECASE),
]

HIGH_RISK_TOOLS = {"apply_ops"}
MEDIUM_RISK_TOOLS = {"open_item"}


@dataclass(frozen=True)
class GuardrailAssessment:
    """Policy flags generated from untrusted text."""

    flags: tuple[str, ...]

    @property
    def suspicious(self) -> bool:
        return bool(self.flags)


def assess_text_for_policy_flags(text: str) -> GuardrailAssessment:
    """Return policy flags for suspicious content."""
    found: list[str] = []
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            found.append("prompt_injection_suspected")
            break
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            found.append("secret_like")
            break
    return GuardrailAssessment(flags=tuple(dict.fromkeys(found)))


def is_storable_memory_text(text: str) -> bool:
    """Gate memory writes for secret-like payloads."""
    assessment = assess_text_for_policy_flags(text)
    return "secret_like" not in assessment.flags


def sanitize_memory_snippet(text: str, *, max_chars: int = 0) -> str:
    """Normalize memory snippets before prompt injection.

    Collapses whitespace for clean formatting.  When *max_chars* is
    positive the result is hard-capped at that length; zero or negative
    means unlimited (whitespace normalization only).
    """
    collapsed = " ".join(text.split())
    if max_chars <= 0 or len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1] + "…"


def should_quarantine(flags: Iterable[str]) -> bool:
    """Whether a memory entry should be excluded from normal retrieval."""
    flag_set = set(flags)
    return "prompt_injection_suspected" in flag_set


def risk_tier_for_tool(tool_name: str) -> str:
    """Classify tool execution risk tier."""
    if tool_name in HIGH_RISK_TOOLS:
        return "high"
    if tool_name in MEDIUM_RISK_TOOLS:
        return "medium"
    return "low"
