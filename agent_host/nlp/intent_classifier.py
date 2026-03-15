"""Local NLP intent classifier for plan-mode clarification replies.

This module is privacy-first:
- all text is sanitized before NLP processing,
- filesystem paths and common sensitive tokens are redacted,
- classifier state is process-local only.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_TOKEN_PATTERN = re.compile(r"[a-z0-9]{3,}")
_URL_PATTERN = re.compile(r"\bhttps?://[^\s]+", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_BEARER_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/\-]+=*\b", re.IGNORECASE)
_LONG_HEX_PATTERN = re.compile(r"\b[a-fA-F0-9]{32,}\b")
_BASE64ISH_PATTERN = re.compile(r"\b[A-Za-z0-9+/]{48,}={0,2}\b")
_UNIX_PATH_PATTERN = re.compile(
    r"(?:(?<=\s)|^)(?:~|/)(?:[^/\s]+/)*[^/\s]+(?:(?=\s)|$)"
)
_WINDOWS_PATH_PATTERN = re.compile(
    r"(?:(?<=\s)|^)(?:[A-Za-z]:\\|\\\\)[^\\\s]+(?:\\[^\\\s]+)*(?:(?=\s)|$)"
)
_REL_PATH_PATTERN = re.compile(
    r"(?:(?<=\s)|^)(?:\.\.?[/\\])(?:[^/\s\\]+[/\\])*[^/\s\\]+(?:(?=\s)|$)"
)
_INLINE_PATH_PATTERN = re.compile(
    r"\b(?:[^/\s\\]+[/\\])+[^/\s\\]+\.[A-Za-z0-9]{1,12}\b"
)
_GOAL_SIGNAL_PATTERN = re.compile(r"\b(goal|objective|outcome|target)\b", re.IGNORECASE)
_TIMEFRAME_SIGNAL_PATTERN = re.compile(
    r"\b(day|days|week|weeks|month|months|year|years|deadline|timeline)\b",
    re.IGNORECASE,
)
_BASELINE_SIGNAL_PATTERN = re.compile(
    r"\b(beginner|intermediate|advanced|experience|background|baseline)\b",
    re.IGNORECASE,
)
_CONSTRAINT_SIGNAL_PATTERN = re.compile(
    r"\b(limit|budget|constraint|available|priority|avoid|weekend|weekends|weekday|weekdays|hours?)\b",
    re.IGNORECASE,
)
_NEW_TASK_PREFIX_PATTERN = re.compile(
    r"^\s*(write|draft|compose|explain|tell|summarize|search|browse|find|open|create|make)\b",
    re.IGNORECASE,
)
_QUESTION_WORD_PATTERN = re.compile(r"^\s*(what|who|when|where|why|how)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ClarificationIntentResult:
    """Result returned by clarification-reply intent analysis."""

    is_clarification_reply: bool
    confidence: float
    source: str
    model_name: str
    sanitized_reply: str
    sanitized_root_prompt: str


class PlanClarificationIntentClassifier:
    """Classifies whether text is likely a clarification reply vs a new task."""

    _CLASSIFIER_NAME = "builtin"

    def __init__(self, model_candidates: tuple[str, ...] | None = None) -> None:
        del model_candidates
        self._load_error: str | None = None

    @property
    def load_error(self) -> str | None:
        return self._load_error

    @staticmethod
    def sanitize_text(text: str) -> str:
        """Remove sensitive artifacts before NLP inference."""
        if not text:
            return ""
        sanitized = text
        sanitized = _URL_PATTERN.sub("[URL]", sanitized)
        sanitized = _EMAIL_PATTERN.sub("[EMAIL]", sanitized)
        sanitized = _BEARER_PATTERN.sub("Bearer [TOKEN]", sanitized)
        sanitized = _LONG_HEX_PATTERN.sub("[HEX]", sanitized)
        sanitized = _BASE64ISH_PATTERN.sub("[TOKEN]", sanitized)
        sanitized = _WINDOWS_PATH_PATTERN.sub("[PATH]", sanitized)
        sanitized = _UNIX_PATH_PATTERN.sub("[PATH]", sanitized)
        sanitized = _REL_PATH_PATTERN.sub("[PATH]", sanitized)
        sanitized = _INLINE_PATH_PATTERN.sub("[PATH]", sanitized)
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        return sanitized

    def classify(
        self,
        *,
        reply_prompt: str,
        root_prompt: str,
        pending_dimension: str | None,
        question_count: int,
    ) -> ClarificationIntentResult:
        """Return clarification-intent probability using the built-in classifier."""
        sanitized_reply = self.sanitize_text(reply_prompt)
        sanitized_root = self.sanitize_text(root_prompt)
        if not sanitized_reply:
            return ClarificationIntentResult(
                is_clarification_reply=False,
                confidence=0.0,
                source=self._CLASSIFIER_NAME,
                model_name=self._CLASSIFIER_NAME,
                sanitized_reply="",
                sanitized_root_prompt=sanitized_root,
            )

        reply_tokens = self._token_set(sanitized_reply)
        root_tokens = self._token_set(sanitized_root)
        dimension_tokens = self._token_set(self._dimension_hint(pending_dimension))
        overlap_ratio = 0.0
        if reply_tokens:
            overlap_ratio = len(reply_tokens.intersection(root_tokens)) / len(reply_tokens)
        dimension_overlap = 0.0
        if reply_tokens:
            dimension_overlap = len(reply_tokens.intersection(dimension_tokens)) / len(reply_tokens)

        specificity_score, dimension_match = self._specificity_signal(
            reply=sanitized_reply,
            pending_dimension=pending_dimension,
        )
        shape_signal = self._shape_signal(sanitized_reply, question_count=question_count)
        semantic_relevance = max(overlap_ratio, dimension_overlap)
        new_task_penalty = self._new_task_penalty(
            reply=sanitized_reply,
            semantic_relevance=semantic_relevance,
        )

        confidence = (
            (semantic_relevance * 0.30)
            + (shape_signal * 0.20)
            + (specificity_score * 0.36)
            + (0.12 if dimension_match else 0.0)
            - new_task_penalty
        )
        confidence = max(0.0, min(1.0, confidence))

        threshold = 0.36 if question_count > 1 else 0.40
        return ClarificationIntentResult(
            is_clarification_reply=confidence >= threshold,
            confidence=confidence,
            source=self._CLASSIFIER_NAME,
            model_name=self._CLASSIFIER_NAME,
            sanitized_reply=sanitized_reply,
            sanitized_root_prompt=sanitized_root,
        )

    @staticmethod
    def _token_set(text: str) -> set[str]:
        return set(_TOKEN_PATTERN.findall(text.lower()))

    @staticmethod
    def _specificity_signal(*, reply: str, pending_dimension: str | None) -> tuple[float, bool]:
        goal_hit = bool(_GOAL_SIGNAL_PATTERN.search(reply))
        timeframe_hit = bool(_TIMEFRAME_SIGNAL_PATTERN.search(reply))
        baseline_hit = bool(_BASELINE_SIGNAL_PATTERN.search(reply))
        constraints_hit = bool(_CONSTRAINT_SIGNAL_PATTERN.search(reply))
        hits = int(goal_hit) + int(timeframe_hit) + int(baseline_hit) + int(constraints_hit)
        specificity = min(1.0, hits / 2.0) if hits else 0.0

        dimension = (pending_dimension or "").strip().lower()
        if not dimension:
            return specificity, False
        if dimension == "goal":
            return specificity, goal_hit
        if dimension == "timeframe":
            return specificity, timeframe_hit
        if dimension == "baseline":
            return specificity, baseline_hit
        if dimension == "constraints":
            return specificity, constraints_hit
        return specificity, False

    @staticmethod
    def _new_task_penalty(*, reply: str, semantic_relevance: float) -> float:
        normalized = reply.strip().lower()
        if not normalized:
            return 0.0
        if semantic_relevance >= 0.20:
            return 0.0
        if _QUESTION_WORD_PATTERN.match(normalized):
            return 0.32
        if _NEW_TASK_PREFIX_PATTERN.match(normalized):
            return 0.28
        return 0.0

    @staticmethod
    def _dimension_hint(pending_dimension: str | None) -> str:
        normalized = (pending_dimension or "").strip().lower()
        if normalized == "goal":
            return "clarify objective desired outcome target result"
        if normalized == "baseline":
            return "clarify current level background experience starting point"
        if normalized == "timeframe":
            return "clarify timeline deadline schedule duration date"
        if normalized == "constraints":
            return "clarify constraints budget limits availability priorities"
        return "clarify request details and assumptions"

    @staticmethod
    def _shape_signal(reply: str, *, question_count: int) -> float:
        words = len(reply.split())
        if words == 0:
            return 0.0
        if words <= 48:
            base = 1.0
        elif words <= 96:
            base = 0.74
        else:
            base = 0.42
        if question_count > 1 and "," in reply:
            base = min(1.0, base + 0.08)
        if "\n" in reply:
            base = min(1.0, base + 0.06)
        return base
