"""Plan-mode logic extracted from ``agent_host.main``.

This module contains all plan-mode constants, regex patterns, dataclasses,
and helper/decision functions that drive the plan-mode clarification,
scoring, alignment, and bootstrap pipeline.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from agent_host.nlp import PlanClarificationIntentClassifier

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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
    "read_document",
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
_PLAN_MODE_CLARIFICATION_INTENT_CLASSIFIER = PlanClarificationIntentClassifier()


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Preload helper
# ---------------------------------------------------------------------------

def _preload_plan_mode_nlp_classifier(logger: logging.Logger) -> str:
    result = _PLAN_MODE_CLARIFICATION_INTENT_CLASSIFIER.classify(
        reply_prompt="Q1:B, Q2:D, notes: keep it practical and beginner-friendly.",
        root_prompt="Create a planning roadmap with timeline and constraints.",
        pending_dimension="goal",
        question_count=2,
    )
    classifier_name = result.model_name or "builtin"
    logger.info("Plan clarification classifier ready: %s", classifier_name)
    return classifier_name


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_plan_mode_discovery_budget() -> int:
    raw = os.environ.get(
        "AI_AGENT_PLAN_MODE_DISCOVERY_BEFORE_PLANNER",
        str(_PLAN_MODE_DISCOVERY_BEFORE_PLANNER_DEFAULT),
    )
    try:
        parsed = int(str(raw).strip())
    except ValueError:
        return _PLAN_MODE_DISCOVERY_BEFORE_PLANNER_DEFAULT
    return max(0, min(_PLAN_MODE_DISCOVERY_BEFORE_PLANNER_DEFAULT, parsed))


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


# ---------------------------------------------------------------------------
# Plan-mode logic functions
# ---------------------------------------------------------------------------

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

_FINAL_ANSWER_READY_PREFIX = "FINAL_ANSWER_READY:"


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


def _build_live_web_audit_instruction(*, root_prompt: str, draft_response: str) -> str:
    compact_prompt = re.sub(r"\s+", " ", root_prompt.strip())
    compact_draft = draft_response.strip()
    return (
        "Audit the draft answer against the original request and the available tools.\n"
        "Use recent conversation/session context first.\n"
        "Only call `browse_web` if the answer materially depends on current external facts, live availability, or explicit web verification.\n"
        "Do not call `browse_web` for ordinary follow-ups, rewrites, summaries, or note refinements that can be answered from existing context.\n"
        "If live web browsing is not needed, return the final answer again and begin it with the exact prefix "
        f"`{_FINAL_ANSWER_READY_PREFIX}`.\n"
        "Do not describe this audit step to the user.\n\n"
        f"Original request: {compact_prompt}\n\n"
        f"Draft answer to audit:\n{compact_draft}"
    )


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
    # P6: Removed false-negative early-return that rejected text matching
    # both Q-numbering ("Q1.") and option blocks ("A) B) C) D)").  That
    # is the exact format the backend's own clarification uses, so the
    # model may imitate it.  The has_clarify_signal check below is the
    # reliable indicator regardless of formatting.

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
