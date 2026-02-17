#!/usr/bin/env python3
"""CLI entrypoint for the Personal macOS AI Agent.

This module provides the command-line interface for interacting with
the AI agent. It integrates all core modules to process natural language
prompts and determine appropriate tool calls.

It also provides IPC server mode for communication with the SwiftUI frontend.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import time
import sys
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, NoReturn, Optional

from dotenv import load_dotenv
from google.genai import types

from agent_host.audit_logger import AuditLogger, AuditLogError, EventType
from agent_host.config import Config, ConfigurationError
from agent_host.gemini_client import (
    GeminiClient,
    GeminiAPIError,
    GeminiClientError,
    GeminiRateLimitError,
    GeminiServerError,
)
from agent_host.schema_validator import (
    SchemaValidator,
    SchemaLoadError,
    SchemaNotFoundError,
    ValidationFailedError,
)
from agent_host.tool_parser import ToolCallParser, MalformedResponseError
from agent_host.system_prompt import build_system_prompt, inject_model_identity
from agent_host.system_prompt import SystemPromptLoadError
from agent_host.memory.embeddings import EmbeddingService
from agent_host.memory.manager import MemoryManager
from agent_host.memory.migration import MemoryMigrationError, run_preflight_migration
from agent_host.memory.store import get_db_metrics_snapshot
from agent_host.tools._helpers import (
    _build_teacher_note_body,
    _normalize_note_tags,
)
from agent_host.tools.registry import (
    ImageToolContext,
    NoteToolContext,
    NOTE_TOOL_NAMES,
    ScreenToolContext,
    TEACHER_DEFAULT_NOTE_TAGS,
    TEACHER_DEFAULT_NOTE_TYPE,
    TEACHER_NOTE_COMPLETION_TOOLS,
    dispatch_note_tool,
    dispatch_screen_tool,
)
# Import tool modules to trigger handler self-registration.
import agent_host.tools.take_note  # noqa: F401
import agent_host.tools.update_note  # noqa: F401
import agent_host.tools.delete_note  # noqa: F401
import agent_host.tools.format_note  # noqa: F401
import agent_host.tools.merge_notes  # noqa: F401
import agent_host.tools.reorder_notes  # noqa: F401
import agent_host.tools.generate_quiz  # noqa: F401
import agent_host.tools.summarize_note  # noqa: F401
import agent_host.tools.generate_image  # noqa: F401
import agent_host.tools.read_screen  # noqa: F401
from agent_host.memory.types import MemoryMode
from agent_host.observability import (
    configure_logging,
    generate_correlation_id,
    reset_request_context,
    set_request_context,
)
from agent_host.response_formatter import format_tool_execution_output
from agent_host.response_sanitizer import (
    looks_like_json_payload,
    sanitize_user_visible_response,
)
from agent_host.tools.executor import ToolExecutionError, ToolExecutor
from agent_host.nlp import PlanClarificationIntentClassifier

logger = logging.getLogger(__name__)

# Exit codes
EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_API_ERROR = 2
EXIT_VALIDATION_ERROR = 3


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
_PLAN_MODE_DISCOVERY_BEFORE_PLANNER_DEFAULT = 20
_PLAN_MODE_CLARIFICATION_REQUIRED_DEFAULT = True
_PLAN_MODE_CLARIFICATION_MIN_MISSING_DEFAULT = 3
_PLAN_MODE_CLARIFICATION_MAX_QUESTIONS = 20
_PLAN_MODE_CLARIFICATION_MAX_ROUNDS_DEFAULT = 20
_PLAN_MODE_CLARIFICATION_SCORE_THRESHOLD_DEFAULT = 0.34
_PLAN_MODE_CLARIFICATION_CONFIDENCE_TARGET_DEFAULT = 0.72
_PLAN_MODE_OPTION_KEYS = ("A", "B", "C", "D")
_PLAN_MODE_DISCOVERY_TOOLS = {
    "search_files",
    "read_text",
    "extract_content",
    "get_metadata",
}
_PLAN_MODE_PLANNER_TOOLS = {"planner", "plan_ops"}
_PLAN_MODE_OP_VERB_PATTERN = re.compile(
    r"\b(move|copy|rename|delete|remove|organize|reorganize|sort|archive|relocate|transfer|arrange|clean(?:\s+up)?|create|make|apply|execute)\b"
)
_PLAN_MODE_OP_OBJECT_PATTERN = re.compile(
    r"\b(file|files|folder|folders|directory|directories|path|paths|document|documents|download|downloads|desktop|archive|operation|operations)\b"
)
_PLAN_MODE_OP_DEMONSTRATIVE_INTENT_PATTERN = re.compile(
    r"\b(move|copy|rename|delete|remove|relocate|transfer|archive)\s+(this|these|it|them)\b"
)
_PLAN_MODE_EXPLICIT_OPERATION_PHRASES = (
    "move file",
    "move files",
    "copy file",
    "copy files",
    "rename file",
    "rename files",
    "delete file",
    "delete files",
    "organize files",
    "organize this file",
    "organize this folder",
)
_PLAN_MODE_GOAL_SIGNAL_PATTERN = re.compile(
    r"\b(goal|objective|outcome|target|for\s+\w+|prepare\s+for|roadmap\s+for|plan\s+for|plan\s+to\s+\w+"
    r"|study\s+for|reorganize|restructure|overhaul|consolidate|streamline|migrate|archive"
    r"|clean\s*up|set\s+up\s+\w+|create\s+a\s+plan|build\s+a\s+plan)\b"
)
_PLAN_MODE_TIMEFRAME_SIGNAL_PATTERN = re.compile(
    r"\b(\d+\s*(day|days|week|weeks|month|months|year|years|hour|hours)|deadline|due|by\s+\d{4}-\d{2}-\d{2})\b"
)
_PLAN_MODE_BASELINE_SIGNAL_PATTERN = re.compile(
    r"\b(beginner|intermediate|advanced|novice|expert|experience|background|current\s+level|skill\s+level"
    r"|familiar|comfortable|proficient|new\s+to\s+this|currently|existing|spread\s+across"
    r"|\d+(?:\.\d+)?\s*(?:tb|gb|mb))\b",
    re.IGNORECASE,
)
_PLAN_MODE_CONSTRAINT_SIGNAL_PATTERN = re.compile(
    r"\b(constraint|limit|budget|priority|exclude|include|available|hours?\s*(/|per)\s*(day|week)"
    r"|focus|avoid|weekend|weekends|weeknight|weeknights"
    r"|safe(?:ly)?|careful(?:ly)?|conservative|gradual(?:ly)?|phased|staged"
    r"|privacy|retention|compliance|audit|legal|rollback|checkpoint|backup"
    r"|no\s+(?:permanent\s+)?delet(?:e|ion)|without\s+deleting)\b"
)
_PLAN_MODE_ANSWER_Q_PATTERN = re.compile(
    r"\bQ\s*(\d+)\s*[:=\-]\s*([A-D])\b",
    re.IGNORECASE,
)
_PLAN_MODE_SINGLE_OPTION_PATTERN = re.compile(r"^\s*([A-D])(?:[\)\].:\-]|\s|$)", re.IGNORECASE)
_PLAN_MODE_CLARIFICATION_PREFIX_PATTERN = re.compile(r"^(?:notes|q\s*\d+)\s*[:=\-]", re.IGNORECASE)
_PLAN_MODE_TOKEN_PATTERN = re.compile(r"[a-z0-9]{3,}")
_PLAN_MODE_STRUCTURED_QUESTION_PATTERN = re.compile(r"\bQ\s*\d+\.", re.IGNORECASE)
_PLAN_MODE_STRUCTURED_OPTION_BLOCK_PATTERN = re.compile(
    r"\bA\)\s+.+\bB\)\s+.+\bC\)\s+.+\bD\)\s+",
    re.IGNORECASE | re.DOTALL,
)
_PLAN_MODE_FOLLOWUP_CLARIFY_SIGNAL_PATTERN = re.compile(
    r"\b(clarif(?:y|ication|ying)|question(?:s)?|please\s+answer|to\s+tailor|to\s+ensure|before\s+writing\s+the\s+plan)\b",
    re.IGNORECASE,
)
_PLAN_MODE_BULLET_QUESTION_LINE_PATTERN = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])\s+.*\?\s*$",
    re.MULTILINE,
)
_PLAN_MODE_BANNER_PLANNING_PATTERN = re.compile(
    r"^plan mode\s*\(\s*planning only\s*\)\s*(?:\.{3}|…)?\s*$",
    re.IGNORECASE,
)
_PLAN_MODE_ALIGNMENT_STRUCTURE_TOKENS = {
    "phase",
    "step",
    "steps",
    "milestone",
    "milestones",
    "timeline",
    "risk",
    "risks",
    "rollback",
    "verification",
    "validation",
    "checkpoint",
    "checkpoints",
    "assumption",
    "assumptions",
}
_PLAN_MODE_TIMELINE_HINT_PATTERN = re.compile(
    r"\b(\d+\s*(?:day|days|week|weeks|month|months|year|years))\b",
    re.IGNORECASE,
)
_PLAN_MODE_VOLUME_HINT_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(tb|gb|mb)\b",
    re.IGNORECASE,
)
_PLAN_MODE_PRIVACY_SIGNAL_PATTERN = re.compile(
    r"\b(privacy|sensitive|confidential|private|security)\b",
    re.IGNORECASE,
)
_PLAN_MODE_ROLLBACK_SIGNAL_PATTERN = re.compile(
    r"\b(rollback|restore|recovery|revert|checkpoint|undo)\b",
    re.IGNORECASE,
)
_PLAN_MODE_NO_DELETE_SIGNAL_PATTERN = re.compile(
    r"\b(no\s+permanent\s+delet(?:e|ion)|without\s+deleting|do\s+not\s+delet(?:e|ion)|don't\s+delete)\b",
    re.IGNORECASE,
)
_PLAN_MODE_HELPER_SIGNAL_PATTERN = re.compile(
    r"\b(helper|helpers|family|team|non-technical|collaboration|delegate)\b",
    re.IGNORECASE,
)
_PLAN_MODE_RETENTION_SIGNAL_PATTERN = re.compile(
    r"\b(retention|tax|legal|compliance|audit)\b",
    re.IGNORECASE,
)
_PLAN_MODE_WEEKEND_SIGNAL_PATTERN = re.compile(r"\b(weekend|weekends|batch)\b", re.IGNORECASE)
_PLAN_MODE_WEEKDAY_LIMIT_SIGNAL_PATTERN = re.compile(
    r"\b(weekday|weekdays|\d+\s*(?:min|mins|minute|minutes|hour|hours)\s*/?\s*(?:day|week))\b",
    re.IGNORECASE,
)
_PLAN_MODE_TOPIC_HINT_ALLOWLIST = (
    "documents",
    "photos",
    "videos",
    "downloads",
    "projects",
    "archives",
    "backup",
    "backups",
    "retention",
    "taxonomy",
    "rollback",
    "verification",
    "privacy",
    "cleanup",
)
def _plan_mode_nlp_model_candidates() -> tuple[str, ...]:
    primary = os.environ.get("AI_AGENT_PLAN_MODE_NLP_MODEL", "en_core_web_trf").strip()
    ordered: list[str] = []
    for candidate in (
        primary,
        "en_core_web_trf",
        "en_core_web_lg",
        "en_core_web_md",
        "en_core_web_sm",
    ):
        normalized = candidate.strip()
        if not normalized or normalized in ordered:
            continue
        ordered.append(normalized)
    return tuple(ordered)


_PLAN_MODE_CLARIFICATION_INTENT_CLASSIFIER = PlanClarificationIntentClassifier(
    model_candidates=_plan_mode_nlp_model_candidates(),
)


class ExecutionMode(str, Enum):
    """Prompt execution behavior mode selected by the UI."""

    DIRECT = "direct"
    PLAN = "plan"
    TEACHER = "teacher"


@dataclass
class PlanClarificationState:
    """Ephemeral per-session plan-mode clarification state."""

    root_prompt: str
    domain: str
    question_dimensions: list[str] = field(default_factory=list)
    pending_dimension: str | None = None
    pending_question_number: int = 1
    asked_rounds: int = 0
    answers_count: int = 0
    confidence: float = 0.0
    answered_dimensions: dict[str, str] = field(default_factory=dict)
    option_answers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanPromptProfile:
    """Context signals extracted from a plan prompt for dynamic clarification."""

    timeline_hint: str = ""
    volume_hint: str = ""
    has_privacy_signal: bool = False
    has_rollback_signal: bool = False
    has_no_delete_signal: bool = False
    has_helper_signal: bool = False
    has_retention_signal: bool = False
    prefers_weekend_batches: bool = False
    has_weekday_time_limit: bool = False
    topic_hints: tuple[str, ...] = ()


def _preload_plan_mode_nlp_classifier(logger: logging.Logger) -> str:
    result = _PLAN_MODE_CLARIFICATION_INTENT_CLASSIFIER.classify(
        reply_prompt="Q1:B, Q2:D, notes: keep it practical and beginner-friendly.",
        root_prompt="Create a planning roadmap with timeline and constraints.",
        pending_dimension="goal",
        question_count=2,
    )
    if result.source == "spacy":
        model_name = result.model_name or "unknown"
        logger.info("Plan-mode NLP preloaded with spaCy model '%s'", model_name)
        return model_name

    load_error = _PLAN_MODE_CLARIFICATION_INTENT_CLASSIFIER.load_error or (
        "spaCy model unavailable for plan-mode classification"
    )
    raise RuntimeError(load_error)


def _normalize_session_id(raw_value: object, *, fallback: str) -> str:
    """Normalize externally provided session ids to a safe filename key."""
    if isinstance(raw_value, str):
        cleaned = _SESSION_ID_SANITIZER.sub("-", raw_value.strip())
        cleaned = cleaned.strip("-.")
        if cleaned:
            return cleaned[:96]
    return fallback


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


def _model_supports_native_deep_think(model_name: str) -> bool:
    """Return whether a model supports strict deep-think controls."""
    normalized = model_name.strip().lower()
    return "gemini-3" in normalized or "gemini-2.5" in normalized


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


def _parse_plan_mode_discovery_budget() -> int:
    raw = os.environ.get(
        "AI_AGENT_PLAN_MODE_DISCOVERY_BEFORE_PLANNER",
        str(_PLAN_MODE_DISCOVERY_BEFORE_PLANNER_DEFAULT),
    )
    try:
        parsed = int(str(raw).strip())
    except ValueError:
        return _PLAN_MODE_DISCOVERY_BEFORE_PLANNER_DEFAULT
    return max(0, min(8, parsed))


def _parse_plan_mode_clarification_required() -> bool:
    raw = os.environ.get(
        "AI_AGENT_PLAN_MODE_CLARIFICATION_REQUIRED",
        "true" if _PLAN_MODE_CLARIFICATION_REQUIRED_DEFAULT else "false",
    )
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return _PLAN_MODE_CLARIFICATION_REQUIRED_DEFAULT


def _parse_plan_mode_clarification_min_missing() -> int:
    raw = os.environ.get(
        "AI_AGENT_PLAN_MODE_CLARIFICATION_MIN_MISSING",
        str(_PLAN_MODE_CLARIFICATION_MIN_MISSING_DEFAULT),
    )
    try:
        parsed = int(str(raw).strip())
    except ValueError:
        return _PLAN_MODE_CLARIFICATION_MIN_MISSING_DEFAULT
    return max(1, min(4, parsed))


def _parse_plan_mode_clarification_max_rounds() -> int:
    raw = os.environ.get(
        "AI_AGENT_PLAN_MODE_CLARIFICATION_MAX_ROUNDS",
        str(_PLAN_MODE_CLARIFICATION_MAX_ROUNDS_DEFAULT),
    )
    try:
        parsed = int(str(raw).strip())
    except ValueError:
        return _PLAN_MODE_CLARIFICATION_MAX_ROUNDS_DEFAULT
    return max(1, min(2, parsed))


def _parse_plan_mode_clarification_score_threshold() -> float:
    raw = os.environ.get(
        "AI_AGENT_PLAN_MODE_CLARIFICATION_SCORE_THRESHOLD",
        str(_PLAN_MODE_CLARIFICATION_SCORE_THRESHOLD_DEFAULT),
    )
    try:
        parsed = float(str(raw).strip())
    except ValueError:
        return _PLAN_MODE_CLARIFICATION_SCORE_THRESHOLD_DEFAULT
    return max(0.05, min(0.95, parsed))


def _parse_plan_mode_clarification_confidence_target() -> float:
    raw = os.environ.get(
        "AI_AGENT_PLAN_MODE_CLARIFICATION_CONFIDENCE_TARGET",
        str(_PLAN_MODE_CLARIFICATION_CONFIDENCE_TARGET_DEFAULT),
    )
    try:
        parsed = float(str(raw).strip())
    except ValueError:
        return _PLAN_MODE_CLARIFICATION_CONFIDENCE_TARGET_DEFAULT
    return max(0.40, min(0.98, parsed))


def _prompt_has_actionable_file_operation_intent(prompt: str) -> bool:
    normalized = prompt.strip().lower()
    if not normalized:
        return False
    if any(phrase in normalized for phrase in _PLAN_MODE_EXPLICIT_OPERATION_PHRASES):
        return True
    has_operation_verb = bool(_PLAN_MODE_OP_VERB_PATTERN.search(normalized))
    if not has_operation_verb:
        return False
    if _PLAN_MODE_OP_OBJECT_PATTERN.search(normalized):
        return True
    if _PLAN_MODE_OP_DEMONSTRATIVE_INTENT_PATTERN.search(normalized):
        return True
    return False


def _should_run_plan_mode_clarification(
    *,
    prompt: str,
    clarification_required: bool,
    requires_unified_planning: bool,
) -> bool:
    """Run clarification when it improves plan quality without blocking planning safety gates."""
    if not clarification_required:
        return False
    if _prompt_explicitly_requests_preplan_clarification(prompt):
        return True
    # File operations also benefit from clarification (goal + constraints).
    # The unified planner bootstrap runs after clarification resolves.
    return True


def _plan_mode_missing_clarification_dimensions(prompt: str) -> list[str]:
    normalized = prompt.strip().lower()
    goal_present = bool(normalized and _PLAN_MODE_GOAL_SIGNAL_PATTERN.search(normalized))
    timeframe_present = bool(normalized and _PLAN_MODE_TIMEFRAME_SIGNAL_PATTERN.search(normalized))
    baseline_present = bool(normalized and _PLAN_MODE_BASELINE_SIGNAL_PATTERN.search(normalized))
    constraints_present = bool(normalized and _PLAN_MODE_CONSTRAINT_SIGNAL_PATTERN.search(normalized))
    # Use profile signals as fallback for baseline and constraints — the profile
    # extractor already has rich patterns for privacy, retention, rollback, volume,
    # etc. that indicate the user has described their environment or constraints.
    if normalized and (not baseline_present or not constraints_present):
        profile = _extract_plan_prompt_profile(prompt)
        if not baseline_present:
            baseline_present = bool(profile.volume_hint) or len(profile.topic_hints) >= 2
        if not constraints_present:
            constraints_present = any((
                profile.has_privacy_signal,
                profile.has_retention_signal,
                profile.has_rollback_signal,
                profile.has_no_delete_signal,
                profile.has_weekday_time_limit,
                profile.prefers_weekend_batches,
                profile.has_helper_signal,
            ))
    dimensions: list[tuple[str, bool]] = [
        ("goal", goal_present),
        ("timeframe", timeframe_present),
        ("baseline", baseline_present),
        ("constraints", constraints_present),
    ]
    return [name for name, present in dimensions if not present]


def _infer_plan_query_domain(prompt: str) -> str:
    normalized = prompt.strip().lower()
    if _prompt_has_actionable_file_operation_intent(normalized):
        return "files"
    if any(
        keyword in normalized
        for keyword in ("study", "learn", "course", "exam", "certification", "roadmap")
    ):
        return "study"
    if any(
        keyword in normalized
        for keyword in ("build", "project", "implement", "feature", "system", "architecture")
    ):
        return "project"
    return "general"


def _plan_dimension_priority_for_domain(domain: str) -> list[str]:
    if domain == "study":
        return ["goal", "baseline", "timeframe", "constraints"]
    if domain == "files":
        return ["goal", "constraints", "timeframe", "baseline"]
    if domain == "project":
        return ["goal", "constraints", "timeframe", "baseline"]
    return ["goal", "timeframe", "constraints", "baseline"]


def _plan_mode_clarification_dimensions_for_prompt(prompt: str, domain: str) -> list[str]:
    if _prompt_explicitly_requests_preplan_clarification(prompt):
        return _plan_dimension_priority_for_domain(domain)[:4]
    missing = _plan_mode_missing_clarification_dimensions(prompt)
    priority = _plan_dimension_priority_for_domain(domain)
    ordered_missing = [dimension for dimension in priority if dimension in missing]
    if ordered_missing:
        return ordered_missing[:4]
    return priority[:1]


def _plan_mode_prompt_complexity(prompt: str) -> float:
    words = max(1, len(prompt.split()))
    return max(0.1, min(1.0, words / 24.0))


def _compute_plan_mode_clarification_score(
    *,
    prompt: str,
    missing_dimensions: list[str],
    asked_rounds: int,
) -> float:
    domain = _infer_plan_query_domain(prompt)
    ambiguity = len(missing_dimensions) / 4.0
    complexity = _plan_mode_prompt_complexity(prompt)
    irreversible_risk = 1.0 if domain == "files" else 0.65
    expected_plan_gain = min(1.0, 0.35 + (0.45 * complexity))
    friction_cost = 0.16 + (asked_rounds * 0.14)
    score = (
        (ambiguity * 0.55)
        + (expected_plan_gain * 0.30)
        + (irreversible_risk * 0.15)
        - friction_cost
    )
    return max(0.0, min(1.0, score))


def _dynamic_plan_mode_clarification_threshold(prompt: str) -> float:
    domain = _infer_plan_query_domain(prompt)
    complexity = _plan_mode_prompt_complexity(prompt)
    missing_count = len(_plan_mode_missing_clarification_dimensions(prompt))
    threshold = 0.25 + (0.15 * complexity)
    if domain == "files":
        threshold += 0.06
    if missing_count >= 3:
        threshold -= 0.05
    if missing_count <= 1:
        threshold += 0.10
    return max(0.12, min(0.82, threshold))


def _prompt_explicitly_requests_preplan_clarification(prompt: str) -> bool:
    normalized = prompt.strip().lower()
    if not normalized:
        return False
    tokens = _plan_mode_token_set(normalized)
    if not tokens:
        return False

    question_terms = {"clarify", "clarification", "clarifying", "question", "questions", "ask"}
    sequencing_terms = {"before", "first", "prior", "initially"}
    planning_terms = {"plan", "roadmap", "draft", "writing", "write", "creating", "create"}

    has_question_signal = any(term in tokens for term in question_terms)
    has_sequence_signal = any(term in tokens for term in sequencing_terms)
    has_plan_signal = any(term in tokens for term in planning_terms)
    if has_question_signal and has_sequence_signal and has_plan_signal:
        return True

    strong_phrase_patterns = (
        r"\bask all clarification questions\b",
        r"\bask clarifying questions\b",
        r"\bbefore writing the plan\b",
        r"\bbefore (you )?(write|draft|create) (the )?plan\b",
    )
    return any(re.search(pattern, normalized) for pattern in strong_phrase_patterns)


def _prompt_requires_plan_mode_clarification(prompt: str) -> bool:
    if _prompt_explicitly_requests_preplan_clarification(prompt):
        return True
    missing = _plan_mode_missing_clarification_dimensions(prompt)
    if len(missing) < _parse_plan_mode_clarification_min_missing():
        return False
    score = _compute_plan_mode_clarification_score(
        prompt=prompt,
        missing_dimensions=missing,
        asked_rounds=0,
    )
    threshold = _dynamic_plan_mode_clarification_threshold(prompt)
    return score >= threshold


_PLAN_MODE_FOLLOWUP_PATTERN = re.compile(
    r"^(?:yes|yeah|yep|yup|ok|okay|sure|go\s*ahead|proceed|do\s*it|start|execute|"
    r"let'?s?\s*(?:go|do\s*it|start)|sounds?\s*good|perfect|great|approved?|confirm(?:ed)?"
    r"|no|nope|not?\s*yet|wait|hold|stop|cancel|revise|change|modify|adjust|redo"
    r"|what\s*about|how\s*about|can\s*you|could\s*you|also|instead|actually"
    r"|thanks?|thank\s*you)[\s!?.]*$",
    re.IGNORECASE,
)

# Matches messages that reference existing session notes — used to detect
# follow-ups like "elaborate on the 2 notes" that should bypass the length
# threshold since they are unambiguously about existing session content.
_NOTE_FOLLOWUP_PATTERN = re.compile(
    r"(?:the|these|those|my|both|all|each|existing)\s+(?:\d+\s+)?notes?"
    r"|(?:elaborate|expand|detail|improve|rewrite|update|add\s*more|break\s*down"
    r"|summarize|shorten|condense|merge|combine|split)\s+.*(?:notes?|them|it|this)"
    r"|(?:notes?|them)\s+.*(?:more\s+detail|bullet|detailed|verbose|concise)"
    r"|make\s+(?:them|it|the\s+notes?)\s+(?:more\s+)?(?:detailed|concise|shorter|longer|better)",
    re.IGNORECASE,
)


def _is_plan_mode_followup(prompt: str, session_has_plan: bool) -> bool:
    """Detect follow-up messages to an existing plan (vs new planning requests)."""
    if not session_has_plan:
        return False
    normalized = prompt.strip()
    if not normalized:
        return False
    # Short messages that match conversational patterns are follow-ups.
    if len(normalized) < 80 and _PLAN_MODE_FOLLOWUP_PATTERN.match(normalized):
        return True
    # Very short messages (< 40 chars) without new-planning signals are follow-ups.
    if len(normalized) < 40:
        lower = normalized.lower()
        if not _PLAN_MODE_GOAL_SIGNAL_PATTERN.search(lower):
            return True
    # Note-referencing follow-ups (any length) — user wants to modify/expand
    # existing notes.  These bypass the length threshold because they are
    # unambiguously about existing session content, not new planning requests.
    if _NOTE_FOLLOWUP_PATTERN.search(normalized):
        return True
    return False


_PLAN_MODE_APPROVAL_PATTERN = re.compile(
    r"^(?:yes|yeah|yep|yup|ok|okay|sure|go\s*ahead|proceed|do\s*it|start|execute|"
    r"let'?s?\s*(?:go|do\s*it|start)|sounds?\s*good|perfect|great|approved?|confirm(?:ed)?)[\s!?.]*$",
    re.IGNORECASE,
)


def _is_plan_mode_execution_approval(prompt: str) -> bool:
    """True when the user approves plan execution (affirmative response)."""
    return bool(_PLAN_MODE_APPROVAL_PATTERN.match(prompt.strip()))


def _plan_mode_topic_snippet(prompt: str) -> str:
    compact = re.sub(r"\s+", " ", prompt.strip())
    if not compact:
        return "your request"
    if len(compact) <= 84:
        return compact
    return f"{compact[:81].rstrip()}..."


def _extract_plan_prompt_profile(prompt: str) -> PlanPromptProfile:
    normalized = prompt.strip().lower()
    if not normalized:
        return PlanPromptProfile()

    timeline_hint = ""
    timeline_match = _PLAN_MODE_TIMELINE_HINT_PATTERN.search(normalized)
    if timeline_match:
        timeline_hint = re.sub(r"\s+", " ", timeline_match.group(1).strip())

    volume_hint = ""
    volume_match = _PLAN_MODE_VOLUME_HINT_PATTERN.search(normalized)
    if volume_match:
        volume_hint = f"{volume_match.group(1)} {volume_match.group(2).upper()}"

    topic_positions: list[tuple[int, str]] = []
    for hint in _PLAN_MODE_TOPIC_HINT_ALLOWLIST:
        match = re.search(rf"\b{re.escape(hint)}\b", normalized)
        if match is None:
            continue
        topic_positions.append((match.start(), hint))
    topic_positions.sort(key=lambda item: item[0])
    topic_hints = tuple(hint for _, hint in topic_positions[:4])

    return PlanPromptProfile(
        timeline_hint=timeline_hint,
        volume_hint=volume_hint,
        has_privacy_signal=bool(_PLAN_MODE_PRIVACY_SIGNAL_PATTERN.search(normalized)),
        has_rollback_signal=bool(_PLAN_MODE_ROLLBACK_SIGNAL_PATTERN.search(normalized)),
        has_no_delete_signal=bool(_PLAN_MODE_NO_DELETE_SIGNAL_PATTERN.search(normalized)),
        has_helper_signal=bool(_PLAN_MODE_HELPER_SIGNAL_PATTERN.search(normalized)),
        has_retention_signal=bool(_PLAN_MODE_RETENTION_SIGNAL_PATTERN.search(normalized)),
        prefers_weekend_batches=bool(_PLAN_MODE_WEEKEND_SIGNAL_PATTERN.search(normalized)),
        has_weekday_time_limit=bool(_PLAN_MODE_WEEKDAY_LIMIT_SIGNAL_PATTERN.search(normalized)),
        topic_hints=topic_hints,
    )


def _plan_prompt_profile_summary(profile: PlanPromptProfile) -> str:
    signals: list[str] = []
    if profile.timeline_hint:
        signals.append(f"timeline={profile.timeline_hint}")
    if profile.volume_hint:
        signals.append(f"data_volume={profile.volume_hint}")
    if profile.has_privacy_signal:
        signals.append("privacy-sensitive")
    if profile.has_no_delete_signal:
        signals.append("no-permanent-delete-first")
    if profile.has_rollback_signal:
        signals.append("rollback-required")
    if profile.has_retention_signal:
        signals.append("retention/compliance-aware")
    if profile.has_helper_signal:
        signals.append("multi-person execution")
    if profile.prefers_weekend_batches:
        signals.append("weekend-batch preference")
    if profile.has_weekday_time_limit:
        signals.append("weekday-time constraints")
    if profile.topic_hints:
        signals.append(f"scope={', '.join(profile.topic_hints)}")
    if not signals:
        return ""
    return f"Detected query signals: {'; '.join(signals)}."


def _plan_dimension_prompt(
    dimension: str,
    domain: str,
    profile: PlanPromptProfile | None = None,
) -> str:
    profile = profile or PlanPromptProfile()
    if dimension == "goal":
        if domain == "study":
            return "What outcome should this plan prioritize?"
        if domain == "files":
            if profile.has_privacy_signal and profile.has_no_delete_signal:
                return (
                    "What should this file-organization plan prioritize first under "
                    "privacy-first and no-permanent-delete constraints?"
                )
            if profile.has_privacy_signal:
                return "What should this privacy-first file-organization plan optimize for first?"
            if profile.has_no_delete_signal:
                return (
                    "What should this file-organization plan prioritize first while avoiding "
                    "permanent deletion in early phases?"
                )
            return "What is the planning objective for these file operations?"
        return "What outcome should this plan target?"
    if dimension == "baseline":
        if profile.has_helper_signal:
            return "What baseline should I assume for you and any non-technical helpers?"
        return "What is your starting point?"
    if dimension == "timeframe":
        if profile.timeline_hint:
            return f"What timeline should I anchor to (you mentioned {profile.timeline_hint})?"
        return "What timeline should the plan follow?"
    if dimension == "constraints":
        if profile.prefers_weekend_batches and profile.has_weekday_time_limit:
            return (
                "Which scheduling constraint style should I optimize for across "
                "weekday-light and weekend-heavy availability?"
            )
        if profile.has_weekday_time_limit:
            return "Which constraint style should I optimize for with limited weekday capacity?"
        return "Which constraint style should I optimize for?"
    return "Which planning style do you prefer?"


def _plan_dimension_why(
    dimension: str,
    domain: str,
    profile: PlanPromptProfile | None = None,
) -> str:
    profile = profile or PlanPromptProfile()
    if dimension == "goal":
        if domain == "files" and profile.has_no_delete_signal:
            return "It keeps the plan safe, staged, and aligned with your no-permanent-delete requirement."
        return "It prevents optimizing the plan for the wrong end result."
    if dimension == "baseline":
        if profile.has_helper_signal:
            return "It calibrates instructions so non-technical helpers can execute reliably."
        return "It calibrates depth and pacing to your current level."
    if dimension == "timeframe":
        if profile.timeline_hint:
            return "It confirms whether I should lock to your stated timeline or reshape scope around it."
        return "It aligns scope with your actual delivery window."
    if dimension == "constraints":
        if domain == "files":
            if profile.has_privacy_signal or profile.has_retention_signal:
                return "It balances privacy/compliance controls with practical execution pace."
            return "It keeps the plan safe and practical for your operating limits."
        return "It keeps the plan realistic and sustainable."
    return "It reduces ambiguity and improves plan quality."


def _plan_dimension_option_catalog(
    dimension: str,
    domain: str,
    profile: PlanPromptProfile | None = None,
) -> list[tuple[str, str, float]]:
    profile = profile or PlanPromptProfile()
    if dimension == "goal" and domain == "study":
        return [
            ("A", "Strong fundamentals first", 0.72),
            ("B", "Exam/assessment readiness", 0.78),
            ("C", "Practical portfolio outcomes", 0.67),
            ("D", "Balanced theory + practice", 0.83),
        ]
    if dimension == "goal" and domain == "files":
        option_a = "High-level strategy only (no execution)"
        option_b = "Safe step-by-step dry run"
        option_c = "Aggressive cleanup/organization"
        option_d = "Minimal-change optimization"
        if profile.has_privacy_signal:
            option_a = "Privacy-first strategy blueprint only (no execution)"
            option_b = f"{option_b} with privacy-preserving controls"
        if profile.has_no_delete_signal:
            option_b = f"{option_b} and no permanent deletions in early phases"
        if profile.has_rollback_signal:
            option_b = f"{option_b} with rollback checkpoints"
        if profile.has_retention_signal:
            option_d = "Retention/compliance-first minimal-change optimization"
        return [
            ("A", option_a, 0.66),
            ("B", option_b, 0.88),
            ("C", option_c, 0.61),
            ("D", option_d, 0.81),
        ]
    if dimension == "goal":
        return [
            ("A", "Beginner-friendly structured path", 0.73),
            ("B", "Practical intermediate path", 0.79),
            ("C", "Advanced/accelerated path", 0.62),
            ("D", "Concise high-level roadmap", 0.75),
        ]
    if dimension == "baseline":
        if profile.has_helper_signal:
            return [
                ("A", "Solo execution only", 0.68),
                ("B", "Mixed helpers, low technical comfort", 0.84),
                ("C", "Mixed helpers, moderate technical comfort", 0.78),
                ("D", "Unknown helper baseline; infer conservative defaults", 0.63),
            ]
        return [
            ("A", "New to this", 0.70),
            ("B", "Basic familiarity", 0.78),
            ("C", "Comfortable, need structure", 0.81),
            ("D", "Not sure; infer from best practices", 0.64),
        ]
    if dimension == "timeframe":
        if profile.timeline_hint:
            return [
                ("A", f"Anchor to requested timeline ({profile.timeline_hint})", 0.88),
                ("B", f"Slightly faster than {profile.timeline_hint}", 0.66),
                ("C", f"More conservative than {profile.timeline_hint}", 0.76),
                ("D", "Adaptive timeline with periodic scope reviews", 0.63),
            ]
        return [
            ("A", "Fast track (1-2 weeks)", 0.62),
            ("B", "Standard (1-2 months)", 0.82),
            ("C", "Extended (3+ months)", 0.74),
            ("D", "No fixed deadline", 0.66),
        ]
    if dimension == "constraints":
        if profile.prefers_weekend_batches and profile.has_weekday_time_limit:
            return [
                ("A", "Weekday micro-sessions + weekend batch blocks", 0.90),
                ("B", "Weekend-only deep work blocks", 0.76),
                ("C", "High-intensity compression regardless of schedule", 0.58),
                ("D", "Balanced cadence with mandatory recovery buffers", 0.69),
            ]
        if profile.has_weekday_time_limit:
            return [
                ("A", "Minimal weekday effort with strict time caps", 0.88),
                ("B", "Flexible weekday effort with optional overflow", 0.72),
                ("C", "Maximum speed even if weekday load spikes", 0.57),
                ("D", "Balanced pace with conservative workload limits", 0.79),
            ]
        return [
            ("A", "Minimal daily time", 0.79),
            ("B", "Weekend/batch sessions", 0.70),
            ("C", "Maximum speed and intensity", 0.61),
            ("D", "Balanced sustainable pace", 0.86),
        ]
    return [
        ("A", "Highly structured milestones", 0.76),
        ("B", "Flexible checkpoints", 0.73),
        ("C", "Lightweight action list", 0.67),
        ("D", "Deep-dive with contingencies", 0.64),
    ]


def _rank_plan_dimension_options(
    catalog: list[tuple[str, str, float]],
    *,
    dimension: str,
    session_learning: dict[str, dict[str, float]] | None,
    global_learning: dict[str, dict[str, float]] | None,
) -> list[tuple[str, str]]:
    del dimension, session_learning, global_learning
    ranked = sorted(catalog, key=lambda entry: entry[0])
    return [(key, text) for key, text, _ in ranked]


def _build_plan_mode_choice_question(
    *,
    dimension: str,
    prompt: str,
    session_learning: dict[str, dict[str, float]] | None = None,
    global_learning: dict[str, dict[str, float]] | None = None,
) -> tuple[str, list[tuple[str, str]], str]:
    domain = _infer_plan_query_domain(prompt)
    profile = _extract_plan_prompt_profile(prompt)
    question = _plan_dimension_prompt(dimension, domain, profile=profile)
    why = _plan_dimension_why(dimension, domain, profile=profile)
    catalog = _plan_dimension_option_catalog(dimension, domain, profile=profile)
    options = _rank_plan_dimension_options(
        catalog,
        dimension=dimension,
        session_learning=session_learning,
        global_learning=global_learning,
    )
    return question, options, why


def _next_plan_clarification_dimension(state: PlanClarificationState) -> str | None:
    missing = _plan_mode_missing_clarification_dimensions(state.root_prompt)
    priority = _plan_dimension_priority_for_domain(state.domain)
    for dimension in priority:
        if dimension in missing and dimension not in state.answered_dimensions:
            return dimension
    for dimension in priority:
        if dimension not in state.answered_dimensions:
            return dimension
    return None


def _extract_plan_option_choice(prompt: str, *, question_number: int) -> str | None:
    for match in _PLAN_MODE_ANSWER_Q_PATTERN.finditer(prompt):
        if int(match.group(1)) == question_number:
            choice = match.group(2).upper()
            if choice in _PLAN_MODE_OPTION_KEYS:
                return choice
    single = _PLAN_MODE_SINGLE_OPTION_PATTERN.match(prompt.strip())
    if single is not None:
        choice = single.group(1).upper()
        if choice in _PLAN_MODE_OPTION_KEYS:
            return choice
    return None


def _extract_all_plan_option_choices(prompt: str) -> dict[int, str]:
    choices: dict[int, str] = {}
    for match in _PLAN_MODE_ANSWER_Q_PATTERN.finditer(prompt):
        choice = match.group(2).upper()
        if choice in _PLAN_MODE_OPTION_KEYS:
            choices[int(match.group(1))] = choice
    return choices


def _plan_mode_token_set(text: str) -> set[str]:
    return set(_PLAN_MODE_TOKEN_PATTERN.findall(text.lower()))


def _plan_mode_signal_strength(
    *,
    normalized_reply: str,
    pending_dimension: str | None,
    question_count: int,
) -> float:
    goal_hit = bool(_PLAN_MODE_GOAL_SIGNAL_PATTERN.search(normalized_reply))
    timeframe_hit = bool(_PLAN_MODE_TIMEFRAME_SIGNAL_PATTERN.search(normalized_reply))
    baseline_hit = bool(_PLAN_MODE_BASELINE_SIGNAL_PATTERN.search(normalized_reply))
    constraints_hit = bool(_PLAN_MODE_CONSTRAINT_SIGNAL_PATTERN.search(normalized_reply))
    total_hits = int(goal_hit) + int(timeframe_hit) + int(baseline_hit) + int(constraints_hit)

    if pending_dimension == "goal":
        return 1.0 if goal_hit else 0.0
    if pending_dimension == "timeframe":
        return 1.0 if timeframe_hit else 0.0
    if pending_dimension == "baseline":
        return 1.0 if baseline_hit else 0.0
    if pending_dimension == "constraints":
        return 1.0 if constraints_hit else 0.0

    if question_count > 1:
        return min(1.0, total_hits / 2.0)
    return 1.0 if total_hits > 0 else 0.0


def _looks_like_plan_clarification_reply(prompt: str, state: PlanClarificationState) -> bool:
    explicit_choices = _extract_all_plan_option_choices(prompt)
    if explicit_choices:
        return True
    if (
        _PLAN_MODE_SINGLE_OPTION_PATTERN.match(prompt.strip()) is not None
        and len(state.question_dimensions) <= 1
    ):
        return True
    normalized = prompt.strip().lower()
    if not normalized:
        return False
    if _PLAN_MODE_CLARIFICATION_PREFIX_PATTERN.match(normalized):
        return True
    if normalized.endswith("?"):
        return False
    # A prompt substantially longer than the root is likely a new task, not a reply.
    root_len = len(state.root_prompt.strip())
    if root_len > 0 and len(normalized) > root_len * 1.5 and len(normalized) > 200:
        return False

    pending_dimension = (state.pending_dimension or "").strip().lower() or None
    question_count = max(1, len(state.question_dimensions))
    intent_result = _PLAN_MODE_CLARIFICATION_INTENT_CLASSIFIER.classify(
        reply_prompt=prompt,
        root_prompt=state.root_prompt,
        pending_dimension=pending_dimension,
        question_count=question_count,
    )

    reply_tokens = _plan_mode_token_set(intent_result.sanitized_reply or normalized)
    if not reply_tokens:
        return False
    root_tokens = _plan_mode_token_set(intent_result.sanitized_root_prompt or state.root_prompt)
    overlap_count = len(reply_tokens.intersection(root_tokens))
    overlap_signal = min(1.0, overlap_count / max(1, min(len(reply_tokens), len(root_tokens))))

    signal_strength = _plan_mode_signal_strength(
        normalized_reply=normalized,
        pending_dimension=pending_dimension,
        question_count=question_count,
    )

    word_count = len(normalized.split())
    shape_signal = 1.0 if 1 <= word_count <= 48 else (0.7 if word_count <= 96 else 0.35)
    if "," in normalized or "\n" in prompt:
        shape_signal = min(1.0, shape_signal + 0.08)

    actionable_intent = _prompt_has_actionable_file_operation_intent(normalized)
    if actionable_intent and state.domain != "files":
        return False

    heuristic_score = (signal_strength * 0.48) + (overlap_signal * 0.34) + (shape_signal * 0.18)
    score = (heuristic_score * 0.40) + (intent_result.confidence * 0.60)
    threshold = 0.34 if question_count > 1 else 0.42
    if state.domain == "files":
        threshold += 0.06
    if intent_result.source != "spacy":
        logger.warning(
            "Plan clarification classifier unavailable (source=%s); refusing fallback path",
            intent_result.source,
        )
        return False
    return intent_result.is_clarification_reply and score >= threshold


def _update_clarification_state_from_reply(
    *,
    state: PlanClarificationState,
    prompt: str,
    session_learning: dict[str, dict[str, float]] | None,
    global_learning: dict[str, dict[str, float]] | None,
) -> bool:
    dimensions = state.question_dimensions or _plan_mode_clarification_dimensions_for_prompt(
        state.root_prompt,
        state.domain,
    )
    if not dimensions:
        return False

    explicit_choices = _extract_all_plan_option_choices(prompt)
    if not explicit_choices:
        single = _PLAN_MODE_SINGLE_OPTION_PATTERN.match(prompt.strip())
        if single is not None and len(dimensions) == 1:
            explicit_choices = {1: single.group(1).upper()}

    applied_dimensions: set[str] = set()
    confidence_signals: list[float] = []

    for question_number, selected_key in sorted(explicit_choices.items()):
        if question_number < 1 or question_number > len(dimensions):
            continue
        if selected_key not in _PLAN_MODE_OPTION_KEYS:
            continue
        dimension = dimensions[question_number - 1]
        _, options, _ = _build_plan_mode_choice_question(
            dimension=dimension,
            prompt=state.root_prompt,
            session_learning=session_learning,
            global_learning=global_learning,
        )
        option_lookup = {key: value for key, value in options}
        option_count = max(1, len(options))
        rank_lookup = {key: index for index, (key, _) in enumerate(options)}
        selected_value = option_lookup.get(selected_key, "").strip()
        if not selected_value:
            continue
        state.option_answers[dimension] = selected_key
        state.answered_dimensions[dimension] = selected_value
        applied_dimensions.add(dimension)
        confidence_signals.append(
            _compute_dynamic_reply_confidence_signal(
                root_prompt=state.root_prompt,
                reply_prompt=prompt,
                selected_key=selected_key,
                option_rank=rank_lookup.get(selected_key, 0),
                option_count=option_count,
            )
        )

    if not applied_dimensions:
        custom = prompt.strip()
        if not custom:
            return False
        if custom.lower().startswith("notes:"):
            custom = custom[6:].strip()
        if not custom:
            return False
        unresolved = [dimension for dimension in dimensions if dimension not in state.answered_dimensions]
        if not unresolved:
            # All dimensions answered — append custom note to the last answered dimension
            # rather than silently overwriting the first one.
            last_dim = dimensions[-1] if dimensions else None
            if last_dim:
                existing = state.answered_dimensions.get(last_dim, "")
                state.answered_dimensions[last_dim] = f"{existing}; {custom}" if existing else custom
                applied_dimensions.add(last_dim)
        else:
            for dimension in unresolved:
                state.answered_dimensions[dimension] = custom
                applied_dimensions.add(dimension)
        confidence_signals.append(
            _compute_dynamic_reply_confidence_signal(
                root_prompt=state.root_prompt,
                reply_prompt=prompt,
                selected_key=None,
                option_rank=0,
                option_count=4,
            )
        )

    state.answers_count += len(applied_dimensions)
    signal = sum(confidence_signals) / max(1, len(confidence_signals))
    answered_count = sum(1 for dimension in dimensions if dimension in state.answered_dimensions)
    coverage_target = max(1, len(dimensions))
    coverage = min(1.0, answered_count / coverage_target)
    complexity = _plan_mode_prompt_complexity(state.root_prompt)
    alpha = min(0.8, max(0.25, 0.30 + (0.35 * complexity)))
    blended = ((1.0 - alpha) * state.confidence) + (alpha * signal)
    state.confidence = max(blended, ((coverage * 0.55) + (signal * 0.45)))
    state.confidence = max(0.0, min(0.98, state.confidence))
    return True


def _compute_dynamic_reply_confidence_signal(
    *,
    root_prompt: str,
    reply_prompt: str,
    selected_key: str | None,
    option_rank: int,
    option_count: int,
) -> float:
    reply = reply_prompt.strip()
    words = max(1, len(reply.split()))
    detail_signal = max(0.15, min(1.0, words / 18.0))
    structured_signal = 1.0 if selected_key is not None else 0.55
    complexity = _plan_mode_prompt_complexity(root_prompt)

    option_rank_signal = 0.6
    if selected_key is not None:
        option_rank_signal = max(
            0.2,
            min(
                1.0,
                (option_count - option_rank) / max(1, option_count),
            ),
        )

    specificity_hits = 0
    normalized_reply = reply.lower()
    if _PLAN_MODE_TIMEFRAME_SIGNAL_PATTERN.search(normalized_reply):
        specificity_hits += 1
    if _PLAN_MODE_BASELINE_SIGNAL_PATTERN.search(normalized_reply):
        specificity_hits += 1
    if _PLAN_MODE_CONSTRAINT_SIGNAL_PATTERN.search(normalized_reply):
        specificity_hits += 1
    if _PLAN_MODE_GOAL_SIGNAL_PATTERN.search(normalized_reply):
        specificity_hits += 1
    specificity_signal = min(1.0, specificity_hits / 2.0) if specificity_hits else (detail_signal * 0.7)

    dynamic_weights = [
        0.22 + (0.12 * complexity),  # detail
        0.22,  # structured
        0.21,  # ranking
        0.35 - (0.12 * complexity),  # specificity
    ]
    total_weight = sum(dynamic_weights) or 1.0
    weighted = (
        (detail_signal * dynamic_weights[0])
        + (structured_signal * dynamic_weights[1])
        + (option_rank_signal * dynamic_weights[2])
        + (specificity_signal * dynamic_weights[3])
    ) / total_weight
    return max(0.0, min(1.0, weighted))


def _compute_dynamic_plan_clarification_policy(
    *,
    root_prompt: str,
    answered_count: int,
) -> tuple[int, float]:
    complexity = _plan_mode_prompt_complexity(root_prompt)
    missing_count = len(_plan_mode_missing_clarification_dimensions(root_prompt))
    base_rounds = 1 + int((complexity * missing_count) >= 1.65)
    configured_cap = _parse_plan_mode_clarification_max_rounds()
    max_rounds = max(1, min(configured_cap, base_rounds))
    if answered_count > 0:
        max_rounds = max(1, max_rounds - 1)

    confidence_target = 0.62 + (0.22 * min(1.0, complexity))
    if missing_count <= 1:
        confidence_target -= 0.06
    confidence_target = max(0.52, min(0.90, confidence_target))
    return max_rounds, confidence_target


def _update_plan_option_learning(
    learning: dict[str, dict[str, float]],
    *,
    dimension: str,
    option_key: str,
    weight: float = 1.0,
) -> None:
    options = learning.setdefault(dimension, {})
    options[option_key] = float(options.get(option_key, 0.0) + weight)


def _build_plan_clarification_context_block(
    state: PlanClarificationState,
    *,
    session_learning: dict[str, dict[str, float]] | None,
    global_learning: dict[str, dict[str, float]] | None,
) -> str:
    labels = {
        "goal": "Goal",
        "baseline": "Baseline",
        "timeframe": "Timeline",
        "constraints": "Constraints",
    }
    lines = [
        "[PLAN_CLARIFICATION_CONTEXT]",
        "Use these user-confirmed clarifications while planning:",
    ]
    for dimension in _plan_dimension_priority_for_domain(state.domain):
        answer = state.answered_dimensions.get(dimension)
        if answer:
            lines.append(f"- {labels.get(dimension, dimension.title())}: {answer}")
    missing_dimensions: list[str] = []
    for dimension in _plan_dimension_priority_for_domain(state.domain):
        if dimension in state.answered_dimensions:
            continue
        missing_dimensions.append(dimension)
    if missing_dimensions:
        lines.append("")
        lines.append("Assumptions used (can be revised by user):")
        for dimension in missing_dimensions:
            _, ranked_options, _ = _build_plan_mode_choice_question(
                dimension=dimension,
                prompt=state.root_prompt,
                session_learning=session_learning,
                global_learning=global_learning,
            )
            if not ranked_options:
                continue
            default_key, default_text = ranked_options[0]
            lines.append(
                f"- {labels.get(dimension, dimension.title())}: "
                f"[ASSUMED {default_key}] {default_text}"
            )
    lines.append("Prioritize explicit user inputs over assumptions and keep assumptions visible.")
    return "\n".join(lines)


def _normalize_plan_mode_banner(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return text
    first = lines[0].strip()
    if _PLAN_MODE_BANNER_PLANNING_PATTERN.match(first):
        lines[0] = "PLAN MODE (Planning Only)"
    return "\n".join(lines)


def _sanitize_planner_bootstrap_goal(prompt: str) -> str:
    sanitized = _PLAN_MODE_CLARIFICATION_INTENT_CLASSIFIER.sanitize_text(prompt)
    normalized = re.sub(r"\s+", " ", sanitized).strip()
    if not normalized:
        return "Planning request"
    return normalized[:320]


def _extract_user_confirmed_clarification_answers(clarification_context_block: str) -> list[str]:
    if not clarification_context_block.strip():
        return []
    values: list[str] = []
    for line in clarification_context_block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        if "[ASSUMED " in stripped:
            continue
        if ":" not in stripped:
            continue
        value = stripped.split(":", 1)[1].strip()
        if value:
            values.append(value)
    return values


def _build_plan_mode_alignment_repair_instruction(
    *,
    root_prompt: str,
    clarification_context_block: str,
) -> str:
    lines = [
        "The previous draft was not query-aligned enough.",
        "Rewrite the plan now so it is tightly aligned with the original user request.",
        "Do not ask new clarification questions in this rewrite.",
        "Use concise, structured sections and explicitly map to user-confirmed constraints.",
        f"Original request: {root_prompt}",
    ]
    if clarification_context_block.strip():
        lines.extend(
            [
                "",
                clarification_context_block,
            ]
        )
    return "\n".join(lines)


def _build_plan_mode_post_clarification_instruction(
    *,
    root_prompt: str,
    clarification_context_block: str,
) -> str:
    lines = [
        "You already received the clarification answers.",
        "Do not ask more clarification questions in this turn.",
        "Produce the final plan now and align it tightly to the request.",
        f"Original request: {root_prompt}",
    ]
    if clarification_context_block.strip():
        lines.extend(["", clarification_context_block])
    return "\n".join(lines)


def _compute_plan_mode_alignment_score(
    *,
    root_prompt: str,
    response_text: str,
    clarification_context_block: str,
) -> float:
    normalized_response = response_text.strip().lower()
    if not normalized_response:
        return 0.0

    response_tokens = _plan_mode_token_set(normalized_response)
    if not response_tokens:
        return 0.5

    prompt_tokens = _plan_mode_token_set(root_prompt.lower())
    prompt_overlap = 0.0
    if prompt_tokens:
        prompt_overlap = len(response_tokens.intersection(prompt_tokens)) / max(
            1,
            min(24, len(prompt_tokens)),
        )

    confirmed_answers = _extract_user_confirmed_clarification_answers(clarification_context_block)
    answer_hits = 0
    answer_total = 0
    for answer in confirmed_answers:
        answer_tokens = [token for token in _plan_mode_token_set(answer.lower()) if len(token) >= 4]
        if not answer_tokens:
            continue
        answer_total += 1
        if any(token in response_tokens for token in answer_tokens[:4]):
            answer_hits += 1
    answer_coverage = 1.0 if answer_total == 0 else (answer_hits / answer_total)

    structure_hits = sum(1 for token in _PLAN_MODE_ALIGNMENT_STRUCTURE_TOKENS if token in response_tokens)
    structure_signal = min(1.0, structure_hits / 3.0)

    weighted = (
        (prompt_overlap * 0.50)
        + (answer_coverage * 0.35)
        + (structure_signal * 0.15)
    )
    return max(0.0, min(1.0, weighted))


def _dynamic_plan_mode_alignment_threshold(root_prompt: str) -> float:
    complexity = _plan_mode_prompt_complexity(root_prompt)
    threshold = 0.30 + (0.10 * complexity)
    if _prompt_has_actionable_file_operation_intent(root_prompt):
        threshold += 0.04
    return max(0.28, min(0.55, threshold))


def _build_unified_planning_bootstrap_context(
    planner_execution: Mapping[str, Any],
) -> str:
    output = planner_execution.get("output", {})
    if not isinstance(output, Mapping):
        return ""

    complexity = output.get("complexity", {})
    privacy = output.get("privacy", {})
    factors = complexity.get("factors", {}) if isinstance(complexity, Mapping) else {}
    strategy = str(complexity.get("strategy", "unknown")) if isinstance(complexity, Mapping) else "unknown"
    level = str(complexity.get("level", "unknown")) if isinstance(complexity, Mapping) else "unknown"
    score = complexity.get("score", "unknown") if isinstance(complexity, Mapping) else "unknown"
    op_count = factors.get("op_count", 0) if isinstance(factors, Mapping) else 0
    destructive = factors.get("destructive_op_count", 0) if isinstance(factors, Mapping) else 0
    dependencies = factors.get("dependency_count", 0) if isinstance(factors, Mapping) else 0
    invalid = factors.get("invalid_op_count", 0) if isinstance(factors, Mapping) else 0
    privacy_boundary = bool(privacy.get("boundary_payload_mode_numeric_boolean_only"))
    path_flag = bool(privacy.get("path_data_sent_to_unified_planning"))
    security_locked = bool(privacy.get("planner_security_locked"))

    lines = [
        "[UNIFIED_PLANNING_CONTEXT]",
        "Unified planning is active for this plan-mode request.",
        f"- Complexity: level={level}, score={score}, strategy={strategy}",
        (
            "- Factors: "
            f"op_count={op_count}, destructive={destructive}, invalid={invalid}, dependencies={dependencies}"
        ),
        (
            "- Privacy boundary: "
            f"numeric_boolean_only={privacy_boundary}, path_data_sent={path_flag}, planner_locked={security_locked}"
        ),
        "Use this context as mandatory planning input and keep output query-aligned.",
    ]
    return "\n".join(lines)


def _plan_mode_text_requests_structured_clarification(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if (
        _PLAN_MODE_STRUCTURED_QUESTION_PATTERN.search(lowered)
        and _PLAN_MODE_STRUCTURED_OPTION_BLOCK_PATTERN.search(lowered)
    ):
        return False

    question_marks = lowered.count("?")
    bullet_question_lines = len(_PLAN_MODE_BULLET_QUESTION_LINE_PATTERN.findall(normalized))
    has_clarify_signal = bool(_PLAN_MODE_FOLLOWUP_CLARIFY_SIGNAL_PATTERN.search(lowered))
    return has_clarify_signal and (question_marks >= 2 or bullet_question_lines >= 2)


def _prepare_plan_mode_followup_clarification_state(
    *,
    root_prompt: str,
    state: PlanClarificationState | None,
) -> PlanClarificationState:
    prepared = state if state is not None else _initialize_plan_clarification_state(root_prompt)
    if not prepared.root_prompt.strip():
        prepared.root_prompt = root_prompt
    if not prepared.domain.strip():
        prepared.domain = _infer_plan_query_domain(prepared.root_prompt)

    priority = _plan_dimension_priority_for_domain(prepared.domain)
    unanswered = [dimension for dimension in priority if dimension not in prepared.answered_dimensions]
    prepared.question_dimensions = unanswered[:4]
    if not prepared.question_dimensions:
        prepared.pending_dimension = None
        prepared.pending_question_number = 1
        return prepared
    prepared.pending_dimension = prepared.question_dimensions[0]
    prepared.pending_question_number = 1
    prepared.asked_rounds = max(1, prepared.asked_rounds + 1)
    return prepared


def _build_plan_mode_clarification_turn_response(
    *,
    state: PlanClarificationState,
    session_learning: dict[str, dict[str, float]] | None,
    global_learning: dict[str, dict[str, float]] | None,
    score: float,
) -> str:
    profile = _extract_plan_prompt_profile(state.root_prompt)
    question_dimensions = state.question_dimensions or _plan_mode_clarification_dimensions_for_prompt(
        state.root_prompt,
        state.domain,
    )
    if not question_dimensions:
        question_dimensions = ["goal"]
    lines = [
        "PLAN MODE (Quick Clarification)",
        (
            "I can tailor this plan to your request about "
            f"\"{_plan_mode_topic_snippet(state.root_prompt)}\"."
        ),
        (
            "Provisional direction so far: "
            f"{' + '.join(state.answered_dimensions.values()) if state.answered_dimensions else 'build a safe, practical first draft'}."
        ),
        "Answer these together in one reply for a faster, cleaner plan draft.",
        "",
    ]
    profile_summary = _plan_prompt_profile_summary(profile)
    if profile_summary:
        lines.append(profile_summary)
        lines.append("")
    for question_number, dimension in enumerate(question_dimensions, start=1):
        question, options, why = _build_plan_mode_choice_question(
            dimension=dimension,
            prompt=state.root_prompt,
            session_learning=session_learning,
            global_learning=global_learning,
        )
        lines.append(f"Q{question_number}. {question}")
        lines.append(f"Why it matters: {why}")
        lines.extend([f"{key}) {text}" for key, text in options])
        lines.append("")

    lines.extend(
        [
            "Reply once with all answers (example: Q1:B, Q2:D, Q3:A).",
            "You can also reply in free-form text and I will infer your preferences.",
            "I will keep assumptions explicit so you can adjust them easily.",
            f"(clarify_score={score:.2f}, confidence={state.confidence:.2f})",
        ]
    )
    return "\n".join(lines)


def _initialize_plan_clarification_state(prompt: str) -> PlanClarificationState:
    domain = _infer_plan_query_domain(prompt)
    dimensions = _plan_mode_clarification_dimensions_for_prompt(prompt, domain)
    state = PlanClarificationState(
        root_prompt=prompt,
        domain=domain,
        question_dimensions=dimensions,
        pending_dimension=dimensions[0] if dimensions else "goal",
        pending_question_number=1,
        asked_rounds=1,
    )
    return state


def _should_continue_plan_clarification(
    *,
    state: PlanClarificationState,
    max_rounds: int,
    confidence_target: float,
) -> bool:
    if state.asked_rounds >= max_rounds:
        return False
    if state.confidence >= confidence_target:
        return False
    return _next_plan_clarification_dimension(state) is not None


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


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity setting.
    
    Args:
        verbose: If True, enable DEBUG level logging. Otherwise INFO.
    """
    configure_logging(verbose=verbose)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser.
    
    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="ai-agent",
        description="Personal macOS AI Agent - Process natural language prompts to determine tool calls",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ai-agent "Find all Python files in my Documents folder"
  ai-agent --verbose "Get metadata for ~/Desktop/report.pdf"
  ai-agent --dry-run "Open the Notes app"
  ai-agent --server  # Run IPC server for SwiftUI frontend

