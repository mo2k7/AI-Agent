"""Prompt parsing and formatting helpers.

Pure functions and constants extracted from ``agent_host.main`` for
prompt-level input validation, environment variable parsing, session
normalisation, and tool output formatting.
"""

from __future__ import annotations

import os
import re

from agent_host.contracts.types.domain import ExecutionMode, MemoryMode
import re as _re
from agent_host.response_formatter import format_tool_execution_output


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _safe_env_int(name: str, default: int) -> int:
    """Parse an integer environment variable, returning *default* on invalid input."""
    raw = os.environ.get(name, "")
    if not raw.strip():
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def _safe_env_float(name: str, default: float) -> float:
    """Parse a float environment variable, returning *default* on invalid input."""
    raw = os.environ.get(name, "")
    if not raw.strip():
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Memory mode parsing
# ---------------------------------------------------------------------------

def _parse_memory_mode(raw_value: object, *, default: MemoryMode = MemoryMode.ON) -> MemoryMode:
    """Parse memory mode values defensively."""
    parsed = _parse_memory_mode_strict(raw_value)
    if parsed is not None:
        return parsed
    return default


def _parse_memory_mode_strict(raw_value: object) -> MemoryMode | None:
    """Parse memory mode values strictly, returning None when invalid."""
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        for mode in MemoryMode:
            if mode.value == normalized:
                return mode
    return None


# ---------------------------------------------------------------------------
# Session / prompt option constants
# ---------------------------------------------------------------------------

_SESSION_ID_SANITIZER = re.compile(r"[^a-zA-Z0-9._-]+")

_VERBOSITY_LEVEL_BY_NAME: dict[str, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "extra_high": 3,
}

_PRESENTATION_STYLE_NAMES: set[str] = {
    "readable_pro",
    "glass_editorial",
    "dense_technical",
}

_STREAM_ANIMATION_STYLE_NAMES: set[str] = {
    "wave_reveal",
    "typewriter_luxe",
    "minimal_motion",
}

_BROWSE_PROFILE_NAMES: set[str] = {
    "strict",
    "standard",
    "flexible",
}


# ---------------------------------------------------------------------------
# Session normalisation
# ---------------------------------------------------------------------------

def _normalize_session_id(raw_value: object, *, fallback: str) -> str:
    """Normalize externally provided session ids to a safe filename key."""
    if isinstance(raw_value, str):
        cleaned = _SESSION_ID_SANITIZER.sub("-", raw_value.strip())
        cleaned = cleaned.strip("-.")
        if cleaned:
            return cleaned[:96]
    return fallback


# ---------------------------------------------------------------------------
# Strict option parsers
# ---------------------------------------------------------------------------

def _parse_verbosity_level_strict(raw_value: object) -> int | None:
    """Parse prompt verbosity setting strictly.

    Accepted values are the user-facing strings:
    ``low``, ``medium``, ``high``, ``extra_high``.
    Returns ``None`` when input is missing/invalid.
    """
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        return _VERBOSITY_LEVEL_BY_NAME.get(normalized)
    return None


def _parse_execution_mode_strict(raw_value: object) -> ExecutionMode | None:
    """Parse execution mode values strictly, returning None when invalid."""
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        for mode in ExecutionMode:
            if mode.value == normalized:
                return mode
    return None


def _parse_presentation_style_strict(raw_value: object) -> str | None:
    """Parse presentation style values strictly, returning None when invalid."""
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in _PRESENTATION_STYLE_NAMES:
            return normalized
    return None


def _parse_stream_animation_style_strict(raw_value: object) -> str | None:
    """Parse stream animation style values strictly, returning None when invalid."""
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in _STREAM_ANIMATION_STYLE_NAMES:
            return normalized
    return None


def _parse_deep_think_flag_strict(raw_value: object) -> bool | None:
    """Parse deep-think toggle strictly as a boolean."""
    if isinstance(raw_value, bool):
        return raw_value
    return None


def _parse_browse_profile_strict(raw_value: object) -> str | None:
    """Parse browse profile values strictly, returning None when invalid."""
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in _BROWSE_PROFILE_NAMES:
            return normalized
    return None


# ---------------------------------------------------------------------------
# Model / timeout helpers
# ---------------------------------------------------------------------------

_MODEL_VERSION_PATTERN = _re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _model_supports_native_deep_think(model_name: str) -> bool:
    """Return whether a model supports strict deep-think controls.

    Gemini 2.5+ and 3.x+ support native thinking configuration.
    """
    lowered = model_name.strip().lower()
    if not lowered.startswith("gemini-"):
        return False
    match = _MODEL_VERSION_PATTERN.search(lowered)
    if not match:
        return False
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    if major >= 3:
        return True
    return major == 2 and minor >= 5


def _resolve_model_timeout_seconds(
    *,
    base_timeout_seconds: float,
    deep_think: bool,
    execution_mode: ExecutionMode,
    is_continuation: bool,
    deep_think_multiplier: float,
    teacher_multiplier: float,
    continuation_multiplier: float,
    max_timeout_seconds: float,
) -> float:
    """Resolve per-model-call timeout for strict deep-think and teacher flows."""
    timeout_seconds = max(5.0, float(base_timeout_seconds))
    if deep_think:
        timeout_seconds *= max(1.0, float(deep_think_multiplier))
    if execution_mode == ExecutionMode.TEACHER:
        timeout_seconds *= max(1.0, float(teacher_multiplier))
    if is_continuation:
        timeout_seconds *= max(1.0, float(continuation_multiplier))
    timeout_cap = max(5.0, float(max_timeout_seconds))
    return min(timeout_seconds, timeout_cap)


def _resolve_prompt_timeout_seconds(
    *,
    base_timeout_seconds: float,
    model_timeout_seconds: float,
    tool_timeout_seconds: float,
    deep_think: bool,
    execution_mode: ExecutionMode,
    max_timeout_seconds: float,
) -> float:
    """Resolve request-level timeout so strict deep-think teacher turns can complete."""
    timeout_seconds = max(30.0, float(base_timeout_seconds))
    if deep_think:
        if execution_mode == ExecutionMode.TEACHER:
            timeout_seconds = max(
                timeout_seconds,
                float(model_timeout_seconds) + float(tool_timeout_seconds) + 45.0,
            )
        else:
            timeout_seconds = max(timeout_seconds, float(model_timeout_seconds) + 30.0)
    timeout_cap = max(30.0, float(max_timeout_seconds))
    return min(timeout_seconds, timeout_cap)


# ---------------------------------------------------------------------------
# Exception / output formatting
# ---------------------------------------------------------------------------

def _format_exception_message(
    exc: BaseException,
    *,
    fallback: str = "Internal backend error",
) -> str:
    """Return a stable human-readable exception message for IPC errors."""
    detail = str(exc).strip()
    if detail:
        return detail
    return f"{fallback} ({exc.__class__.__name__})"


def _format_tool_execution_output(
    tool_name: str,
    execution: dict[str, object],
) -> tuple[str, str]:
    """Build user-facing content + concise summary for executed tools.

    Delegates to the dedicated ``response_formatter`` module which
    provides per-tool markdown formatters for all 8 tool types.
    """
    return format_tool_execution_output(tool_name, execution)