Exit Codes:
  0 - Success
  1 - Configuration error (missing API key, invalid config)
  2 - API error (rate limit, network issues)
  3 - Validation error (invalid tool call arguments)
        """,
    )
    
    parser.add_argument(
        "prompt",
        type=str,
        nargs="?",
        default=None,
        help="Natural language prompt describing the desired action",
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output with debug logging",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't call API, just show configuration",
    )
    
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    
    parser.add_argument(
        "--server",
        action="store_true",
        help="Run IPC server for SwiftUI frontend communication",
    )
    
    parser.add_argument(
        "--socket-path",
        type=str,
        default=None,
        help="Custom socket path for IPC server (default: /tmp/ai-agent-<pid>.sock)",
    )
    
    return parser


def print_error(message: str, no_color: bool = False) -> None:
    """Print an error message to stderr.
    
    Args:
        message: Error message to print.
        no_color: If True, don't use ANSI colors.
    """
    if no_color:
        print(f"Error: {message}", file=sys.stderr)
    else:
        print(f"\033[91mError:\033[0m {message}", file=sys.stderr)


def print_success(message: str, no_color: bool = False) -> None:
    """Print a success message to stdout.
    
    Args:
        message: Success message to print.
        no_color: If True, don't use ANSI colors.
    """
    if no_color:
        print(f"Success: {message}")
    else:
        print(f"\033[92mSuccess:\033[0m {message}")


def print_info(message: str, no_color: bool = False) -> None:
    """Print an info message to stdout.
    
    Args:
        message: Info message to print.
        no_color: If True, don't use ANSI colors.
    """
    if no_color:
        print(f"Info: {message}")
    else:
        print(f"\033[94mInfo:\033[0m {message}")


def run_dry_run(config: Config, no_color: bool = False) -> None:
    """Execute a dry run showing configuration without calling API.
    
    Args:
        config: Configuration instance.
        no_color: If True, don't use ANSI colors.
    """
    print_info("Dry run mode - showing configuration:", no_color)
    print()
    print(f"Model: {config.model_name}")
    print(f"Require No-Training: {config.require_no_training}")
    print(f"Use Vertex AI: {config.use_vertexai}")
    if config.use_vertexai:
        print(f"Vertex Project: {config.vertex_project}")
        print(f"Vertex Location: {config.vertex_location}")
    print(f"Schemas Directory: {config.schemas_dir}")
    print(f"Audit Log Path: {config.audit_log_path}")
    print(f"Audit Include Prompt: {bool(getattr(config, 'audit_include_prompt', False))}")
    print(f"Memory Root: {config.memory_root}")
    print(f"Max Retries: {config.max_retries}")
    print(f"Retry Delay: {config.retry_delay}s")
    
    # Check schemas directory
    if config.validate_schemas_dir():
        schema_files = list(config.schemas_dir.glob("*.json"))
        print(f"Schemas Found: {len(schema_files)}")
        for schema_file in schema_files:
            print(f"  - {schema_file.name}")
    else:
        print("Schemas Status: NOT FOUND or empty")


async def run_server(
    config: Config,
    socket_path: Optional[str] = None,
    verbose: bool = False,
) -> int:
    """Run the IPC server for SwiftUI frontend communication.
    
    Args:
        config: Configuration instance.
        socket_path: Optional custom socket path.
        verbose: Whether verbose mode is enabled.
    
    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    from agent_host.ipc.server import IPCServer, ClientConnection
    from agent_host.ipc.protocol import (
        PROTOCOL_VERSION,
        IncomingRequest,
        StatusUpdate,
        ToolCallStatus,
        ToolCallNotification,
        ResultMessage,
        ErrorMessage,
        SystemMessage,
    )
    from agent_host.ipc.hot_reload import init_reload_manager, ReloadEvent
    
    logger = logging.getLogger(__name__)
    if verbose:
        logger.info("IPC server running with verbose mode enabled")
    try:
        audit_logger = AuditLogger(config.audit_log_path)
        audit_logger.log_event(
            EventType.STARTUP,
            {
                "mode": "ipc_server",
                "model": config.model_name,
                "socket_path": socket_path or "default",
            },
        )
    except AuditLogError as e:
        logger.error("Audit logging initialization failed: %s", e)
        return EXIT_CONFIG_ERROR
    
    # Initialize components
    try:
        validator = SchemaValidator(config.schemas_dir)
        tools = validator.get_all_tools_for_gemini()
        logger.info(f"Loaded {len(tools)} tool schemas")
    except SchemaLoadError as e:
        logger.error(f"Schema loading error: {e}")
        return EXIT_CONFIG_ERROR
    
    if not tools:
        logger.error("No tool schemas found in schemas directory")
        return EXIT_CONFIG_ERROR

    try:
        migration_result = run_preflight_migration(config.memory_root)
        if migration_result.already_migrated:
            logger.info(
                "Memory preflight migration already completed (marker=%s)",
                migration_result.marker_path,
            )
        else:
            logger.info(
                "Memory preflight migration completed (upgraded_hmac_rows=%s removed_ghost_sessions=%s backup=%s marker=%s)",
                migration_result.upgraded_hmac_rows,
                migration_result.removed_ghost_sessions,
                migration_result.backup_path,
                migration_result.marker_path,
            )
    except MemoryMigrationError as exc:
        logger.error("Strict memory migration failed: %s", exc)
        return EXIT_CONFIG_ERROR

    # Initialize secure session memory manager
    try:
        memory_manager = MemoryManager(config.memory_root)
        logger.info("Memory manager initialized at %s", config.memory_root)
    except Exception as e:
        logger.error("Failed to initialize memory manager: %s", e)
        return EXIT_CONFIG_ERROR

    try:
        tool_executor = ToolExecutor.from_config(config)
        logger.info(
            "Tool executor initialized (roots=%s, automations_dir=%s)",
            [str(root) for root in config.allowed_roots],
            config.automations_dir,
        )
    except Exception as e:
        logger.error("Failed to initialize tool executor: %s", e)
        return EXIT_CONFIG_ERROR
    
    # Initialize Gemini client
    try:
        gemini_client = GeminiClient(
            api_key=config.gemini_api_key,
            model_name=config.model_name,
            max_retries=config.max_retries,
            retry_delay=config.retry_delay,
            require_no_training=config.require_no_training,
            use_vertexai=config.use_vertexai,
            vertex_project=config.vertex_project,
            vertex_location=config.vertex_location,
        )
        logger.info("Gemini client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        return EXIT_CONFIG_ERROR

    # Wire semantic embedding service (uses Gemini text-embedding-004)
    try:
        embedding_client = getattr(gemini_client, "_client", gemini_client)
        embedding_service = EmbeddingService(embedding_client)
        memory_manager.set_embedding_service(embedding_service)
        logger.info("Semantic embedding service initialized")
    except Exception as e:
        logger.error("Embedding service initialization failed: %s", e)
        return EXIT_CONFIG_ERROR

    ipc_auth_token = os.environ.get("AI_AGENT_IPC_AUTH_TOKEN", "").strip()
    if not ipc_auth_token:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            ipc_auth_token = "test-ipc-auth-token"
            logger.warning(
                "AI_AGENT_IPC_AUTH_TOKEN missing under pytest; using deterministic test token."
            )
        else:
            logger.error(
                "Missing required AI_AGENT_IPC_AUTH_TOKEN. Refusing to start unauthenticated IPC server."
            )
            return EXIT_CONFIG_ERROR

    # Create IPC server
    server_max_clients = max(1, _safe_env_int("AI_AGENT_IPC_MAX_CLIENTS", 128))
    server = IPCServer(
        socket_path=socket_path,
        max_clients=server_max_clients,
        require_auth=True,
        auth_token=ipc_auth_token,
        required_protocol_version=PROTOCOL_VERSION,
    )
    
    # Build base system prompt once at startup (cached for all requests).
    # Model identity is injected per-request via inject_model_identity().
    try:
        base_system_instruction = build_system_prompt(tools)
        logger.info(
            "Base system prompt loaded (%s chars, %s tools injected)",
            len(base_system_instruction),
            len(tools),
        )
    except SystemPromptLoadError as e:
        logger.error("System prompt load error: %s", e)
        return EXIT_CONFIG_ERROR

    # Track active prompt tasks for cancellation and lifecycle management
    active_prompt_tasks: dict[str, asyncio.Task[None]] = {}
    cancelled_prompt_requests: set[str] = set()
    client_prompt_index: dict[str, set[str]] = {}
    pending_tool_confirmations: dict[str, tuple[str, asyncio.Future[bool]]] = {}
    pending_screen_captures: dict[str, tuple[str, asyncio.Future[dict | None]]] = {}
    plan_mode_clarification_states: dict[str, PlanClarificationState] = {}
    plan_mode_sessions_with_plan: dict[str, bool] = {}
    # Runtime-only planner preference learning. Not persisted to memory DB.
    plan_mode_option_learning_by_session: dict[str, dict[str, dict[str, float]]] = {}
    plan_mode_option_learning_global: dict[str, dict[str, float]] = {}
    destructive_tool_names = {"apply_ops", "run_automation"}
    plan_mode_allowed_tools = {
        "planner",
        "plan_ops",
        "search_files",
        "read_text",
        "extract_content",
        "get_metadata",
        "read_screen",
        "take_note",
        "update_note",
        "delete_note",
        "format_note",
        "merge_notes",
        "reorder_notes",
        "generate_image",
        "generate_quiz",
        "summarize_note",
        "browse_web",
    }
    confirmation_timeout_seconds = 60.0
    db_timeout_seconds = _safe_env_float("AI_AGENT_DB_TIMEOUT_SECONDS", 20.0)
    model_timeout_seconds = _safe_env_float("AI_AGENT_MODEL_TIMEOUT_SECONDS", 180.0)
    image_timeout_seconds = max(
        1.0,
        _safe_env_float("AI_AGENT_IMAGE_TIMEOUT_SECONDS", config.image_timeout_seconds),
    )
    image_output_root = config.image_output_root.expanduser().resolve(strict=False)
    image_model_override = config.image_model_override
    deep_think_model_timeout_multiplier = _safe_env_float(
        "AI_AGENT_DEEP_THINK_MODEL_TIMEOUT_MULTIPLIER",
        1.25,
    )
    teacher_model_timeout_multiplier = _safe_env_float(
        "AI_AGENT_TEACHER_MODEL_TIMEOUT_MULTIPLIER",
        1.10,
    )
    continuation_model_timeout_multiplier = _safe_env_float(
        "AI_AGENT_CONTINUATION_MODEL_TIMEOUT_MULTIPLIER",
        1.15,
    )
    model_timeout_max_seconds = _safe_env_float("AI_AGENT_MODEL_TIMEOUT_MAX_SECONDS", 300.0)
    tool_timeout_seconds = _safe_env_float("AI_AGENT_TOOL_TIMEOUT_SECONDS", 120.0)
    prompt_timeout_seconds = _safe_env_float("AI_AGENT_PROMPT_TIMEOUT_SECONDS", 300.0)
    prompt_timeout_max_seconds = _safe_env_float("AI_AGENT_PROMPT_TIMEOUT_MAX_SECONDS", 900.0)
    max_tool_chain_depth = _safe_env_int("AI_AGENT_MAX_TOOL_CHAIN_DEPTH", 100)
    read_screen_ocr_max_chars = max(800, _safe_env_int("AI_AGENT_READ_SCREEN_OCR_MAX_CHARS", 12000))
    read_screen_ocr_max_lines = max(20, _safe_env_int("AI_AGENT_READ_SCREEN_OCR_MAX_LINES", 220))
    db_metrics_interval_seconds = _safe_env_float(
        "AI_AGENT_DEBUG_DB_METRICS_INTERVAL_SECONDS", 15.0
    )
    db_metrics_enabled = os.environ.get("AI_AGENT_DEBUG_DB_METRICS", "0").strip() == "1"
    plan_mode_nlp_ready = False
    plan_mode_nlp_error: str | None = None
    plan_mode_nlp_preload_ms: float | None = None
    plan_mode_nlp_preload_task: asyncio.Task[None] | None = None
    unhealthy_shutdown_requested = asyncio.Event()
    blocking_timeout_grace_seconds = 0.25

    class BlockingCallTimeoutError(TimeoutError):
        """Raised when a blocking operation timeout escalates process health failure."""

    async def _run_blocking_with_timeout(
        *,
        label: str,
        timeout_seconds: float,
        func: Callable[..., Any],
        request_id: str,
        method: str,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(func, *args, **(kwargs or {})),
                timeout=timeout_seconds,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "%s complete",
                label,
                extra={
                    "component": label,
                    "request_id": request_id,
                    "method": method,
                    "duration_ms": round(elapsed_ms, 3),
                    "error_type": None,
                    "error_message": None,
                },
            )
            return result
        except asyncio.TimeoutError as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.error(
                "%s timeout; marking backend unhealthy",
                label,
                extra={
                    "component": label,
                    "request_id": request_id,
                    "method": method,
                    "duration_ms": round(elapsed_ms, 3),
                    "error_type": "TimeoutError",
                    "error_message": f"{label} timed out after {timeout_seconds}s",
                },
            )
            unhealthy_shutdown_requested.set()
            await asyncio.sleep(blocking_timeout_grace_seconds)
            raise BlockingCallTimeoutError(
                f"{label} timed out after {timeout_seconds}s; backend marked unhealthy"
            ) from exc

    async def _resolve_note_id(
        session_id: str,
        raw_id: str,
        mgr: Any,
        timeout: float,
        request_id: str,
        method: str,
        *,
        notes_cache: list[dict[str, object]] | None = None,
    ) -> str | None:
        """Resolve a full or prefix note_id to the full UUID.

        The agent may provide an 8-char prefix from [SESSION_NOTES] context.
        We list notes and match by prefix.  Returns None if no match found.

        Pass *notes_cache* to avoid repeated list_notes calls in batch operations.
        """
        raw_id = raw_id.strip() if isinstance(raw_id, str) else ""
        if not raw_id:
            return None
        if notes_cache is not None:
            notes = notes_cache
        else:
            notes = await _run_blocking_with_timeout(
                label="notes.list_for_resolve",
                timeout_seconds=timeout,
                func=mgr.list_notes,
                args=(session_id,),
                kwargs={"limit": 200},
                request_id=request_id,
                method=method,
            )
        prefix_matches: list[str] = []
        for note in notes:
            nid = note.get("note_id", "")
            if nid == raw_id:
                return nid  # Exact match always wins.
            if nid.startswith(raw_id):
                prefix_matches.append(nid)
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        if len(prefix_matches) > 1:
            logger.warning(
                "Ambiguous note ID prefix '%s' matches %d notes",
                raw_id,
                len(prefix_matches),
            )
        return None

    db_metrics_task: asyncio.Task[None] | None = None
    unhealthy_shutdown_task: asyncio.Task[None] | None = None

    def _track_prompt_task(
        request_id: str,
        client: ClientConnection,
        task: asyncio.Task[None],
    ) -> None:
        """Track an active prompt task and clean up indexes on completion."""
        active_prompt_tasks[request_id] = task
        client_prompt_index.setdefault(client.address, set()).add(request_id)

        def _cleanup(_completed_task: asyncio.Task[None]) -> None:
            active_prompt_tasks.pop(request_id, None)
            cancelled_prompt_requests.discard(request_id)
            pending_confirmation = pending_tool_confirmations.pop(request_id, None)
            if pending_confirmation is not None:
                pending_future = pending_confirmation[1]
                if not pending_future.done():
                    pending_future.set_result(False)
            pending_capture = pending_screen_captures.pop(request_id, None)
            if pending_capture is not None:
                _, capture_future = pending_capture
                if not capture_future.done():
                    capture_future.set_result(None)
            request_ids = client_prompt_index.get(client.address)
            if not request_ids:
                return
            request_ids.discard(request_id)
            if not request_ids:
                client_prompt_index.pop(client.address, None)

        task.add_done_callback(_cleanup)

    def _cancel_requests_for_client(client_address: str) -> int:
        cancelled_count = 0
        for request_id in list(client_prompt_index.get(client_address, set())):
            task = active_prompt_tasks.get(request_id)
            if task and not task.done():
                cancelled_prompt_requests.add(request_id)
                pending_confirmation = pending_tool_confirmations.pop(request_id, None)
                if pending_confirmation is not None:
                    _, pending_future = pending_confirmation
                    if not pending_future.done():
                        pending_future.set_result(False)
                pending_capture = pending_screen_captures.pop(request_id, None)
                if pending_capture is not None:
                    _, capture_future = pending_capture
                    if not capture_future.done():
                        capture_future.set_result(None)
                task.cancel()
                cancelled_count += 1
        return cancelled_count

    def _client_is_connected(client: ClientConnection) -> bool:
        writer = getattr(client, "writer", None)
        if writer is None:
            # Test doubles and alternate transport adapters may omit `writer`.
            return True
        is_closing = getattr(writer, "is_closing", None)
        if not callable(is_closing):
            return True
        try:
            return not bool(is_closing())
        except Exception:
            return False

    def _is_request_in_flight(request_id: str) -> bool:
        current_task = asyncio.current_task()
        tracked_task = active_prompt_tasks.get(request_id)
        if current_task is None or tracked_task is None:
            return False
        if tracked_task is not current_task:
            return False
        if tracked_task.done():
            return False
        if request_id in cancelled_prompt_requests:
            return False
        return True

    async def _send_request_message(
        *,
        client: ClientConnection,
        request_id: str,
        payload: bytes,
        require_in_flight: bool,
    ) -> bool:
        if require_in_flight and not _is_request_in_flight(request_id):
            return False
        if not _client_is_connected(client):
            return False
        try:
            await client.send(payload)
            return True
        except (BrokenPipeError, ConnectionError, OSError):
            return False
        except RuntimeError:
            logger.warning(
                "RuntimeError while sending to client (transport likely closed)",
                extra={"request_id": request_id},
            )
            return False

    async def _send_request_error(
        client: ClientConnection,
        request_id: str,
        code: int,
        message: str,
        *,
        require_in_flight: bool = False,
    ) -> None:
        """Send a structured error and terminal status updates for a request."""
        await _send_request_message(
            client=client,
            request_id=request_id,
            payload=ErrorMessage.create(request_id, code, message).to_bytes(),
            require_in_flight=require_in_flight,
        )
        await _send_request_message(
            client=client,
            request_id=request_id,
            payload=StatusUpdate.error(request_id, message).to_bytes(),
            require_in_flight=require_in_flight,
        )
        await _send_request_message(
            client=client,
            request_id=request_id,
            payload=StatusUpdate.complete(request_id).to_bytes(),
            require_in_flight=require_in_flight,
        )

    def _session_payload(session: object) -> dict[str, object]:
        """Serialize a session record into the canonical IPC payload shape."""
        return {
            "session_id": getattr(session, "session_id"),
            "title": getattr(session, "title"),
            "memory_mode": getattr(getattr(session, "memory_mode"), "value"),
            "created_at": getattr(session, "created_at"),
            "updated_at": getattr(session, "updated_at"),
            "last_activity": getattr(session, "last_activity"),
            "status": getattr(session, "status"),
        }

    async def _broadcast_system_message(message: SystemMessage) -> None:
        """Broadcast a system message to all connected IPC clients."""
        try:
            await server.broadcast(message.to_bytes())
        except Exception as exc:  # pragma: no cover - defensive transport guard
            logger.warning("Failed to broadcast system event: %s", exc)

    async def _broadcast_session_event(*, action: str, session: dict[str, object]) -> None:
        await _broadcast_system_message(
            SystemMessage.session_event(
                str(uuid.uuid4()),
                action=action,
                session=session,
            )
        )

    async def _broadcast_notes_event(
        *,
        action: str,
        session_id: str,
        note: dict[str, object] | None = None,
        note_id: str | None = None,
    ) -> None:
        await _broadcast_system_message(
            SystemMessage.notes_event(
                str(uuid.uuid4()),
                action=action,
                session_id=session_id,
                note=note,
                note_id=note_id,
            )
        )

    async def _broadcast_memory_event(
        *,
        action: str,
        session_id: str,
        memory_id: str | None = None,
    ) -> None:
        await _broadcast_system_message(
            SystemMessage.memory_event(
                str(uuid.uuid4()),
                action=action,
                session_id=session_id,
                memory_id=memory_id,
            )
        )

    async def _broadcast_session_refresh(
        *,
        session_id: str,
        request_id: str,
        method: str,
    ) -> None:
        updated_session = await _run_blocking_with_timeout(
            label="db.get_session",
            timeout_seconds=db_timeout_seconds,
            func=memory_manager.get_session,
            args=(session_id,),
            request_id=request_id,
            method=method,
        )
        if updated_session is not None:
            await _broadcast_session_event(
                action="updated",
                session=_session_payload(updated_session),
            )

    async def _process_prompt(
        request: IncomingRequest,
        client: ClientConnection,
        prompt: str,
        model: Optional[str],
        session_id: str,
        memory_mode: MemoryMode,
        execution_mode: ExecutionMode,
        input_paths: list[str],
        verbosity_level: int,
        presentation_style: str,
        stream_animation_style: str,
        deep_think: bool,
        correlation_id: str,
    ) -> None:
        """Process a prompt request without blocking the IPC event loop."""
        request_id = request.id
        context_tokens = set_request_context(
            correlation_id=correlation_id,
            request_id=request_id,
            method=request.method,
        )

        try:
            plan_mode_auto_execute = False

            async def _send_mode_status(detail: str) -> None:
                trimmed = detail.strip() or "Working on your request..."
                if plan_mode_auto_execute:
                    payload = StatusUpdate.executing_plan(
                        request_id, trimmed
                    ).to_bytes()
                elif execution_mode == ExecutionMode.PLAN:
                    payload = StatusUpdate.planning(
                        request_id, trimmed
                    ).to_bytes()
                else:
                    payload = StatusUpdate.thinking(
                        request_id, trimmed
                    ).to_bytes()
                await _send_request_message(
                    client=client,
                    request_id=request_id,
                    payload=payload,
                    require_in_flight=True,
                )

            # Log the model selection for debugging
            if model:
                logger.info(f"Model Selection Debug: Using frontend-specified model '{model}'")
                logger.info(f"Received prompt with model '{model}': {prompt[:100]}...")
            else:
                logger.info("Model Selection Debug: No model specified, using client default")
                logger.info(f"Received prompt (default model): {prompt[:100]}...")
            logger.info(
                (
                    "Prompt context: session_id=%s memory_mode=%s execution_mode=%s verbosity=%s deep_think=%s "
                    "presentation_style=%s stream_animation=%s input_paths=%s"
                ),
                session_id,
                memory_mode.value,
                execution_mode.value,
                verbosity_level,
                deep_think,
                presentation_style,
                stream_animation_style,
                len(input_paths),
            )

            if execution_mode == ExecutionMode.PLAN:
                await _send_mode_status("Loading session context...")
            elif execution_mode == ExecutionMode.TEACHER:
                await _send_mode_status("Loading study context...")
            else:
                await _send_mode_status("Loading context...")

            prepared = await _run_blocking_with_timeout(
                label="db.prepare_prompt_context",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.prepare_prompt_context,
                args=(),
                kwargs={
                    "session_id": session_id,
                    "prompt": prompt,
                    "memory_mode": memory_mode,
                },
                request_id=request_id,
                method=request.method,
            )
            prompt_for_model = prepared.augmented_prompt
            resolved_user_prompt = prompt
            clarification_context_block = ""
            unified_planning_context_block = ""
            plan_mode_discovery_budget = _parse_plan_mode_discovery_budget()
            plan_mode_clarification_required = _parse_plan_mode_clarification_required()
            latest_plan_clarification_state: PlanClarificationState | None = None
            plan_mode_clarification_resolved_this_turn = False
            session_learning_for_ranking: dict[str, dict[str, float]] | None = None
            if memory_mode != MemoryMode.OFF:
                session_learning_for_ranking = plan_mode_option_learning_by_session.setdefault(
                    session_id,
                    {},
                )
            global_learning_for_ranking = plan_mode_option_learning_global if memory_mode != MemoryMode.OFF else None
            teacher_mode_note_captured = False

            async def _ensure_teacher_note_capture(response_text: str) -> bool:
                nonlocal teacher_mode_note_captured
                if execution_mode != ExecutionMode.TEACHER or teacher_mode_note_captured:
                    return True
                await _send_mode_status("Capturing key highlights in study notes...")
                try:
                    note_body = _build_teacher_note_body(
                        prompt=resolved_user_prompt,
                        response_text=response_text,
                    )
                    note_tags = _normalize_note_tags(
                        [],
                        extra_tags=TEACHER_DEFAULT_NOTE_TAGS,
                    )
                    tagged_content = f"<!-- note-type:{TEACHER_DEFAULT_NOTE_TYPE} -->\n{note_body}"
                    if note_tags:
                        tagged_content = (
                            f"<!-- tags:{','.join(note_tags)} -->\n{tagged_content}"
                        )
                    created_note = await _run_blocking_with_timeout(
                        label="notes.teacher_autocapture",
                        timeout_seconds=db_timeout_seconds,
                        func=memory_manager.create_note,
                        args=(session_id,),
                        kwargs={"content": tagged_content, "source": "agent"},
                        request_id=request_id,
                        method=request.method,
                    )
                    teacher_mode_note_captured = True
                    await _send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=ToolCallNotification.success(
                            request_id,
                            "take_note",
                            {
                                "title": "Study Session",
                                "note_type": TEACHER_DEFAULT_NOTE_TYPE,
                                "tags": note_tags,
                            },
                            (
                                f"Teacher note saved (id={created_note['note_id'][:8]}) "
                                "with key highlights."
                            ),
                        ).to_bytes(),
                        require_in_flight=True,
                    )
                    return True
                except Exception as exc:
                    message = f"Teacher mode requires note capture and failed: {exc}"
                    await _send_request_error(
                        client=client,
                        request_id=request_id,
                        code=ErrorMessage.INTERNAL_ERROR,
                        message=message,
                        require_in_flight=True,
                    )
                    if _is_request_in_flight(request_id):
                        await _run_blocking_with_timeout(
                            label="db.record_interaction",
                            timeout_seconds=db_timeout_seconds,
                            func=memory_manager.record_interaction,
                            args=(),
                            kwargs={
                                "session_id": session_id,
                                "memory_mode": memory_mode,
                                "user_prompt": prompt,
                                "assistant_response": message,
                                "model_name": model or config.model_name,
                            },
                            request_id=request_id,
                            method=request.method,
                        )
                    return False

            if execution_mode != ExecutionMode.PLAN:
                plan_mode_clarification_states.pop(session_id, None)
                plan_mode_sessions_with_plan.pop(session_id, None)

            plan_mode_is_followup = (
                execution_mode == ExecutionMode.PLAN
                and _is_plan_mode_followup(prompt, session_id in plan_mode_sessions_with_plan)
            )
            plan_mode_auto_execute = (
                plan_mode_is_followup
                and _is_plan_mode_execution_approval(prompt)
            )
            if plan_mode_auto_execute:
                execution_mode = ExecutionMode.DIRECT
                logger.info(
                    "Plan Mode auto-switch to DIRECT for request %s (user approved execution)",
                    request_id,
                )
                await _send_request_message(
                    client=client,
                    request_id=request_id,
                    payload=StatusUpdate.executing_plan(
                        request_id,
                        "Executing your approved plan...",
                    ).to_bytes(),
                    require_in_flight=True,
                )

            # Compute once using the effective root prompt (not a raw clarification reply).
            _effective_root_prompt = prompt
            if execution_mode == ExecutionMode.PLAN:
                clarification_state = plan_mode_clarification_states.get(session_id)
                if (
                    clarification_state is not None
                    and not _looks_like_plan_clarification_reply(prompt, clarification_state)
                ):
                    # User changed direction -> reset stale clarification flow.
                    plan_mode_clarification_states.pop(session_id, None)
                    clarification_state = None
                elif clarification_state is not None:
                    _effective_root_prompt = clarification_state.root_prompt

            plan_mode_requires_unified_planning = (
                execution_mode == ExecutionMode.PLAN
                and _prompt_has_actionable_file_operation_intent(_effective_root_prompt)
            )

            if execution_mode == ExecutionMode.PLAN and not plan_mode_is_followup and _should_run_plan_mode_clarification(
                    prompt=prompt,
                    clarification_required=plan_mode_clarification_required,
                    requires_unified_planning=plan_mode_requires_unified_planning,
                ):
                    if (
                        clarification_state is not None
                        and _looks_like_plan_clarification_reply(prompt, clarification_state)
                    ):
                        accepted = _update_clarification_state_from_reply(
                            state=clarification_state,
                            prompt=prompt,
                            session_learning=session_learning_for_ranking,
                            global_learning=global_learning_for_ranking,
                        )
                        if not accepted:
                            score = _compute_plan_mode_clarification_score(
                                prompt=clarification_state.root_prompt,
                                missing_dimensions=_plan_mode_missing_clarification_dimensions(
                                    clarification_state.root_prompt
                                ),
                                asked_rounds=clarification_state.asked_rounds,
                            )
                            clarification_text = _build_plan_mode_clarification_turn_response(
                                state=clarification_state,
                                session_learning=session_learning_for_ranking,
                                global_learning=global_learning_for_ranking,
                                score=score,
                            )
                            await _send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=StatusUpdate.planning(
                                    request_id,
                                    "I couldn't confidently parse that answer. Quick retry:",
                                ).to_bytes(),
                                require_in_flight=True,
                            )
                            if _is_request_in_flight(request_id) and _client_is_connected(client):
                                streamer = server.create_streaming_handler(client, request_id)
                                await streamer.stream_words(clarification_text)
                            await _send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=ResultMessage.create(request_id, clarification_text).to_bytes(),
                                require_in_flight=True,
                            )
                            if _is_request_in_flight(request_id):
                                await _run_blocking_with_timeout(
                                    label="db.record_interaction",
                                    timeout_seconds=db_timeout_seconds,
                                    func=memory_manager.record_interaction,
                                    args=(),
                                    kwargs={
                                        "session_id": session_id,
                                        "memory_mode": memory_mode,
                                        "user_prompt": prompt,
                                        "assistant_response": clarification_text,
                                        "model_name": model or config.model_name,
                                    },
                                    request_id=request_id,
                                    method=request.method,
                                )
                            await _send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=StatusUpdate.complete(request_id).to_bytes(),
                                require_in_flight=True,
                                )
                            return

                        for answered_dimension, selected_option in clarification_state.option_answers.items():
                            if not selected_option:
                                continue
                            if session_learning_for_ranking is not None:
                                _update_plan_option_learning(
                                    session_learning_for_ranking,
                                    dimension=answered_dimension,
                                    option_key=selected_option,
                                    weight=1.0,
                                )
                            if global_learning_for_ranking is not None:
                                _update_plan_option_learning(
                                    global_learning_for_ranking,
                                    dimension=answered_dimension,
                                    option_key=selected_option,
                                    weight=0.45,
                                )

                        resolved_user_prompt = clarification_state.root_prompt
                        clarification_context_block = _build_plan_clarification_context_block(
                            clarification_state,
                            session_learning=session_learning_for_ranking,
                            global_learning=global_learning_for_ranking,
                        )
                        latest_plan_clarification_state = clarification_state
                        plan_mode_clarification_resolved_this_turn = True
                        plan_mode_clarification_states.pop(session_id, None)
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=StatusUpdate.planning(
                                request_id,
                                "Great, drafting a tailored plan from your answers...",
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                    elif clarification_state is None and _prompt_requires_plan_mode_clarification(prompt):
                        plan_mode_sessions_with_plan.pop(session_id, None)
                        new_state = _initialize_plan_clarification_state(prompt)
                        if len(plan_mode_clarification_states) > 100:
                            oldest_key = next(iter(plan_mode_clarification_states))
                            plan_mode_clarification_states.pop(oldest_key, None)
                        plan_mode_clarification_states[session_id] = new_state
                        score = _compute_plan_mode_clarification_score(
                            prompt=prompt,
                            missing_dimensions=_plan_mode_missing_clarification_dimensions(prompt),
                            asked_rounds=0,
                        )
                        clarification_text = _build_plan_mode_clarification_turn_response(
                            state=new_state,
                            session_learning=session_learning_for_ranking,
                            global_learning=global_learning_for_ranking,
                            score=score,
                        )
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=StatusUpdate.planning(
                                request_id,
                                "Need a quick clarification before drafting.",
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                        if _is_request_in_flight(request_id) and _client_is_connected(client):
                            streamer = server.create_streaming_handler(client, request_id)
                            await streamer.stream_words(clarification_text)
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ResultMessage.create(request_id, clarification_text).to_bytes(),
                            require_in_flight=True,
                        )
                        if _is_request_in_flight(request_id):
                            await _run_blocking_with_timeout(
                                label="db.record_interaction",
                                timeout_seconds=db_timeout_seconds,
                                func=memory_manager.record_interaction,
                                args=(),
                                kwargs={
                                    "session_id": session_id,
                                    "memory_mode": memory_mode,
                                    "user_prompt": prompt,
                                    "assistant_response": clarification_text,
                                    "model_name": model or config.model_name,
                                },
                                request_id=request_id,
                                method=request.method,
                            )
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=StatusUpdate.complete(request_id).to_bytes(),
                            require_in_flight=True,
                        )
                        return

            if resolved_user_prompt != prompt:
                prepared = await _run_blocking_with_timeout(
                    label="db.prepare_prompt_context",
                    timeout_seconds=db_timeout_seconds,
                    func=memory_manager.prepare_prompt_context,
                    args=(),
                    kwargs={
                        "session_id": session_id,
                        "prompt": resolved_user_prompt,
                        "memory_mode": memory_mode,
                    },
                    request_id=request_id,
                    method=request.method,
                )
                prompt_for_model = prepared.augmented_prompt

            if clarification_context_block:
                prompt_for_model = f"{prompt_for_model}\n\n{clarification_context_block}"

            if input_paths:
                lines = [
                    "[USER_SELECTED_PATHS]",
                    "The user explicitly dropped/selected these paths for this request:",
                ]
                lines.extend(f"- {path}" for path in input_paths)
                lines.append(
                    "Treat this list as trusted user intent context and prioritize these paths when planning."
                )
                prompt_for_model = f"{prompt_for_model}\n\n" + "\n".join(lines)

            if execution_mode == ExecutionMode.PLAN and not plan_mode_is_followup:
                await _send_mode_status("Preparing unified planner context...")
                planner_bootstrap_goal = _sanitize_planner_bootstrap_goal(resolved_user_prompt)
                planner_bootstrap_args = {"mode": "analyze", "goal": planner_bootstrap_goal}
                planner_bootstrap_execution: dict[str, object]
                try:
                    planner_bootstrap_execution = await _run_blocking_with_timeout(
                        label="tool.execute.planner_bootstrap",
                        timeout_seconds=tool_timeout_seconds,
                        func=tool_executor.execute,
                        args=("planner", planner_bootstrap_args),
                        request_id=request_id,
                        method=request.method,
                    )
                except ToolExecutionError as exc:
                    bootstrap_error = (
                        "Plan mode requires unified-planning initialization before drafting. "
                        f"Planner bootstrap failed: {exc}"
                    )
                    await _send_request_error(
                        client=client,
                        request_id=request_id,
                        code=ErrorMessage.INVALID_REQUEST,
                        message=bootstrap_error,
                        require_in_flight=True,
                    )
                    if _is_request_in_flight(request_id):
                        await _run_blocking_with_timeout(
                            label="db.record_interaction",
                            timeout_seconds=db_timeout_seconds,
                            func=memory_manager.record_interaction,
                            args=(),
                            kwargs={
                                "session_id": session_id,
                                "memory_mode": memory_mode,
                                "user_prompt": prompt,
                                "assistant_response": bootstrap_error,
                                "model_name": model or config.model_name,
                            },
                            request_id=request_id,
                            method=request.method,
                        )
                    return

                if not planner_bootstrap_execution.get("ok", False):
                    bootstrap_error = (
                        "Plan mode requires unified-planning initialization before drafting. "
                        "Planner bootstrap returned non-success status."
                    )
                    await _send_request_error(
                        client=client,
                        request_id=request_id,
                        code=ErrorMessage.INVALID_REQUEST,
                        message=bootstrap_error,
                        require_in_flight=True,
                    )
                    if _is_request_in_flight(request_id):
                        await _run_blocking_with_timeout(
                            label="db.record_interaction",
                            timeout_seconds=db_timeout_seconds,
                            func=memory_manager.record_interaction,
                            args=(),
                            kwargs={
                                "session_id": session_id,
                                "memory_mode": memory_mode,
                                "user_prompt": prompt,
                                "assistant_response": bootstrap_error,
                                "model_name": model or config.model_name,
                            },
                            request_id=request_id,
                            method=request.method,
                        )
                    return

                unified_planning_context_block = _build_unified_planning_bootstrap_context(
                    planner_bootstrap_execution
                )
                if unified_planning_context_block:
                    prompt_for_model = f"{prompt_for_model}\n\n{unified_planning_context_block}"
                await _send_mode_status("Planner initialized, preparing model...")

            # Inject model identity into the cached base prompt for this request.
            effective_model = model or config.model_name
            system_instruction = inject_model_identity(
                base_system_instruction,
                effective_model,
                verbosity=verbosity_level,
                presentation_style=presentation_style,
                deep_think=deep_think,
            )
            if execution_mode == ExecutionMode.PLAN:
                if plan_mode_is_followup:
                    plan_mode_header = (
                        "## PLAN MODE — Conversation Follow-up\n\n"
                        "Current mode: **PLAN** (responding to an existing plan).\n\n"
                        "The user is responding to a plan you previously produced in this session.\n"
                        "Check [RECENT_SESSION_CONTEXT] for the full conversation history.\n"
                        "Respond conversationally to their follow-up:\n"
                        "- If they confirm/approve, summarize the next concrete steps.\n"
                        "- If they ask to revise, adjust the plan.\n"
                        "- If they ask a question, answer it in context.\n"
                        "- If they reference notes (e.g. 'elaborate on the notes', 'make them detailed'),\n"
                        "  use the [SESSION_NOTES] section in the prompt — the notes are already there.\n"
                        "  Do NOT call `read_screen` or `search_files` to find note content.\n"
                        "  Use `update_note` or `take_note` to modify or add notes directly.\n"
                        "Do NOT restart the planning process. Do NOT ask clarification questions.\n"
                        "Only call `plan_ops` if they explicitly request a revised or new plan.\n"
                    )
                else:
                    plan_mode_header = (
                        "## EXECUTION MODE\n\n"
                        "Current mode: **PLAN**.\n"
                        "This mode is planning-only. Unified-planning context is preloaded.\n\n"
                        "**MANDATORY**: You MUST produce a structured plan by calling `plan_ops`.\n"
                        "Workflow: (1) optionally gather context with discovery tools, then "
                        "(2) call `plan_ops` to create the phased execution plan.\n"
                        "NEVER return only discovery results or empty text without a plan.\n"
                        "Your text response must be a human-readable plan summary — not raw tool output.\n\n"
                        "Blend advanced planning rigor with concise, user-friendly communication.\n"
                        "Make assumptions explicit and easy to revise.\n"
                        "Do not execute destructive tools in this mode (`apply_ops`, `run_automation`).\n"
                    )
                    if plan_mode_requires_unified_planning:
                        plan_mode_header += (
                            "This prompt indicates actionable file-operations.\n"
                            "Use unified planning via `planner`/`plan_ops` early.\n"
                            "Limit pre-planning discovery calls (`search_files`, `get_metadata`, "
                            "`read_text`, `extract_content`) to "
                            f"{plan_mode_discovery_budget} before producing a plan.\n"
                        )
                system_instruction = f"{plan_mode_header}\n\n{system_instruction}"
            elif execution_mode == ExecutionMode.TEACHER:
                teacher_mode_header = (
                    "## EXECUTION MODE\n\n"
                    "Current mode: **TEACHER**.\n"
                    "You are the user's tutor and autonomous study-note assistant.\n"
                    "Teach clearly, then ensure the turn produces structured notes with key highlights.\n"
                    "If you call note tools, prefer concise study formatting and include key takeaways.\n"
                    "Do not skip note capture in this mode.\n"
                )
                system_instruction = f"{teacher_mode_header}\n\n{system_instruction}"
            elif plan_mode_auto_execute:
                auto_exec_header = (
                    "## EXECUTION MODE — Plan Approved\n\n"
                    "Current mode: **DIRECT** (auto-switched from plan after user approval).\n\n"
                    "The user approved a plan you produced earlier in this session.\n"
                    "Check [RECENT_SESSION_CONTEXT] for the plan and conversation history.\n"
                    "Execute the plan now using all available tools.\n"
                    "Start with the first concrete step. Be safe and confirm destructive actions.\n"
                    "Report progress as you go.\n"
                )
                system_instruction = f"{auto_exec_header}\n\n{system_instruction}"
            else:
                direct_mode_header = (
                    "## EXECUTION MODE\n\n"
                    "Current mode: **DIRECT**.\n"
                    "Execute tools when needed to complete the request safely.\n"
                    "Using `plan_ops` is optional in this mode.\n"
                )
                system_instruction = f"{direct_mode_header}\n\n{system_instruction}"
            active_tools = tools
            if execution_mode == ExecutionMode.PLAN:
                active_tools = [
                    tool
                    for tool in tools
                    if isinstance(tool, dict) and tool.get("name") in plan_mode_allowed_tools
                ]

            def _decorate_mode_result(text: str) -> str:
                if execution_mode != ExecutionMode.PLAN:
                    return text
                stripped = text.lstrip()
                if stripped.startswith("PLAN MODE (Planning Only)") or stripped.startswith(
                    "PLAN MODE (Quick Clarification)"
                ):
                    return _normalize_plan_mode_banner(text)
                decorated = (
                    "PLAN MODE (Planning Only)\n"
                    "No destructive tools were executed in this response.\n"
                    "If assumptions look wrong, ask to revise and I will replan.\n\n"
                    f"{text}"
                )
                return _normalize_plan_mode_banner(decorated)

            parser_instance = ToolCallParser()
            conversation_history: list[types.Content] = [
                types.Content(role="user", parts=[types.Part.from_text(text=prompt_for_model)])
            ]
            chain_depth = 0
            final_assistant_response: str | None = None
            last_non_terminal_result: tuple[str, dict[str, object]] | None = None
            # The planner bootstrap at line ~2364 already called `planner`
            # for Plan Mode requests, so mark it as used to avoid false
            # discovery budget enforcement in the tool chain loop.
            plan_mode_planner_used = execution_mode == ExecutionMode.PLAN
            # Tracks whether the model has called `plan_ops` (or `planner`)
            # to actually produce a plan.  Separate from planner_used because
            # the bootstrap pre-satisfies budget but doesn't produce the plan.
            plan_mode_plan_produced = False
            plan_mode_discovery_calls = 0
            plan_mode_alignment_retry_used = False
            plan_mode_post_clarification_retry_used = False

            def _model_timeout_for_turn(*, continuation: bool) -> float:
                return _resolve_model_timeout_seconds(
                    base_timeout_seconds=model_timeout_seconds,
                    deep_think=deep_think,
                    execution_mode=execution_mode,
                    is_continuation=continuation,
                    deep_think_multiplier=deep_think_model_timeout_multiplier,
                    teacher_multiplier=teacher_model_timeout_multiplier,
                    continuation_multiplier=continuation_model_timeout_multiplier,
                    max_timeout_seconds=model_timeout_max_seconds,
                )

            while chain_depth < max_tool_chain_depth:
                chain_depth += 1

                # Determine once per iteration whether to show tool call
                # cards in the frontend.  In Plan Mode the cards are hidden
                # and the status bar shows phase descriptions instead.
                show_tool_call_card = execution_mode != ExecutionMode.PLAN

                if not _is_request_in_flight(request_id):
                    logger.info("Skipping late prompt response for inactive request: %s", request_id)
                    return
                if not _client_is_connected(client):
                    logger.info("Client disconnected mid-chain for request: %s", request_id)
                    return

                logger.info(
                    "Tool chain iteration %s/%s for request %s",
                    chain_depth,
                    max_tool_chain_depth,
                    request_id,
                )
                if chain_depth == 1:
                    if execution_mode == ExecutionMode.TEACHER:
                        await _send_mode_status("Understanding your question...")
                    else:
                        await _send_mode_status("Analyzing your request...")
                elif chain_depth == 2:
                    if execution_mode == ExecutionMode.TEACHER:
                        await _send_mode_status("Preparing explanation and key highlights...")
                    else:
                        await _send_mode_status("Evaluating initial findings...")
                else:
                    if execution_mode == ExecutionMode.TEACHER:
                        await _send_mode_status("Refining explanation and study notes...")
                    else:
                        await _send_mode_status("Refining plan with new data...")

                if chain_depth == 1:
                    response = await _run_blocking_with_timeout(
                        label="model.generate_content",
                        timeout_seconds=_model_timeout_for_turn(continuation=False),
                        func=gemini_client.send_prompt_with_tools,
                        args=(),
                        kwargs={
                            "prompt": prompt_for_model,
                            "tools": active_tools,
                            "system_instruction": system_instruction,
                            "model": model,
                            "deep_think": deep_think,
                        },
                        request_id=request_id,
                        method=request.method,
                    )
                else:
                    continuation_callable = getattr(gemini_client, "send_continuation", None)
                    if not callable(continuation_callable):
                        raise RuntimeError(
                            "Gemini client does not implement required continuation API"
                        )
                    response = await _run_blocking_with_timeout(
                        label="model.generate_content.continuation",
                        timeout_seconds=_model_timeout_for_turn(continuation=True),
                        func=continuation_callable,
                        args=(),
                        kwargs={
                            "contents": conversation_history,
                            "tools": active_tools,
                            "system_instruction": system_instruction,
                            "model": model,
                            "deep_think": deep_think,
                        },
                        request_id=request_id,
                        method=request.method,
                    )

                if not _is_request_in_flight(request_id):
                    logger.info("Skipping late model response for inactive request: %s", request_id)
                    return

                logger.info(
                    "[MODEL_VERIFICATION] Response received. Requested model: '%s'",
                    model or "default",
                )

                tool_call = parser_instance.parse_response(response)

                if tool_call is None:
                    if response.get("text"):
                        raw_text = str(response["text"])
                        text = (
                            sanitize_user_visible_response(raw_text)
                            if looks_like_json_payload(raw_text)
                            else raw_text
                        )
                        if execution_mode == ExecutionMode.PLAN:
                            asks_structured_clarification = _plan_mode_text_requests_structured_clarification(
                                text
                            )
                            continuation_callable = getattr(gemini_client, "send_continuation", None)
                            can_retry_with_continuation = callable(continuation_callable)

                            if asks_structured_clarification and plan_mode_clarification_resolved_this_turn:
                                if (
                                    not plan_mode_post_clarification_retry_used
                                    and can_retry_with_continuation
                                ):
                                    plan_mode_post_clarification_retry_used = True
                                    conversation_history.append(
                                        types.Content(
                                            role="model",
                                            parts=[types.Part.from_text(text=raw_text)],
                                        )
                                    )
                                    conversation_history.append(
                                        types.Content(
                                            role="user",
                                            parts=[
                                                types.Part.from_text(
                                                    text=_build_plan_mode_post_clarification_instruction(
                                                        root_prompt=resolved_user_prompt,
                                                        clarification_context_block=clarification_context_block,
                                                    )
                                                )
                                            ],
                                        )
                                    )
                                    await _send_mode_status(
                                        "Using your clarification answers to finalize the plan..."
                                    )
                                    continue

                            if asks_structured_clarification:
                                # Reset retry flag so a new clarification round can use it.
                                plan_mode_post_clarification_retry_used = False
                                existing_followup_state = (
                                    plan_mode_clarification_states.get(session_id)
                                    or latest_plan_clarification_state
                                )
                                should_continue = (
                                    existing_followup_state is None
                                    or _should_continue_plan_clarification(
                                        state=existing_followup_state,
                                        max_rounds=_parse_plan_mode_clarification_max_rounds(),
                                        confidence_target=_parse_plan_mode_clarification_confidence_target(),
                                    )
                                )
                                if not should_continue:
                                    plan_mode_clarification_states.pop(session_id, None)
                                else:
                                    followup_state = _prepare_plan_mode_followup_clarification_state(
                                        root_prompt=resolved_user_prompt,
                                        state=existing_followup_state,
                                    )
                                    if followup_state.question_dimensions:
                                        if len(plan_mode_clarification_states) > 100:
                                            oldest_key = next(iter(plan_mode_clarification_states))
                                            plan_mode_clarification_states.pop(oldest_key, None)
                                        plan_mode_clarification_states[session_id] = followup_state
                                        followup_score = _compute_plan_mode_clarification_score(
                                            prompt=followup_state.root_prompt,
                                            missing_dimensions=_plan_mode_missing_clarification_dimensions(
                                                followup_state.root_prompt
                                            ),
                                            asked_rounds=followup_state.asked_rounds,
                                        )
                                        text = _build_plan_mode_clarification_turn_response(
                                            state=followup_state,
                                            session_learning=session_learning_for_ranking,
                                            global_learning=global_learning_for_ranking,
                                            score=followup_score,
                                        )
                                    else:
                                        plan_mode_clarification_states.pop(session_id, None)
                            else:
                                alignment_score = _compute_plan_mode_alignment_score(
                                    root_prompt=resolved_user_prompt,
                                    response_text=text,
                                    clarification_context_block=clarification_context_block,
                                )
                                alignment_threshold = _dynamic_plan_mode_alignment_threshold(
                                    resolved_user_prompt
                                )
                                if (
                                    alignment_score < alignment_threshold
                                    and not plan_mode_alignment_retry_used
                                    and can_retry_with_continuation
                                ):
                                    plan_mode_alignment_retry_used = True
                                    conversation_history.append(
                                        types.Content(
                                            role="model",
                                            parts=[types.Part.from_text(text=raw_text)],
                                        )
                                    )
                                    conversation_history.append(
                                        types.Content(
                                            role="user",
                                            parts=[
                                                types.Part.from_text(
                                                    text=_build_plan_mode_alignment_repair_instruction(
                                                        root_prompt=resolved_user_prompt,
                                                        clarification_context_block=clarification_context_block,
                                                    )
                                                )
                                            ],
                                        )
                                    )
                                    await _send_mode_status(
                                        "Refining plan alignment to your request..."
                                    )
                                    continue
                        text = _decorate_mode_result(text)
                        if not await _ensure_teacher_note_capture(text):
                            return
                        await _send_mode_status("Drafting response...")
                        if _is_request_in_flight(request_id) and _client_is_connected(client):
                            streamer = server.create_streaming_handler(client, request_id)
                            await streamer.stream_words(text)
                        result_tool_calls: list[dict[str, object]] | None = None
                        if last_non_terminal_result is not None:
                            _, prior_tool_call_payload = last_non_terminal_result
                            if prior_tool_call_payload:
                                result_tool_calls = [prior_tool_call_payload]
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ResultMessage.create(
                                request_id,
                                text,
                                result_tool_calls,
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                        final_assistant_response = text
                    else:
                        # Plan Mode planner nudge: if the model returned no actionable
                        # output without having produced a plan, re-prompt it to call
                        # plan_ops.  Uses plan_mode_plan_produced (not planner_used)
                        # because the bootstrap pre-satisfies planner_used for budget
                        # enforcement but doesn't produce the actual plan.
                        continuation_callable = getattr(gemini_client, "send_continuation", None)
                        can_retry_with_continuation = callable(continuation_callable)
                        if (
                            execution_mode == ExecutionMode.PLAN
                            and not plan_mode_plan_produced
                            and can_retry_with_continuation
                            and chain_depth < max_tool_chain_depth
                        ):
                            # Insert a minimal model turn so the Gemini API sees
                            # proper user/model alternation in the history.
                            conversation_history.append(
                                types.Content(
                                    role="model",
                                    parts=[
                                        types.Part.from_text(
                                            text="I have the planning context. Let me build the plan now."
                                        )
                                    ],
                                )
                            )
                            nudge_text = (
                                "You MUST now call the `plan_ops` tool to produce a structured, "
                                "phased execution plan. The planner context is already loaded. "
                                "Do not return text — call `plan_ops` with your plan now."
                            ) if last_non_terminal_result is None else (
                                "You gathered discovery information but returned no plan. "
                                "You MUST now call the `plan_ops` tool to produce a structured, "
                                "phased execution plan based on the discovery results above. "
                                "Do not call more discovery tools. Produce the plan now."
                            )
                            conversation_history.append(
                                types.Content(
                                    role="user",
                                    parts=[types.Part.from_text(text=nudge_text)],
                                )
                            )
                            await _send_mode_status("Assembling plan from discovery results...")
                            continue
                        if execution_mode == ExecutionMode.PLAN:
                            fallback_text = (
                                "I analyzed your request but couldn't produce a structured plan. "
                                "This can happen when the planning engine needs more specific guidance. "
                                "Try rephrasing with: what you want organized, a timeline, and any constraints."
                            )
                        elif execution_mode == ExecutionMode.TEACHER:
                            failure_text = (
                                "Teacher mode could not produce a valid teaching response in this turn."
                            )
                            await _send_request_error(
                                client=client,
                                request_id=request_id,
                                code=ErrorMessage.INTERNAL_ERROR,
                                message=failure_text,
                                require_in_flight=True,
                            )
                            if _is_request_in_flight(request_id):
                                await _run_blocking_with_timeout(
                                    label="db.record_interaction",
                                    timeout_seconds=db_timeout_seconds,
                                    func=memory_manager.record_interaction,
                                    args=(),
                                    kwargs={
                                        "session_id": session_id,
                                        "memory_mode": memory_mode,
                                        "user_prompt": prompt,
                                        "assistant_response": failure_text,
                                        "model_name": model or config.model_name,
                                    },
                                    request_id=request_id,
                                    method=request.method,
                                )
                            return
                        else:
                            fallback_text = (
                                "I wasn't able to generate a response for that request. This might happen if "
                                "the question is outside my capabilities (like weather forecasts or web "
                                "searches). Feel free to ask me about file management or other tasks I can "
                                "help with on your Mac!"
                            )
                        fallback_text = _decorate_mode_result(fallback_text)
                        if not await _ensure_teacher_note_capture(fallback_text):
                            return
                        await _send_mode_status("Drafting response...")
                        if _is_request_in_flight(request_id) and _client_is_connected(client):
                            streamer = server.create_streaming_handler(client, request_id)
                            await streamer.stream_words(fallback_text)
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ResultMessage.create(request_id, fallback_text).to_bytes(),
                            require_in_flight=True,
                        )
                        final_assistant_response = fallback_text
                    break

                if execution_mode == ExecutionMode.PLAN and tool_call.name not in plan_mode_allowed_tools:
                    allowed_tool_list = ", ".join(sorted(plan_mode_allowed_tools))
                    rejection = (
                        "Plan mode is planning-only. This tool is disabled in plan mode: "
                        f"`{tool_call.name}`. Allowed tools: {allowed_tool_list}. "
                        "Switch to Direct mode to execute operations."
                    )
                    if show_tool_call_card:
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.failed(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                rejection,
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                    await _send_request_error(
                        client=client,
                        request_id=request_id,
                        code=ErrorMessage.INVALID_REQUEST,
                        message=rejection,
                        require_in_flight=True,
                    )
                    if _is_request_in_flight(request_id):
                        await _run_blocking_with_timeout(
                            label="db.record_interaction",
                            timeout_seconds=db_timeout_seconds,
                            func=memory_manager.record_interaction,
                            args=(),
                            kwargs={
                                "session_id": session_id,
                                "memory_mode": memory_mode,
                                "user_prompt": prompt,
                                "assistant_response": rejection,
                                "model_name": model or config.model_name,
                            },
                            request_id=request_id,
                            method=request.method,
                        )
                    return

                if execution_mode == ExecutionMode.PLAN and tool_call.name in _PLAN_MODE_PLANNER_TOOLS:
                    plan_mode_planner_used = True
                    # Only mark plan as produced for plan_ops or planner
                    # in create/replan mode (analyze mode is advisory only).
                    if tool_call.name == "plan_ops" or (
                        tool_call.name == "planner"
                        and tool_call.arguments.get("mode") in ("create", "replan")
                    ):
                        plan_mode_plan_produced = True
                        plan_mode_sessions_with_plan[session_id] = True
                    if len(plan_mode_sessions_with_plan) > 100:
                        oldest = next(iter(plan_mode_sessions_with_plan))
                        plan_mode_sessions_with_plan.pop(oldest, None)
                elif (
                    execution_mode == ExecutionMode.PLAN
                    and plan_mode_requires_unified_planning
                    and not plan_mode_planner_used
                    and tool_call.name in _PLAN_MODE_DISCOVERY_TOOLS
                ):
                    plan_mode_discovery_calls += 1
                    if plan_mode_discovery_calls > plan_mode_discovery_budget:
                        rejection = (
                            "Plan mode requires unified planning for actionable file operations. "
                            "Call `planner` or `plan_ops` now before additional discovery tools. "
                            f"Discovery budget before planning: {plan_mode_discovery_budget}."
                        )
                        if show_tool_call_card:
                            await _send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=ToolCallNotification.failed(
                                    request_id,
                                    tool_call.name,
                                    tool_call.arguments,
                                    rejection,
                                ).to_bytes(),
                                require_in_flight=True,
                            )
                        await _send_request_error(
                            client=client,
                            request_id=request_id,
                            code=ErrorMessage.INVALID_REQUEST,
                            message=rejection,
                            require_in_flight=True,
                        )
                        if _is_request_in_flight(request_id):
                            await _run_blocking_with_timeout(
                                label="db.record_interaction",
                                timeout_seconds=db_timeout_seconds,
                                func=memory_manager.record_interaction,
                                args=(),
                                kwargs={
                                    "session_id": session_id,
                                    "memory_mode": memory_mode,
                                    "user_prompt": prompt,
                                    "assistant_response": rejection,
                                    "model_name": model or config.model_name,
                                },
                                request_id=request_id,
                                method=request.method,
                            )
                        return

                if show_tool_call_card:
                    await _send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=StatusUpdate.calling_tool(request_id, tool_call.name).to_bytes(),
                        require_in_flight=True,
                    )
                else:
                    # Plan Mode: tool cards are hidden, so send a user-friendly
                    # phase description so the status bar stays dynamic.
                    _tool_phase_labels = {
                        "search_files": "Scanning your files...",
                        "read_text": "Reading file contents...",
                        "extract_content": "Extracting document content...",
                        "get_metadata": "Inspecting file metadata...",
                        "planner": "Initializing the planner...",
                        "plan_ops": "Building the execution plan...",
                        "apply_ops": "Executing the plan...",
                        "read_screen": "Reading screen contents...",
                        "take_note": "Saving a note...",
                        "update_note": "Updating a note...",
                        "delete_note": "Removing a note...",
                        "format_note": "Formatting a note...",
                        "merge_notes": "Merging notes...",
                        "reorder_notes": "Reordering notes...",
                        "generate_image": "Generating an image...",
                        "generate_quiz": "Creating a quiz...",
                        "summarize_note": "Summarizing a note...",
                        "browse_web": "Browsing web page...",
                    }
                    _phase = _tool_phase_labels.get(
                        tool_call.name,
                        f"Running {tool_call.name}...",
                    )
                    await _send_mode_status(_phase)

                try:
                    validator.validate_tool_call(tool_call.name, tool_call.arguments)
                except (SchemaNotFoundError, ValidationFailedError) as e:
                    validation_error_text = f"Tool call validation failed: {e}"
                    logger.warning(
                        "Schema validation error for %s (request %s): %s",
                        tool_call.name,
                        request_id,
                        e,
                    )
                    if show_tool_call_card:
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.failed(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                str(e),
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                    # Feed the validation error back to the model as a
                    # function response so it can self-correct, rather than
                    # terminating the request outright.
                    validation_model_content = types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name=tool_call.name,
                                args=tool_call.arguments,
                            )
                        ],
                    )
                    conversation_history.append(validation_model_content)
                    conversation_history.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_function_response(
                                    name=tool_call.name,
                                    response={
                                        "ok": False,
                                        "output": {"error": validation_error_text},
                                    },
                                )
                            ],
                        )
                    )
                    last_non_terminal_result = (
                        f"I couldn't complete `{tool_call.name}`.\n\n"
                        f"- Error: {validation_error_text}\n"
                        "- Suggested fix: review the input arguments and retry.",
                        {},
                    )
                    continue

                raw_response = response.get("raw_response")
                model_content: types.Content | None = None
                if raw_response is not None and hasattr(raw_response, "candidates"):
                    candidates = getattr(raw_response, "candidates", None)
                    if candidates:
                        candidate_content = getattr(candidates[0], "content", None)
                        if isinstance(candidate_content, types.Content):
                            model_content = candidate_content
                if model_content is None:
                    model_content = types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name=tool_call.name,
                                args=tool_call.arguments,
                            )
                        ],
                    )

                if tool_call.name in destructive_tool_names:
                    confirmation_future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
                    pending_tool_confirmations[request_id] = (client.address, confirmation_future)
                    await _send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=StatusUpdate.awaiting_approval(
                            request_id,
                            f"Awaiting approval for {tool_call.name}",
                        ).to_bytes(),
                        require_in_flight=True,
                    )
                    if show_tool_call_card:
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.create(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                status=ToolCallStatus.PENDING,
                                result="Awaiting confirmation for destructive operation",
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                    try:
                        approved = await asyncio.wait_for(
                            confirmation_future,
                            timeout=confirmation_timeout_seconds,
                        )
                    except asyncio.TimeoutError:
                        timeout_text = "Tool execution confirmation timed out"
                        if show_tool_call_card:
                            await _send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=ToolCallNotification.failed(
                                    request_id,
                                    tool_call.name,
                                    tool_call.arguments,
                                    "Confirmation timed out",
                                ).to_bytes(),
                                require_in_flight=True,
                            )
                        await _send_request_error(
                            client=client,
                            request_id=request_id,
                            code=ErrorMessage.INVALID_REQUEST,
                            message=timeout_text,
                            require_in_flight=True,
                        )
                        if _is_request_in_flight(request_id):
                            await _run_blocking_with_timeout(
                                label="db.record_interaction",
                                timeout_seconds=db_timeout_seconds,
                                func=memory_manager.record_interaction,
                                args=(),
                                kwargs={
                                    "session_id": session_id,
                                    "memory_mode": memory_mode,
                                    "user_prompt": prompt,
                                    "assistant_response": timeout_text,
                                    "model_name": model or config.model_name,
                                },
                                request_id=request_id,
                                method=request.method,
                            )
                        return
                    finally:
                        pending_tool_confirmations.pop(request_id, None)

                    if not approved:
                        denied_text = "Tool execution denied by user"
                        if show_tool_call_card:
                            await _send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=ToolCallNotification.failed(
                                    request_id,
                                    tool_call.name,
                                    tool_call.arguments,
                                    denied_text,
                                ).to_bytes(),
                                require_in_flight=True,
                            )
                        await _send_request_error(
                            client=client,
                            request_id=request_id,
                            code=ErrorMessage.INVALID_REQUEST,
                            message=denied_text,
                            require_in_flight=True,
                        )
                        if _is_request_in_flight(request_id):
                            await _run_blocking_with_timeout(
                                label="db.record_interaction",
                                timeout_seconds=db_timeout_seconds,
                                func=memory_manager.record_interaction,
                                args=(),
                                kwargs={
                                    "session_id": session_id,
                                    "memory_mode": memory_mode,
                                    "user_prompt": prompt,
                                    "assistant_response": denied_text,
                                    "model_name": model or config.model_name,
                                },
                                request_id=request_id,
                                method=request.method,
                            )
                        return

                # ── read_screen: delegate to frontend via IPC ──
                if tool_call.name == "read_screen":
                    async def _screen_send_status(rid: str) -> None:
                        await _send_request_message(
                            client=client,
                            request_id=rid,
                            payload=StatusUpdate.capturing_screen(rid).to_bytes(),
                            require_in_flight=True,
                        )

                    _screen_ctx = ScreenToolContext(
                        request_id=request_id,
                        client_address=client.address,
                        pending_screen_captures=pending_screen_captures,
                        send_status=_screen_send_status,
                        resolved_user_prompt=resolved_user_prompt,
                        read_screen_ocr_max_chars=read_screen_ocr_max_chars,
                        read_screen_ocr_max_lines=read_screen_ocr_max_lines,
                    )
                    execution, screen_image_bytes = await dispatch_screen_tool(
                        _screen_ctx, tool_call.arguments,
                    )

                    # Build function response + optional image part
                    conversation_history.append(model_content)
                    _fn_response = types.Part.from_function_response(
                        name=tool_call.name,
                        response={
                            "ok": bool(execution.get("ok")),
                            "output": execution.get("output"),
                        },
                    )
                    _parts: list[types.Part] = [_fn_response]
                    if screen_image_bytes:
                        _parts.append(
                            types.Part.from_bytes(
                                data=screen_image_bytes,
                                mime_type="image/jpeg",
                            )
                        )
                    conversation_history.append(
                        types.Content(role="user", parts=_parts)
                    )

                    # Send tool card to frontend
                    if show_tool_call_card:
                        _card_status = (
                            ToolCallStatus.SUCCESS
                            if execution.get("ok")
                            else ToolCallStatus.FAILED
                        )
                        _result_preview = str(
                            execution.get("output", "")
                        )[:200]
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.create(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                status=_card_status,
                                result=_result_preview,
                            ).to_bytes(),
                            require_in_flight=True,
                        )

                    last_non_terminal_result = (
                        str(execution.get("output", "")),
                        {
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                            "status": "success" if execution.get("ok") else "failed",
                            "result": str(execution.get("output", ""))[:200],
                        },
                    )
                    continue

                # ── note tools (dispatched via registry) ──
                if tool_call.name in NOTE_TOOL_NAMES:
                    note_execution: dict[str, object]
                    try:
                        if tool_call.name == "generate_image":
                            _note_ctx: NoteToolContext = ImageToolContext(
                                session_id=session_id,
                                memory_manager=memory_manager,
                                db_timeout_seconds=db_timeout_seconds,
                                request_id=request_id,
                                method=request.method,
                                execution_mode=execution_mode,
                                resolved_user_prompt=resolved_user_prompt,
                                run_blocking=_run_blocking_with_timeout,
                                resolve_note_id=_resolve_note_id,
                                gemini_client=gemini_client,
                                image_output_root=image_output_root,
                                image_timeout_seconds=image_timeout_seconds,
                                image_model_override=image_model_override,
                                config_allowed_roots=list(config.allowed_roots),
                            )
                        else:
                            _note_ctx = NoteToolContext(
                                session_id=session_id,
                                memory_manager=memory_manager,
                                db_timeout_seconds=db_timeout_seconds,
                                request_id=request_id,
                                method=request.method,
                                execution_mode=execution_mode,
                                resolved_user_prompt=resolved_user_prompt,
                                run_blocking=_run_blocking_with_timeout,
                                resolve_note_id=_resolve_note_id,
                            )
                        note_execution = await dispatch_note_tool(
                            tool_call.name, _note_ctx, tool_call.arguments,
                        )
                    except TimeoutError as te:
                        logger.warning("Note tool %s timed out: %s", tool_call.name, te)
                        note_execution = {
                            "ok": False,
                            "output": (
                                f"Note operation timed out ({tool_call.name}): {te}. "
                                "The database may be busy — try again."
                            ),
                        }
                    except Exception as exc:
                        logger.warning("Note tool %s failed: %s", tool_call.name, exc)
                        note_execution = {
                            "ok": False,
                            "output": f"Note operation failed: {exc}",
                        }
                    if (
                        execution_mode == ExecutionMode.TEACHER
                        and bool(note_execution.get("ok"))
                        and tool_call.name in TEACHER_NOTE_COMPLETION_TOOLS
                    ):
                        teacher_mode_note_captured = True

                    # Feed result back into conversation
                    conversation_history.append(model_content)
                    conversation_history.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_function_response(
                                    name=tool_call.name,
                                    response={
                                        "ok": bool(note_execution.get("ok")),
                                        "output": note_execution.get("output"),
                                    },
                                )
                            ],
                        )
                    )

                    # Send tool card to frontend
                    if show_tool_call_card:
                        _note_card_status = (
                            ToolCallStatus.SUCCESS
                            if note_execution.get("ok")
                            else ToolCallStatus.FAILED
                        )
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.create(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                status=_note_card_status,
                                result=str(note_execution.get("output", ""))[:200],
                            ).to_bytes(),
                            require_in_flight=True,
                        )

                    last_non_terminal_result = (
                        str(note_execution.get("output", "")),
                        {
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                            "status": "success" if note_execution.get("ok") else "failed",
                            "result": str(note_execution.get("output", ""))[:200],
                        },
                    )
                    continue

                if tool_call.name == "apply_ops":
                    await _send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=StatusUpdate.executing_plan(
                            request_id,
                            f"Executing plan: {tool_call.arguments.get('plan_id', '')}",
                        ).to_bytes(),
                        require_in_flight=True,
                    )

                if show_tool_call_card:
                    await _send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=ToolCallNotification.executing(
                            request_id,
                            tool_call.name,
                            tool_call.arguments,
                        ).to_bytes(),
                        require_in_flight=True,
                    )

                # execution: dict[str, object]  <-- reused variable
                execution_content: str
                execution_summary: str
                plan_mode_result_override: str | None = None
                try:
                    execution = await _run_blocking_with_timeout(
                        label="tool.execute",
                        timeout_seconds=tool_timeout_seconds,
                        func=tool_executor.execute,
                        args=(tool_call.name, tool_call.arguments),
                        request_id=request_id,
                        method=request.method,
                    )
                    if not _is_request_in_flight(request_id):
                        logger.info(
                            "Skipping late tool execution response for inactive request: %s",
                            request_id,
                        )
                        return
                except ToolExecutionError as e:
                    error_text = str(e)
                    execution = {
                        "tool": tool_call.name,
                        "ok": False,
                        "output": {"error": error_text},
                        "error": error_text,
                    }
                    execution_content = (
                        f"I couldn't complete `{tool_call.name}`.\n\n"
                        f"- Error: {error_text}\n"
                        "- Suggested fix: review the input arguments and retry."
                    )
                    execution_summary = error_text or "execution failed"
                    if show_tool_call_card:
                        await _send_request_message(
                            client=client,
                            request_id=request_id,
                            payload=ToolCallNotification.failed(
                                request_id,
                                tool_call.name,
                                tool_call.arguments,
                                execution_summary,
                            ).to_bytes(),
                            require_in_flight=True,
                        )
                else:
                    execution_content, execution_summary = _format_tool_execution_output(
                        tool_call.name,
                        execution,
                    )
                    if (
                        execution_mode == ExecutionMode.PLAN
                        and tool_call.name == "plan_ops"
                        and execution.get("ok")
                    ):
                        planned_id = ""
                        output_payload = execution.get("output", {})
                        if isinstance(output_payload, dict):
                            planned_id_raw = output_payload.get("plan_id")
                            if isinstance(planned_id_raw, str) and planned_id_raw.strip():
                                planned_id = planned_id_raw.strip()
                                await _send_request_message(
                                    client=client,
                                    request_id=request_id,
                                    payload=StatusUpdate.plan_ready(
                                        request_id,
                                        f"Plan ready: {planned_id}",
                                    ).to_bytes(),
                                    require_in_flight=True,
                                )
                        if not planned_id:
                            planned_id = "unknown-plan-id"
                        plan_mode_result_override = (
                            f"{execution_content}\n\n"
                            "Plan mode is ON: no filesystem changes were executed.\n"
                            "To execute this plan, switch to Direct mode and ask to apply "
                            f"`plan_id={planned_id}`."
                        )
                    if execution.get("ok"):
                        if show_tool_call_card:
                            await _send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=ToolCallNotification.success(
                                    request_id,
                                    tool_call.name,
                                    tool_call.arguments,
                                    execution_summary,
                                ).to_bytes(),
                                require_in_flight=True,
                            )
                    else:
                        failure_reason = execution_summary or "execution failed"
                        if show_tool_call_card:
                            await _send_request_message(
                                client=client,
                                request_id=request_id,
                                payload=ToolCallNotification.failed(
                                    request_id,
                                    tool_call.name,
                                    tool_call.arguments,
                                    failure_reason,
                                ).to_bytes(),
                                require_in_flight=True,
                            )

                tool_call_payload: dict[str, object] = (
                    {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    }
                    if show_tool_call_card
                    else {}
                )
                if plan_mode_result_override is not None:
                    if not await _ensure_teacher_note_capture(plan_mode_result_override):
                        return
                    await _send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=ResultMessage.create(
                            request_id,
                            plan_mode_result_override,
                            [tool_call_payload] if tool_call_payload else None,
                        ).to_bytes(),
                        require_in_flight=True,
                    )
                    final_assistant_response = plan_mode_result_override
                    break
                if tool_call.name in destructive_tool_names:
                    if not await _ensure_teacher_note_capture(execution_content):
                        return
                    await _send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=ResultMessage.create(
                            request_id,
                            execution_content,
                            [tool_call_payload] if tool_call_payload else None,
                        ).to_bytes(),
                        require_in_flight=True,
                    )
                    final_assistant_response = execution_content
                    break

                last_non_terminal_result = (execution_content, tool_call_payload)
                conversation_history.append(model_content)
                function_response = types.Part.from_function_response(
                    name=tool_call.name,
                    response={
                        "ok": bool(execution.get("ok")),
                        "output": execution.get("output"),
                    },
                )
                conversation_history.append(
                    types.Content(role="user", parts=[function_response])
                )

            if final_assistant_response is None:
                if last_non_terminal_result is not None:
                    final_assistant_response, tool_call_payload = last_non_terminal_result
                    if chain_depth >= max_tool_chain_depth:
                        final_assistant_response = (
                            f"{final_assistant_response}\n\n"
                            f"Stopped after reaching tool-chain depth limit "
                            f"({max_tool_chain_depth}) before a final model answer."
                        )
                    final_assistant_response = _decorate_mode_result(final_assistant_response)
                    if not await _ensure_teacher_note_capture(final_assistant_response):
                        return
                    await _send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=ResultMessage.create(
                            request_id,
                            final_assistant_response,
                            [tool_call_payload] if tool_call_payload else None,
                        ).to_bytes(),
                        require_in_flight=True,
                    )
                elif chain_depth >= max_tool_chain_depth:
                    final_assistant_response = (
                        f"I reached the maximum tool-chain depth ({max_tool_chain_depth}) "
                        "before producing a final response."
                    )
                    final_assistant_response = _decorate_mode_result(final_assistant_response)
                    if not await _ensure_teacher_note_capture(final_assistant_response):
                        return
                    await _send_request_message(
                        client=client,
                        request_id=request_id,
                        payload=ResultMessage.create(request_id, final_assistant_response).to_bytes(),
                        require_in_flight=True,
                    )

            if final_assistant_response is not None and _is_request_in_flight(request_id):
                await _run_blocking_with_timeout(
                    label="db.record_interaction",
                    timeout_seconds=db_timeout_seconds,
                    func=memory_manager.record_interaction,
                    args=(),
                    kwargs={
                        "session_id": session_id,
                        "memory_mode": memory_mode,
                        "user_prompt": prompt,
                        "assistant_response": final_assistant_response,
                        "model_name": model or config.model_name,
                    },
                    request_id=request_id,
                    method=request.method,
                )
                updated_session = await _run_blocking_with_timeout(
                    label="db.get_session",
                    timeout_seconds=db_timeout_seconds,
                    func=memory_manager.get_session,
                    args=(session_id,),
                    request_id=request_id,
                    method=request.method,
                )
                if updated_session is not None:
                    await _broadcast_session_event(
                        action="activity",
                        session=_session_payload(updated_session),
                    )

            # Send complete status
            await _send_request_message(
                client=client,
                request_id=request_id,
                payload=StatusUpdate.complete(request_id).to_bytes(),
                require_in_flight=True,
            )

        except asyncio.CancelledError:
            logger.info(f"Prompt request cancelled: {request_id}")
            await _send_request_error(
                client=client,
                request_id=request_id,
                code=-32800,
                message="Request cancelled by user",
            )
            raise
        except GeminiRateLimitError as e:
            await _send_request_error(
                client=client,
                request_id=request_id,
                code=-32000,
                message=f"Rate limit: {_format_exception_message(e, fallback='Rate limit exceeded')}",
                require_in_flight=True,
            )
        except GeminiAPIError as e:
            await _send_request_error(
                client=client,
                request_id=request_id,
                code=-32001,
                message=f"API error: {_format_exception_message(e, fallback='Gemini API request failed')}",
                require_in_flight=True,
            )
        except MalformedResponseError as e:
            await _send_request_error(
                client=client,
                request_id=request_id,
                code=-32002,
                message=f"Parse error: {_format_exception_message(e, fallback='Malformed Gemini response')}",
                require_in_flight=True,
            )
        except Exception as e:
            logger.exception(f"Error handling prompt: {e}")
            message = _format_exception_message(e)
            await _send_request_error(
                client=client,
                request_id=request_id,
                code=ErrorMessage.INTERNAL_ERROR,
                message=message,
                require_in_flight=True,
            )
        finally:
            reset_request_context(context_tokens)

    def _extract_correlation_id(request: IncomingRequest) -> str:
        raw = request.params.get("correlation_id")
        if isinstance(raw, str):
            trimmed = raw.strip()
            if trimmed:
                return trimmed[:128]
        return generate_correlation_id()

    async def handle_prompt(request: IncomingRequest, client: ClientConnection) -> None:
        """Handle prompt requests from the SwiftUI frontend."""
        correlation_id = _extract_correlation_id(request)
        request_id = request.id
        context_tokens = set_request_context(
            correlation_id=correlation_id,
            request_id=request_id,
            method=request.method,
        )
        try:
            prompt_raw = request.params.get("prompt")
            model = request.params.get("model")
            raw_session_id = request.params.get("session_id")
            session_id_provided = "session_id" in request.params
            memory_mode_provided = "memory_mode" in request.params
            execution_mode_provided = "execution_mode" in request.params
            verbosity_provided = "verbosity" in request.params
            presentation_style_provided = "presentation_style" in request.params
            stream_animation_style_provided = "stream_animation" in request.params
            deep_think_provided = "deep_think" in request.params
            input_paths_raw = request.params.get("input_paths")

            if not isinstance(prompt_raw, str) or not prompt_raw.strip():
                error = ErrorMessage.invalid_request(
                    request_id,
                    "Missing 'prompt' parameter (must be a non-empty string)",
                )
                await client.send(error.to_bytes())
                return
            prompt = prompt_raw

            if session_id_provided:
                if not isinstance(raw_session_id, str) or not raw_session_id.strip():
                    await client.send(
                        ErrorMessage.invalid_request(request_id, "Invalid session_id").to_bytes()
                    )
                    return
                session_id = _normalize_session_id(raw_session_id, fallback="")
                if not session_id:
                    await client.send(
                        ErrorMessage.invalid_request(request_id, "Invalid session_id").to_bytes()
                    )
                    return
                existing_session = await _run_blocking_with_timeout(
                    label="db.get_session",
                    timeout_seconds=db_timeout_seconds,
                    func=memory_manager.get_session,
                    args=(session_id,),
                    request_id=request_id,
                    method=request.method,
                )
                if existing_session is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            f"Unknown session_id: {session_id}",
                        ).to_bytes()
                    )
                    return
            else:
                logger.warning(
                    "Prompt request missing session_id from client %s (request_id=%s)",
                    client.address,
                    request_id,
                )
                await client.send(
                    ErrorMessage.invalid_request(
                        request_id,
                        "Missing required 'session_id' parameter. "
                        "Create a session via 'session.create' first.",
                    ).to_bytes()
                )
                return

            if memory_mode_provided:
                parsed_mode = _parse_memory_mode_strict(request.params.get("memory_mode"))
                if parsed_mode is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            f"Invalid memory_mode: {request.params.get('memory_mode')}",
                        ).to_bytes()
                    )
                    return
                memory_mode = parsed_mode
            elif existing_session is not None:
                # Respect persisted session mode unless request explicitly overrides it.
                memory_mode = existing_session.memory_mode
            else:
                memory_mode = MemoryMode.ON

            if verbosity_provided:
                verbosity_level = _parse_verbosity_level_strict(request.params.get("verbosity"))
                if verbosity_level is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                f"Invalid verbosity: {request.params.get('verbosity')} "
                                "(expected: low, medium, high, extra_high)"
                            ),
                        ).to_bytes()
                    )
                    return
            else:
                verbosity_level = _VERBOSITY_LEVEL_BY_NAME["medium"]

            if execution_mode_provided:
                execution_mode = _parse_execution_mode_strict(request.params.get("execution_mode"))
                if execution_mode is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                f"Invalid execution_mode: {request.params.get('execution_mode')} "
                                "(expected: direct, plan, teacher)"
                            ),
                        ).to_bytes()
                    )
                    return
            else:
                execution_mode = ExecutionMode.DIRECT

            if execution_mode == ExecutionMode.PLAN and not plan_mode_nlp_ready:
                if plan_mode_nlp_preload_task is not None and not plan_mode_nlp_preload_task.done():
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(plan_mode_nlp_preload_task),
                            timeout=8.0,
                        )
                    except asyncio.TimeoutError:
                        await client.send(
                            ErrorMessage.invalid_request(
                                request_id,
                                "Plan mode is unavailable: NLP classifier is still initializing.",
                            ).to_bytes()
                        )
                        return
                if not plan_mode_nlp_ready:
                    reason = plan_mode_nlp_error or "spaCy classifier failed to initialize"
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                "Plan mode is unavailable because NLP classifier startup failed: "
                                f"{reason}"
                            ),
                        ).to_bytes()
                    )
                    return

            if presentation_style_provided:
                presentation_style = _parse_presentation_style_strict(
                    request.params.get("presentation_style")
                )
                if presentation_style is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                f"Invalid presentation_style: {request.params.get('presentation_style')} "
                                "(expected: readable_pro, glass_editorial, dense_technical)"
                            ),
                        ).to_bytes()
                    )
                    return
            else:
                presentation_style = "readable_pro"

            if stream_animation_style_provided:
                stream_animation_style = _parse_stream_animation_style_strict(
                    request.params.get("stream_animation")
                )
                if stream_animation_style is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                f"Invalid stream_animation: {request.params.get('stream_animation')} "
                                "(expected: wave_reveal, typewriter_luxe, minimal_motion)"
                            ),
                        ).to_bytes()
                    )
                    return
            else:
                stream_animation_style = "wave_reveal"

            if deep_think_provided:
                deep_think = _parse_deep_think_flag_strict(request.params.get("deep_think"))
                if deep_think is None:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            "Invalid deep_think: expected boolean true or false",
                        ).to_bytes()
                    )
                    return
            else:
                deep_think = False

            if deep_think:
                requested_model = model if isinstance(model, str) and model.strip() else config.model_name
                if not _model_supports_native_deep_think(requested_model):
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            (
                                "Deep-think mode requires a reasoning-enabled model with native "
                                f"thinking controls (got '{requested_model}'). "
                                "Use Gemini 3 or Gemini 2.5."
                            ),
                        ).to_bytes()
                    )
                    return

            input_paths: list[str] = []
            if input_paths_raw is not None:
                if not isinstance(input_paths_raw, list):
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            "Invalid input_paths: expected array of path strings",
                        ).to_bytes()
                    )
                    return
                if len(input_paths_raw) > 100:
                    await client.send(
                        ErrorMessage.invalid_request(
                            request_id,
                            "Too many input_paths: maximum is 100",
                        ).to_bytes()
                    )
                    return
                seen_paths: set[str] = set()
                for idx, raw_path in enumerate(input_paths_raw):
                    if not isinstance(raw_path, str) or not raw_path.strip():
                        await client.send(
                            ErrorMessage.invalid_request(
                                request_id,
                                f"Invalid input_paths[{idx}] (must be non-empty string)",
                            ).to_bytes()
                        )
                        return
                    try:
                        normalized = tool_executor._normalize_user_path(
                            raw_path,
                            must_exist=True,
                        )
                    except ToolExecutionError as exc:
                        await client.send(
                            ErrorMessage.invalid_request(
                                request_id,
                                f"Invalid input_paths[{idx}]: {exc}",
                            ).to_bytes()
                        )
                        return
                    normalized_str = str(normalized)
                    if normalized_str in seen_paths:
                        continue
                    seen_paths.add(normalized_str)
                    input_paths.append(normalized_str)

            effective_model_timeout = _resolve_model_timeout_seconds(
                base_timeout_seconds=model_timeout_seconds,
                deep_think=deep_think,
                execution_mode=execution_mode,
                is_continuation=True,
                deep_think_multiplier=deep_think_model_timeout_multiplier,
                teacher_multiplier=teacher_model_timeout_multiplier,
                continuation_multiplier=continuation_model_timeout_multiplier,
                max_timeout_seconds=model_timeout_max_seconds,
            )
            effective_prompt_timeout_seconds = _resolve_prompt_timeout_seconds(
                base_timeout_seconds=prompt_timeout_seconds,
                model_timeout_seconds=effective_model_timeout,
                tool_timeout_seconds=tool_timeout_seconds,
                deep_think=deep_think,
                execution_mode=execution_mode,
                max_timeout_seconds=prompt_timeout_max_seconds,
            )

            # Reject duplicate in-flight request ids to avoid ambiguous cancellation/routing.
            if request_id in active_prompt_tasks and not active_prompt_tasks[request_id].done():
                await client.send(
                    ErrorMessage.invalid_request(
                        request_id, "A request with this id is already in progress"
                    ).to_bytes()
                )
                return

            task_start_gate = asyncio.Event()

            async def _run_prompt_with_timeout() -> None:
                # Prevent a startup race where the task runs before it is indexed
                # as in-flight for request-scoped status/result routing.
                await task_start_gate.wait()
                try:
                    await asyncio.wait_for(
                        _process_prompt(
                            request,
                            client,
                            prompt,
                            model,
                            session_id,
                            memory_mode,
                            execution_mode,
                            input_paths,
                            verbosity_level,
                            presentation_style,
                            stream_animation_style,
                            deep_think,
                            correlation_id,
                        ),
                        timeout=effective_prompt_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    await _send_request_error(
                        client=client,
                        request_id=request_id,
                        code=ErrorMessage.INTERNAL_ERROR,
                        message=f"Prompt timed out after {effective_prompt_timeout_seconds}s",
                    )

            task = asyncio.create_task(_run_prompt_with_timeout())
            _track_prompt_task(request_id, client, task)
            task_start_gate.set()
        finally:
            reset_request_context(context_tokens)
    
    async def handle_cancel(request: IncomingRequest, client: ClientConnection) -> None:
        """Handle cancel requests from the SwiftUI frontend."""
        target_request_id = request.params.get("request_id")
        cancelled_request_ids: list[str] = []

        def _cancel_request(request_id: str) -> None:
            task = active_prompt_tasks.get(request_id)
            if task and not task.done():
                cancelled_prompt_requests.add(request_id)
                pending_confirmation = pending_tool_confirmations.pop(request_id, None)
                if pending_confirmation is not None:
                    _, pending_future = pending_confirmation
                    if not pending_future.done():
                        pending_future.set_result(False)
                pending_capture = pending_screen_captures.pop(request_id, None)
                if pending_capture is not None:
                    _, capture_future = pending_capture
                    if not capture_future.done():
                        capture_future.set_result(None)
                task.cancel()
                cancelled_request_ids.append(request_id)

        if isinstance(target_request_id, str) and target_request_id:
            owned_requests = client_prompt_index.get(client.address, set())
            if target_request_id not in owned_requests:
                await client.send(
                    ErrorMessage.invalid_request(
                        request.id,
                        "Request is not active for this client",
                    ).to_bytes()
                )
                await client.send(StatusUpdate.complete(request.id).to_bytes())
                return
            _cancel_request(target_request_id)
        else:
            for request_id in list(client_prompt_index.get(client.address, set())):
                _cancel_request(request_id)

        if not cancelled_request_ids:
            await client.send(
                ErrorMessage.invalid_request(request.id, "No active request to cancel").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        result = ResultMessage.create(
            request.id,
            f"Cancellation requested for {len(cancelled_request_ids)} active request(s).",
        )
        await client.send(result.to_bytes())
        await client.send(StatusUpdate.complete(request.id).to_bytes())

    async def handle_tool_confirm(request: IncomingRequest, client: ClientConnection) -> None:
        """Handle explicit confirmation/denial for pending destructive tool execution."""
        target_request_id = request.params.get("request_id")
        approved_value = request.params.get("approved")
        if not isinstance(target_request_id, str) or not target_request_id:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing request_id").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return
        if not isinstance(approved_value, bool):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing approved boolean").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        pending = pending_tool_confirmations.get(target_request_id)
        if pending is None:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    f"No pending confirmation for request: {target_request_id}",
                ).to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        owner_client_id, pending_future = pending
        if owner_client_id != client.address:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    "Confirmation must be sent by the same client that initiated the request",
                ).to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        if not pending_future.done():
            pending_future.set_result(approved_value)

        acknowledgement = ResultMessage.create(
            request.id,
            (
                f"Confirmation {'approved' if approved_value else 'denied'} "
                f"for request {target_request_id}."
            ),
        )
        await client.send(acknowledgement.to_bytes())
        await client.send(StatusUpdate.complete(request.id).to_bytes())
    
    async def handle_screen_capture(request: IncomingRequest, client: ClientConnection) -> None:
        """Handle screen capture response from the frontend."""
        target_request_id = request.params.get("request_id")
        if not isinstance(target_request_id, str) or not target_request_id:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing request_id").to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        pending = pending_screen_captures.get(target_request_id)
        if pending is None:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    f"No pending screen capture for request: {target_request_id}",
                ).to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        owner_client_id, capture_future = pending
        if owner_client_id != client.address:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    "Capture response must come from the requesting client",
                ).to_bytes()
            )
            await client.send(StatusUpdate.complete(request.id).to_bytes())
            return

        if not capture_future.done():
            capture_future.set_result({
                "image_data": request.params.get("image_data") or "",
                "ocr_text": request.params.get("ocr_text") or "",
                "width": request.params.get("width") or 0,
                "height": request.params.get("height") or 0,
                "error": request.params.get("error") or "",
            })

        acknowledgement = ResultMessage.create(
            request.id, "Screen capture received."
        )
        await client.send(acknowledgement.to_bytes())
        await client.send(StatusUpdate.complete(request.id).to_bytes())

    async def handle_ping(request: IncomingRequest, client: ClientConnection) -> None:
        """Handles ping requests for health check."""
        result = ResultMessage.create(request.id, "pong")
        await client.send(result.to_bytes())

    async def handle_session_create(request: IncomingRequest, client: ClientConnection) -> None:
        """Create a secure session memory container."""
        title_raw = request.params.get("title")
        mode = MemoryMode.ON
        if "memory_mode" in request.params:
            parsed_mode = _parse_memory_mode_strict(request.params.get("memory_mode"))
            if parsed_mode is None:
                await client.send(
                    ErrorMessage.invalid_request(
                        request.id,
                        f"Invalid memory_mode: {request.params.get('memory_mode')}",
                    ).to_bytes()
                )
                return
            mode = parsed_mode
        title = title_raw if isinstance(title_raw, str) else None
        session = await _run_blocking_with_timeout(
            label="db.create_session",
            timeout_seconds=db_timeout_seconds,
            func=memory_manager.create_session,
            args=(),
            kwargs={"title": title, "memory_mode": mode},
            request_id=request.id,
            method=request.method,
        )
        payload = _session_payload(session)
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())
        await _broadcast_session_event(action="created", session=payload)

    async def handle_session_list(request: IncomingRequest, client: ClientConnection) -> None:
        """List known sessions."""
        limit_raw = request.params.get("limit", 50)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 50
        sessions = await _run_blocking_with_timeout(
            label="db.list_sessions",
            timeout_seconds=db_timeout_seconds,
            func=memory_manager.list_sessions,
            args=(),
            kwargs={"limit": max(1, min(limit, 200))},
            request_id=request.id,
            method=request.method,
        )
        payload = [_session_payload(session) for session in sessions]
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())

    async def handle_session_history(request: IncomingRequest, client: ClientConnection) -> None:
        """List persisted chat messages for a session."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        if not session_id:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id").to_bytes()
            )
            return

        limit_raw = request.params.get("limit", 500)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 500

        session_exists = await _run_blocking_with_timeout(
            label="db.get_session",
            timeout_seconds=db_timeout_seconds,
            func=memory_manager.get_session,
            args=(session_id,),
            request_id=request.id,
            method=request.method,
        )
        if session_exists is None:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    f"Unknown session_id: {session_id}",
                ).to_bytes()
            )
            return

        if "memory_mode" in request.params:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    "session.history no longer accepts memory_mode",
                ).to_bytes()
            )
            return

        try:
            payload = await _run_blocking_with_timeout(
                label="db.list_session_messages",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.list_session_messages,
                args=(),
                kwargs={
                    "session_id": session_id,
                    "limit": max(1, min(limit, 2000)),
                },
                request_id=request.id,
                method=request.method,
            )
        except ValueError as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    _format_exception_message(exc, fallback="Unknown session"),
                ).to_bytes()
            )
            return
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())

    async def handle_session_set_mode(request: IncomingRequest, client: ClientConnection) -> None:
        """Update a session's memory mode."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        mode_raw = request.params.get("memory_mode")
        if not session_id or not isinstance(mode_raw, str):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or memory_mode").to_bytes()
            )
            return

        normalized_mode = mode_raw.strip().lower()
        mode = _parse_memory_mode(mode_raw, default=MemoryMode.ON)
        if normalized_mode != mode.value:
            await client.send(
                ErrorMessage.invalid_request(request.id, f"Invalid memory_mode: {mode_raw}").to_bytes()
            )
            return

        try:
            updated = await _run_blocking_with_timeout(
                label="db.set_session_mode",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.set_session_mode,
                args=(),
                kwargs={"session_id": session_id, "memory_mode": mode},
                request_id=request.id,
                method=request.method,
            )
        except ValueError as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    _format_exception_message(exc, fallback="Unable to set session mode"),
                ).to_bytes()
            )
            return

        payload = _session_payload(updated)
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())
        await _broadcast_session_event(action="updated", session=payload)

    async def handle_session_rename(request: IncomingRequest, client: ClientConnection) -> None:
        """Rename a session."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        title_raw = request.params.get("title")
        title = title_raw.strip() if isinstance(title_raw, str) else ""
        if not session_id or not title:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or title").to_bytes()
            )
            return

        try:
            renamed = await _run_blocking_with_timeout(
                label="db.rename_session",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.rename_session,
                args=(),
                kwargs={"session_id": session_id, "title": title},
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Unable to rename session")
                ).to_bytes()
            )
            return
        payload = _session_payload(renamed)
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())
        await _broadcast_session_event(action="updated", session=payload)

    async def handle_session_delete(request: IncomingRequest, client: ClientConnection) -> None:
        """Delete a session and its encrypted memory store."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        if not session_id:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id").to_bytes()
            )
            return
        existing_session = await _run_blocking_with_timeout(
            label="db.get_session",
            timeout_seconds=db_timeout_seconds,
            func=memory_manager.get_session,
            args=(session_id,),
            request_id=request.id,
            method=request.method,
        )
        try:
            await _run_blocking_with_timeout(
                label="db.delete_session",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.delete_session,
                args=(session_id,),
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    _format_exception_message(exc, fallback=f"Unable to delete session: {session_id}"),
                ).to_bytes()
            )
            return

        payload = {
            "deleted": True,
            "session_id": session_id,
        }
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())
        await _broadcast_session_event(
            action="deleted",
            session=(
                _session_payload(existing_session)
                if existing_session is not None
                else {"session_id": session_id, "status": "deleted"}
            ),
        )

    async def handle_session_delete_many(request: IncomingRequest, client: ClientConnection) -> None:
        """Delete multiple sessions and return per-session outcomes."""
        raw_ids = request.params.get("session_ids")
        if not isinstance(raw_ids, list):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_ids list").to_bytes()
            )
            return

        ordered_ids: list[str] = []
        seen: set[str] = set()
        for raw in raw_ids:
            normalized = _normalize_session_id(raw, fallback="")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered_ids.append(normalized)

        if not ordered_ids:
            await client.send(
                ErrorMessage.invalid_request(request.id, "No valid session_ids provided").to_bytes()
            )
            return

        try:
            deleted_ids, failed = await _run_blocking_with_timeout(
                label="db.delete_sessions",
                timeout_seconds=min(max(db_timeout_seconds, len(ordered_ids) * 5.0), 60.0),
                func=memory_manager.delete_sessions,
                args=(ordered_ids,),
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    _format_exception_message(exc, fallback="Unable to delete sessions"),
                ).to_bytes()
            )
            return

        payload = {
            "requested_count": len(ordered_ids),
            "deleted_count": len(deleted_ids),
            "deleted_session_ids": deleted_ids,
            "failed": [
                {"session_id": session_id, "error": reason}
                for session_id, reason in failed.items()
            ],
        }
        await client.send(ResultMessage.create(request.id, json.dumps(payload)).to_bytes())
        for deleted_session_id in deleted_ids:
            await _broadcast_session_event(
                action="deleted",
                session={"session_id": deleted_session_id, "status": "deleted"},
            )

    async def handle_memory_list(request: IncomingRequest, client: ClientConnection) -> None:
        """List semantic memories for a session."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        if not session_id:
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id").to_bytes()
            )
            return
        session_exists = await _run_blocking_with_timeout(
            label="db.get_session",
            timeout_seconds=db_timeout_seconds,
            func=memory_manager.get_session,
            args=(session_id,),
            request_id=request.id,
            method=request.method,
        )
        if session_exists is None:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    f"Unknown session_id: {session_id}",
                ).to_bytes()
            )
            return
        limit_raw = request.params.get("limit", 100)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 100
        try:
            memories = await _run_blocking_with_timeout(
                label="db.list_memories",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.list_memories,
                args=(session_id,),
                kwargs={"limit": max(1, min(limit, 500))},
                request_id=request.id,
                method=request.method,
            )
        except ValueError as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    _format_exception_message(exc, fallback="Unknown session"),
                ).to_bytes()
            )
            return
        await client.send(ResultMessage.create(request.id, json.dumps(memories)).to_bytes())

    async def handle_memory_delete(request: IncomingRequest, client: ClientConnection) -> None:
        """Delete a semantic memory entry."""
        session_id = _normalize_session_id(
            request.params.get("session_id"),
            fallback="",
        )
        memory_id = request.params.get("memory_id")
        if not session_id or not isinstance(memory_id, str):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or memory_id").to_bytes()
            )
            return
        session_exists = await _run_blocking_with_timeout(
            label="db.get_session",
            timeout_seconds=db_timeout_seconds,
            func=memory_manager.get_session,
            args=(session_id,),
            request_id=request.id,
            method=request.method,
        )
        if session_exists is None:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    f"Unknown session_id: {session_id}",
                ).to_bytes()
            )
            return
        normalized_memory_id = memory_id.strip()
        try:
            deleted = await _run_blocking_with_timeout(
                label="db.delete_memory",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.delete_memory,
                args=(session_id, normalized_memory_id),
                request_id=request.id,
                method=request.method,
            )
        except ValueError as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id,
                    _format_exception_message(exc, fallback="Unknown session"),
                ).to_bytes()
            )
            return
        await client.send(
            ResultMessage.create(
                request.id,
                json.dumps({"deleted": deleted, "memory_id": normalized_memory_id}),
            ).to_bytes()
        )
        if deleted:
            await _broadcast_memory_event(
                action="deleted",
                session_id=session_id,
                memory_id=normalized_memory_id,
            )
            await _broadcast_session_refresh(
                session_id=session_id,
                request_id=request.id,
                method=request.method,
            )

    # ------------------------------------------------------------------
    # notes IPC handlers (frontend CRUD)
    # ------------------------------------------------------------------
    async def handle_notes_list(request: IncomingRequest, client: ClientConnection) -> None:
        """List notes for a session."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        if not session_id:
            await client.send(ErrorMessage.invalid_request(request.id, "Missing session_id").to_bytes())
            return
        limit_raw = request.params.get("limit", 200)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 200
        try:
            notes = await _run_blocking_with_timeout(
                label="db.list_notes",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.list_notes,
                args=(session_id,),
                kwargs={"limit": max(1, min(limit, 500))},
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to list notes"),
                ).to_bytes()
            )
            return
        await client.send(ResultMessage.create(request.id, json.dumps(notes)).to_bytes())

    async def handle_notes_create(request: IncomingRequest, client: ClientConnection) -> None:
        """Create a new note."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        content = request.params.get("content")
        if not session_id or not isinstance(content, str) or not content.strip():
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or content").to_bytes()
            )
            return
        source = request.params.get("source", "user")
        if source not in ("user", "agent"):
            source = "user"
        try:
            note = await _run_blocking_with_timeout(
                label="db.create_note",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.create_note,
                args=(session_id,),
                kwargs={"content": content.strip(), "source": source},
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to create note"),
                ).to_bytes()
            )
            return
        await client.send(ResultMessage.create(request.id, json.dumps(note)).to_bytes())
        await _broadcast_notes_event(
            action="created",
            session_id=session_id,
            note=note,
        )
        await _broadcast_session_refresh(
            session_id=session_id,
            request_id=request.id,
            method=request.method,
        )

    async def handle_notes_update(request: IncomingRequest, client: ClientConnection) -> None:
        """Update an existing note."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        note_id = request.params.get("note_id")
        if not session_id or not isinstance(note_id, str):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or note_id").to_bytes()
            )
            return
        content = request.params.get("content")
        if content is not None and not isinstance(content, str):
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, "Invalid content: expected string when provided",
                ).to_bytes()
            )
            return
        is_pinned = request.params.get("is_pinned")
        if is_pinned is not None and not isinstance(is_pinned, bool):
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, "Invalid is_pinned: expected boolean when provided",
                ).to_bytes()
            )
            return
        try:
            updated = await _run_blocking_with_timeout(
                label="db.update_note",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.update_note,
                args=(session_id, note_id.strip()),
                kwargs={
                    "content": content,
                    "is_pinned": is_pinned,
                },
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to update note"),
                ).to_bytes()
            )
            return
        if updated is None:
            await client.send(
                ErrorMessage.invalid_request(request.id, f"Note not found: {note_id}").to_bytes()
            )
            return
        await client.send(ResultMessage.create(request.id, json.dumps(updated)).to_bytes())
        await _broadcast_notes_event(
            action="updated",
            session_id=session_id,
            note=updated,
        )
        await _broadcast_session_refresh(
            session_id=session_id,
            request_id=request.id,
            method=request.method,
        )

    async def handle_notes_delete(request: IncomingRequest, client: ClientConnection) -> None:
        """Delete a note (soft-delete)."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        note_id = request.params.get("note_id")
        if not session_id or not isinstance(note_id, str):
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or note_id").to_bytes()
            )
            return
        normalized_note_id = note_id.strip()
        try:
            deleted = await _run_blocking_with_timeout(
                label="db.delete_note",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.delete_note,
                args=(session_id, normalized_note_id),
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to delete note"),
                ).to_bytes()
            )
            return
        await client.send(
            ResultMessage.create(
                request.id, json.dumps({"deleted": deleted, "note_id": normalized_note_id}),
            ).to_bytes()
        )
        if deleted:
            await _broadcast_notes_event(
                action="deleted",
                session_id=session_id,
                note_id=normalized_note_id,
            )
            await _broadcast_session_refresh(
                session_id=session_id,
                request_id=request.id,
                method=request.method,
            )

    async def handle_notes_get_image(request: IncomingRequest, client: ClientConnection) -> None:
        """Return a single note image's data (base64-encoded) by image_id."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        image_id = request.params.get("image_id")
        if not session_id or not isinstance(image_id, str) or not image_id.strip():
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or image_id").to_bytes()
            )
            return
        try:
            img = await _run_blocking_with_timeout(
                label="db.get_note_image",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.get_note_image,
                args=(session_id, image_id.strip()),
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to get note image"),
                ).to_bytes()
            )
            return
        if img is None:
            await client.send(
                ErrorMessage.invalid_request(request.id, f"Image not found: {image_id}").to_bytes()
            )
            return
        import base64 as _b64_mod
        result = {
            "image_id": img["image_id"],
            "note_id": img["note_id"],
            "image_data": _b64_mod.b64encode(img["image_data"]).decode("ascii"),
            "mime_type": img["mime_type"],
            "width": img["width"],
            "height": img["height"],
            "alt_text": img["alt_text"],
        }
        await client.send(ResultMessage.create(request.id, json.dumps(result)).to_bytes())

    async def handle_notes_list_versions(request: IncomingRequest, client: ClientConnection) -> None:
        """Return version history for a note."""
        session_id = _normalize_session_id(request.params.get("session_id"), fallback="")
        note_id = request.params.get("note_id")
        if not session_id or not isinstance(note_id, str) or not note_id.strip():
            await client.send(
                ErrorMessage.invalid_request(request.id, "Missing session_id or note_id").to_bytes()
            )
            return
        try:
            versions = await _run_blocking_with_timeout(
                label="db.list_note_versions",
                timeout_seconds=db_timeout_seconds,
                func=memory_manager.list_note_versions,
                args=(session_id, note_id.strip()),
                kwargs={"limit": 50},
                request_id=request.id,
                method=request.method,
            )
        except Exception as exc:
            await client.send(
                ErrorMessage.invalid_request(
                    request.id, _format_exception_message(exc, fallback="Failed to list versions"),
                ).to_bytes()
            )
            return
        await client.send(ResultMessage.create(request.id, json.dumps(versions)).to_bytes())

    # Initialize hot reload manager
    reload_manager = init_reload_manager(
        watch_dir=Path(__file__).parent,
        poll_interval=2.0,
        auto_watch=True,  # Enable automatic file watching
    )
    
    def on_reload_complete(event: ReloadEvent) -> None:
        """Callback when hot reload completes - notify all clients."""
        logger.info(f"Hot reload event: {event.trigger}, success={event.success}")
        # Note: This is called synchronously, so we can't await here
        # Clients will be notified on their next request via version check
    
    reload_manager.on_reload(on_reload_complete)

    async def handle_client_disconnect(disconnected_client: ClientConnection) -> None:
        cancelled = _cancel_requests_for_client(disconnected_client.address)
        if cancelled > 0:
            logger.info(
                "Cancelled %s in-flight request(s) after client disconnect: %s",
                cancelled,
                disconnected_client.address,
            )

    server.set_disconnect_handler(handle_client_disconnect)
    
    async def handle_reload(request: IncomingRequest, client: ClientConnection) -> None:
        """Handles reload requests from the SwiftUI frontend."""
        request_id = request.id
        trigger = request.params.get("trigger", "ipc")
        
        logger.info(f"Reload requested via IPC (trigger: {trigger})")
        
        # Send reload started notification
        started_msg = SystemMessage.reload_started(request_id, trigger)
        await client.send(started_msg.to_bytes())
        
        # Perform the reload
        event = reload_manager.reload_modules(trigger=trigger)
        
        # Send reload complete notification
        complete_msg = SystemMessage.reload_complete(
            request_id,
            success=event.success,
            new_version=reload_manager.version,
            error=event.error,
        )
        await client.send(complete_msg.to_bytes())
        
        if event.success:
            logger.info(f"Reload complete. New version: {reload_manager.version}")
        else:
            logger.error(f"Reload failed: {event.error}")
    
    async def handle_version(request: IncomingRequest, client: ClientConnection) -> None:
        """Handles version requests - returns protocol and code version."""
        version_msg = SystemMessage.version_info(
            request.id,
            protocol_version=PROTOCOL_VERSION,
            code_version=reload_manager.version,
            features=[
                "auth.hello",
                "prompt",
                "prompt.execution_mode",
                "prompt.input_paths",
                "cancel",
                "tool.confirm",
                "screen.capture_response",
                "ping",
                "reload",
                "version",
                "session.create",
                "session.list",
                "session.history",
                "session.set_mode",
                "session.rename",
                "session.delete",
                "session.delete_many",
                "memory.list",
                "memory.delete",
                "notes.list",
                "notes.create",
                "notes.update",
                "notes.delete",
                "notes.get_image",
                "notes.list_versions",
                "system.session_events",
                "system.notes_events",
                "system.memory_events",
            ],
        )
        await client.send(version_msg.to_bytes())
    
    # Register handlers
    server.register_handler("prompt", handle_prompt)
    server.register_handler("cancel", handle_cancel)
    server.register_handler("tool.confirm", handle_tool_confirm)
    server.register_handler("screen.capture_response", handle_screen_capture)
    server.register_handler("ping", handle_ping)
    server.register_handler("session.create", handle_session_create)
    server.register_handler("session.list", handle_session_list)
    server.register_handler("session.history", handle_session_history)
    server.register_handler("session.set_mode", handle_session_set_mode)
    server.register_handler("session.rename", handle_session_rename)
    server.register_handler("session.delete", handle_session_delete)
    server.register_handler("session.delete_many", handle_session_delete_many)
    server.register_handler("memory.list", handle_memory_list)
    server.register_handler("memory.delete", handle_memory_delete)
    server.register_handler("notes.list", handle_notes_list)
    server.register_handler("notes.create", handle_notes_create)
    server.register_handler("notes.update", handle_notes_update)
    server.register_handler("notes.delete", handle_notes_delete)
    server.register_handler("notes.get_image", handle_notes_get_image)
    server.register_handler("notes.list_versions", handle_notes_list_versions)
    server.register_handler("reload", handle_reload)
    server.register_handler("version", handle_version)

    async def _db_metrics_reporter() -> None:
        while True:
            await asyncio.sleep(max(1.0, db_metrics_interval_seconds))
            snapshot = get_db_metrics_snapshot()
            logger.info(
                "sqlite_metrics",
                extra={
                    "component": "db.metrics",
                    "method": "sqlite",
                    "duration_ms": None,
                    "error_type": None,
                    "error_message": None,
                    "metrics": snapshot,
                },
            )

    async def _plan_mode_nlp_preload_worker() -> None:
        nonlocal plan_mode_nlp_ready, plan_mode_nlp_error, plan_mode_nlp_preload_ms
        started = time.perf_counter()
        try:
            model_name = await asyncio.to_thread(_preload_plan_mode_nlp_classifier, logger)
            plan_mode_nlp_ready = True
            plan_mode_nlp_error = None
            logger.info(
                "Plan-mode NLP preload complete",
                extra={
                    "component": "plan_mode_nlp_preload",
                    "method": "startup",
                    "duration_ms": None,
                    "error_type": None,
                    "error_message": None,
                    "model_name": model_name,
                },
            )
        except Exception as exc:
            plan_mode_nlp_ready = False
            plan_mode_nlp_error = _format_exception_message(
                exc,
                fallback="spaCy model unavailable",
            )
            logger.error(
                "Plan-mode NLP preload failed: %s",
                plan_mode_nlp_error,
            )
        finally:
            plan_mode_nlp_preload_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "plan_mode_nlp_preload_complete",
                extra={
                    "component": "plan_mode_nlp_preload",
                    "method": "startup",
                    "duration_ms": round(plan_mode_nlp_preload_ms, 3),
                    "error_type": None if plan_mode_nlp_ready else "RuntimeError",
                    "error_message": plan_mode_nlp_error,
                },
            )

    async def _watch_unhealthy_shutdown() -> None:
        await unhealthy_shutdown_requested.wait()
        logger.critical("Unhealthy blocking timeout detected; shutting down IPC server")
        await server.stop()
    
    # Start server
    try:
        socket_bind_started = time.perf_counter()
        await server.start()
        socket_bind_ms = (time.perf_counter() - socket_bind_started) * 1000.0
        logger.info(
            "ipc_socket_bound",
            extra={
                "component": "ipc.server",
                "method": "startup",
                "duration_ms": round(socket_bind_ms, 3),
                "error_type": None,
                "error_message": None,
            },
        )
        unhealthy_shutdown_task = asyncio.create_task(_watch_unhealthy_shutdown())
        plan_mode_nlp_preload_task = asyncio.create_task(_plan_mode_nlp_preload_worker())
        if db_metrics_enabled:
            db_metrics_task = asyncio.create_task(_db_metrics_reporter())
        
        # Start hot reload file watcher
        await reload_manager.start()
        
        print_info(f"IPC Server started on {server.socket_path}")
        print_info(f"Protocol version: {PROTOCOL_VERSION}")
        print_info(f"Code version: {reload_manager.version}")
        print_info("Hot reload enabled - code changes will be auto-detected")
        print_info("Press Ctrl+C to stop...")
        
        # Wait for shutdown signal
        try:
            await server.serve_forever()
        except asyncio.CancelledError:
            pass
        
    finally:
        # Cancel any in-flight prompt tasks before shutdown.
        unhealthy_shutdown_requested.set()
        if unhealthy_shutdown_task is not None:
            unhealthy_shutdown_task.cancel()
            await asyncio.gather(unhealthy_shutdown_task, return_exceptions=True)
        if plan_mode_nlp_preload_task is not None:
            plan_mode_nlp_preload_task.cancel()
            await asyncio.gather(plan_mode_nlp_preload_task, return_exceptions=True)
        if db_metrics_task is not None:
            db_metrics_task.cancel()
            await asyncio.gather(db_metrics_task, return_exceptions=True)
        for task in list(active_prompt_tasks.values()):
            if not task.done():
                task.cancel()
        if active_prompt_tasks:
            await asyncio.gather(*active_prompt_tasks.values(), return_exceptions=True)
        await reload_manager.stop()
        await server.stop()
        if audit_logger:
            try:
                audit_logger.log_event(
                    EventType.SHUTDOWN,
                    {
                        "mode": "ipc_server",
                    },
                )
            except AuditLogError as e:
                logger.warning("Failed to write audit shutdown event: %s", e)
        print_info("IPC Server stopped")
    
    return EXIT_SUCCESS


def main(args: list[str] | None = None) -> int:
    """Main entry point for the CLI.
    
    Args:
        args: Command line arguments. If None, uses sys.argv.
    
    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    # Load environment variables from .env file (if exists)
    load_dotenv()
    
    parser = create_argument_parser()
    parsed_args = parser.parse_args(args)
    
    # Setup logging
    setup_logging(parsed_args.verbose)
    logger = logging.getLogger(__name__)
    
    no_color = parsed_args.no_color
    
    # Step 1: Load configuration from environment
    try:
        config = Config.from_env()
        logger.debug("Configuration loaded successfully")
    except ConfigurationError as e:
        print_error(f"Configuration error: {e}", no_color)
        return EXIT_CONFIG_ERROR
    
    # Handle dry run mode
    if parsed_args.dry_run:
        run_dry_run(config, no_color)
        return EXIT_SUCCESS
    
    # Handle server mode
    if parsed_args.server:
        return asyncio.run(
            run_server(
                config,
                socket_path=parsed_args.socket_path,
                verbose=parsed_args.verbose,
            )
        )
    
    # For CLI mode, prompt is required
    if not parsed_args.prompt:
        print_error("prompt is required for CLI mode. Use --server for IPC mode.", no_color)
        return EXIT_CONFIG_ERROR
    
    # Step 2: Load schemas and create validator
    try:
        validator = SchemaValidator(config.schemas_dir)
        tools = validator.get_all_tools_for_gemini()
        logger.debug(f"Loaded {len(tools)} tool schemas")
    except SchemaLoadError as e:
        print_error(f"Schema loading error: {e}", no_color)
        return EXIT_CONFIG_ERROR
    
    if not tools:
        print_error("No tool schemas found in schemas directory", no_color)
        return EXIT_CONFIG_ERROR

    try:
        migration_result = run_preflight_migration(config.memory_root)
        if migration_result.already_migrated:
            logger.info(
                "Memory preflight migration already completed (marker=%s)",
                migration_result.marker_path,
            )
        else:
            logger.info(
                "Memory preflight migration completed (upgraded_hmac_rows=%s removed_ghost_sessions=%s backup=%s marker=%s)",
                migration_result.upgraded_hmac_rows,
                migration_result.removed_ghost_sessions,
                migration_result.backup_path,
                migration_result.marker_path,
            )
    except MemoryMigrationError as e:
        print_error(f"Strict memory migration failed: {e}", no_color)
        return EXIT_CONFIG_ERROR

    try:
        memory_manager = MemoryManager(config.memory_root)
        logger.debug("Memory manager initialized")
    except Exception as e:
        print_error(f"Memory manager initialization failed: {e}", no_color)
        return EXIT_CONFIG_ERROR

    try:
        tool_executor = ToolExecutor.from_config(config)
        logger.debug("Tool executor initialized")
    except Exception as e:
        print_error(f"Tool executor initialization failed: {e}", no_color)
        return EXIT_CONFIG_ERROR
    
    # Step 3: Initialize audit logger
    try:
        audit_logger = AuditLogger(config.audit_log_path)
        audit_include_prompt = bool(getattr(config, "audit_include_prompt", False))
        startup_payload: dict[str, object] = {
            "model": config.model_name,
            "tools_count": len(tools),
            "mode": "cli",
            "prompt_present": bool(parsed_args.prompt),
            "prompt_chars": len(parsed_args.prompt),
        }
        if audit_include_prompt:
            startup_payload["prompt"] = parsed_args.prompt
        audit_logger.log_event(EventType.STARTUP, startup_payload)
        logger.debug("Audit logger initialized")
    except AuditLogError as e:
        print_error(f"Audit logging initialization failed: {e}", no_color)
        return EXIT_CONFIG_ERROR
    
    # Step 4: Initialize Gemini client and send prompt
    try:
        client = GeminiClient(
            api_key=config.gemini_api_key,
            model_name=config.model_name,
            max_retries=config.max_retries,
            retry_delay=config.retry_delay,
            require_no_training=config.require_no_training,
            use_vertexai=config.use_vertexai,
            vertex_project=config.vertex_project,
            vertex_location=config.vertex_location,
        )
        logger.debug("Gemini client initialized")

        # Wire semantic embedding service (second init site — CLI mode)
        try:
            embedding_client = getattr(client, "_client", client)
            embedding_service = EmbeddingService(embedding_client)
            memory_manager.set_embedding_service(embedding_service)
            logger.debug("Semantic embedding service initialized")
        except Exception as e:
            print_error(f"Embedding service initialization failed: {e}", no_color)
            if audit_logger:
                audit_logger.log_error("EMBEDDING_INIT_ERROR", str(e))
            return EXIT_CONFIG_ERROR

        base_system_instruction = build_system_prompt(tools)
        system_instruction = inject_model_identity(
            base_system_instruction, config.model_name
        )
        logger.debug(
            "System prompt loaded (%s chars, %s tools injected)",
            len(system_instruction),
            len(tools),
        )
        
        cli_session_id = os.environ.get("AI_AGENT_SESSION_ID", "cli-default")
        cli_memory_mode = _parse_memory_mode(os.environ.get("AI_AGENT_MEMORY_MODE"))
        prepared = memory_manager.prepare_prompt_context(
            session_id=cli_session_id,
            prompt=parsed_args.prompt,
            memory_mode=cli_memory_mode,
        )

        response = client.send_prompt_with_tools(
            prompt=prepared.augmented_prompt,
            tools=tools,
            system_instruction=system_instruction,
        )
        logger.debug("Received response from Gemini")
        
    except GeminiRateLimitError as e:
        print_error(f"Rate limit exceeded: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("RATE_LIMIT", str(e))
        return EXIT_API_ERROR
    except GeminiServerError as e:
        print_error(f"Server error: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("SERVER_ERROR", str(e))
        return EXIT_API_ERROR
    except GeminiAPIError as e:
        print_error(f"API error: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("API_ERROR", str(e))
        return EXIT_API_ERROR
    except GeminiClientError as e:
        print_error(f"Client error: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("CLIENT_ERROR", str(e))
        return EXIT_API_ERROR
    except SystemPromptLoadError as e:
        print_error(f"System prompt load error: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("PROMPT_LOAD_ERROR", str(e))
        return EXIT_CONFIG_ERROR
    
    # Step 5: Parse response for function call
    parser_instance = ToolCallParser()
    
    try:
        tool_call = parser_instance.parse_response(response)
    except MalformedResponseError as e:
        print_error(f"Failed to parse response: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("PARSE_ERROR", str(e))
        return EXIT_VALIDATION_ERROR
    
    if tool_call is None:
        # No function call in response - might be a text response
        if response.get("text"):
            raw_text = str(response["text"])
            rendered_text = (
                sanitize_user_visible_response(raw_text)
                if looks_like_json_payload(raw_text)
                else raw_text
            )
            memory_manager.record_interaction(
                session_id=cli_session_id,
                memory_mode=cli_memory_mode,
                user_prompt=parsed_args.prompt,
                assistant_response=rendered_text,
                model_name=config.model_name,
            )
            print_info("Gemini responded with text instead of a tool call:", no_color)
            print(rendered_text)
            if audit_logger:
                audit_logger.log_event(EventType.API_RESPONSE, {
                    "type": "text",
                    "text": rendered_text[:500],  # Truncate for log
                })
            return EXIT_SUCCESS
        else:
            print_error("No tool call or text response received", no_color)
            if audit_logger:
                audit_logger.log_error("NO_RESPONSE", "Empty response from Gemini")
            return EXIT_VALIDATION_ERROR
    
    # Step 6: Validate tool call against schema
    try:
        validator.validate_tool_call(tool_call.name, tool_call.arguments)
        logger.debug(f"Validation passed for tool: {tool_call.name}")
    except SchemaNotFoundError as e:
        print_error(f"Unknown tool: {e}", no_color)
        if audit_logger:
            audit_logger.log_error("UNKNOWN_TOOL", str(e), {
                "tool": tool_call.name,
                "arguments": tool_call.arguments,
            })
        return EXIT_VALIDATION_ERROR
    except ValidationFailedError as e:
        print_error(f"Validation failed: {e}", no_color)
        if audit_logger:
            audit_logger.log_validation_fail(
                tool_call.name,
                tool_call.arguments,
                e.errors,
            )
        return EXIT_VALIDATION_ERROR
    
    # Step 7: Log to audit log
    if audit_logger:
        audit_include_prompt = bool(getattr(config, "audit_include_prompt", False))
        audit_logger.log_tool_call(
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
            user_prompt=parsed_args.prompt if audit_include_prompt else None,
            validated=True,
        )

    # Step 8: Execute tool call
    try:
        execution = tool_executor.execute(tool_call.name, tool_call.arguments)
    except ToolExecutionError as e:
        message = str(e)
        print_error(f"Tool execution failed: {message}", no_color)
        if audit_logger:
            audit_logger.log_error(
                "TOOL_EXECUTION_FAILED",
                message,
                {
                    "tool": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            )
        memory_manager.record_interaction(
            session_id=cli_session_id,
            memory_mode=cli_memory_mode,
            user_prompt=parsed_args.prompt,
            assistant_response=f"Tool execution failed: {message}",
            model_name=config.model_name,
        )
        return EXIT_VALIDATION_ERROR

    execution_text, _ = _format_tool_execution_output(tool_call.name, execution)
    execution_json = json.dumps(execution, ensure_ascii=False)
    memory_manager.record_interaction(
        session_id=cli_session_id,
        memory_mode=cli_memory_mode,
        user_prompt=parsed_args.prompt,
        assistant_response=execution_text,
        model_name=config.model_name,
    )

    # Step 9: Display results
    print_success(f"Tool call executed: {tool_call.name}", no_color)
    print()
    print("Tool: " + tool_call.name)
    print("Arguments:")
    print(json.dumps(tool_call.arguments, indent=2))
    print("Execution:")
    print(execution_text)
    if execution_text != execution_json:
        print()
        print("Execution (JSON):")
        print(json.dumps(execution, indent=2, ensure_ascii=False))
    
    return EXIT_SUCCESS if execution.get("ok") else EXIT_VALIDATION_ERROR


def cli_main() -> NoReturn:
    """Entry point for CLI that exits with appropriate code.
    
    This function is intended for use as a console script entry point.
    """
    sys.exit(main())


if __name__ == "__main__":
    cli_main()
