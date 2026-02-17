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

    _DEFAULT_MODELS: tuple[str, ...] = (
        "en_core_web_trf",
        "en_core_web_lg",
        "en_core_web_md",
        "en_core_web_sm",
    )

    def __init__(self, model_candidates: tuple[str, ...] | None = None) -> None:
        self._model_candidates = model_candidates or self._DEFAULT_MODELS
        self._load_attempted = False
        self._nlp: Any = None
        self._loaded_model_name = ""
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
        """Return clarification-intent probability using spaCy when available."""
        sanitized_reply = self.sanitize_text(reply_prompt)
        sanitized_root = self.sanitize_text(root_prompt)
        if not sanitized_reply:
            return ClarificationIntentResult(
                is_clarification_reply=False,
                confidence=0.0,
                source="unavailable",
                model_name="none",
                sanitized_reply="",
                sanitized_root_prompt=sanitized_root,
            )

        nlp = self._ensure_model_loaded()
        if nlp is None:
            return ClarificationIntentResult(
                is_clarification_reply=False,
                confidence=0.0,
                source="unavailable",
                model_name="none",
                sanitized_reply=sanitized_reply,
                sanitized_root_prompt=sanitized_root,
            )

        reply_doc = nlp(sanitized_reply)
        root_doc = nlp(sanitized_root or "plan request")
        dim_doc = nlp(self._dimension_hint(pending_dimension))
        diversion_doc = nlp("new unrelated request different task change topic")

        root_similarity = self._safe_similarity(reply_doc, root_doc)
        dimension_similarity = self._safe_similarity(reply_doc, dim_doc)
        diversion_similarity = self._safe_similarity(reply_doc, diversion_doc)

        reply_tokens = self._token_set(sanitized_reply)
        root_tokens = self._token_set(sanitized_root)
        overlap_ratio = 0.0
        if reply_tokens:
            overlap_ratio = len(reply_tokens.intersection(root_tokens)) / len(reply_tokens)

        reply_lemmas = self._lemma_set(reply_doc)
        root_lemmas = self._lemma_set(root_doc)
        dim_lemmas = self._lemma_set(dim_doc)
        lemma_overlap_root = 0.0
        lemma_overlap_dim = 0.0
        if reply_lemmas:
            lemma_overlap_root = len(reply_lemmas.intersection(root_lemmas)) / len(reply_lemmas)
            lemma_overlap_dim = len(reply_lemmas.intersection(dim_lemmas)) / len(reply_lemmas)

        specificity_score, dimension_match = self._specificity_signal(
            reply=sanitized_reply,
            pending_dimension=pending_dimension,
        )
        semantic_relevance = max(
            root_similarity,
            dimension_similarity,
            lemma_overlap_root,
            lemma_overlap_dim,
        )
        diversion_penalty = max(0.0, diversion_similarity - semantic_relevance)
        shape_signal = self._shape_signal(sanitized_reply, question_count=question_count)
        imperative_shift_penalty = self._imperative_topic_shift_penalty(
            reply_doc=reply_doc,
            lemma_overlap_root=lemma_overlap_root,
            lemma_overlap_dim=lemma_overlap_dim,
        )

        confidence = (
            (semantic_relevance * 0.28)
            + (overlap_ratio * 0.20)
            + (shape_signal * 0.16)
            + (specificity_score * 0.36)
            + (0.08 if dimension_match else 0.0)
            - (diversion_penalty * 0.35)
            - imperative_shift_penalty
        )
        confidence = max(0.0, min(1.0, confidence))

        threshold = 0.36 if question_count > 1 else 0.40
        return ClarificationIntentResult(
            is_clarification_reply=confidence >= threshold,
            confidence=confidence,
            source="spacy",
            model_name=self._loaded_model_name,
            sanitized_reply=sanitized_reply,
            sanitized_root_prompt=sanitized_root,
        )

    def _ensure_model_loaded(self) -> Any:
        if self._load_attempted:
            return self._nlp
        self._load_attempted = True
        try:
            # Patch pydantic.v1 to handle Python 3.14 compatibility issue in confection
            try:
                import pydantic.v1.main
                
                # Only patch if not already patched
                if not getattr(pydantic.v1.main.ModelMetaclass, "_patched_for_regex", False):
                    original_new = pydantic.v1.main.ModelMetaclass.__new__
                    
                    def patched_new(mcs, name, bases, namespace, **kwargs):
                        try:
                            return original_new(mcs, name, bases, namespace, **kwargs)
                        except TypeError as e:
                            if 'unable to infer type for attribute "REGEX"' in str(e):
                                # Define explicit type for REGEX to satisfy pydantic
                                if "REGEX" in namespace:
                                    # Fallback: remove the problematic attribute from validation
                                    # or allow it to be ignored by not calling super new if possible,
                                    # but we need a class.
                                    # Better approach: modify namespace before calling original
                                    namespace["__annotations__"] = namespace.get("__annotations__", {})
                                    namespace["__annotations__"]["REGEX"] = Any
                                    return original_new(mcs, name, bases, namespace, **kwargs)
                            raise

                    # Since __new__ is a static method on the metaclass, we wrap it properly
                    # Actually, pydantic.v1.main.ModelMetaclass is a type.
                    # We need to patch the method on the class.
                    pydantic.v1.main.ModelMetaclass.__new__ = patched_new  # type: ignore
                    pydantic.v1.main.ModelMetaclass._patched_for_regex = True  # type: ignore
            except ImportError:
                pass

            import spacy
        except Exception as exc:  # pragma: no cover - import path is environment-specific
            self._load_error = f"spacy import failed: {exc}"
            return None

        for model_name in self._model_candidates:
            try:
                self._nlp = spacy.load(model_name)
                self._loaded_model_name = model_name
                self._load_error = None
                return self._nlp
            except Exception:
                continue
        self._load_error = "no configured spaCy model is installed"
        return None

    @staticmethod
    def _safe_similarity(doc_a: Any, doc_b: Any) -> float:
        has_vector_a = bool(getattr(doc_a, "has_vector", False))
        has_vector_b = bool(getattr(doc_b, "has_vector", False))
        if not has_vector_a or not has_vector_b:
            return 0.0
        vector_norm_a = float(getattr(doc_a, "vector_norm", 0.0) or 0.0)
        vector_norm_b = float(getattr(doc_b, "vector_norm", 0.0) or 0.0)
        if vector_norm_a <= 0.0 or vector_norm_b <= 0.0:
            return 0.0
        try:
            value = float(doc_a.similarity(doc_b))
        except Exception:
            return 0.0
        if value != value:  # NaN check
            return 0.0
        return max(0.0, min(1.0, value))

    @staticmethod
    def _token_set(text: str) -> set[str]:
        return set(_TOKEN_PATTERN.findall(text.lower()))

    @staticmethod
    def _lemma_set(doc: Any) -> set[str]:
        values: set[str] = set()
        for token in doc:
            lemma = str(getattr(token, "lemma_", "")).strip().lower()
            if len(lemma) < 3:
                continue
            if not lemma.isalpha():
                continue
            if bool(getattr(token, "is_stop", False)):
                continue
            values.add(lemma)
        return values

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
    def _imperative_topic_shift_penalty(
        *,
        reply_doc: Any,
        lemma_overlap_root: float,
        lemma_overlap_dim: float,
    ) -> float:
        if not reply_doc:
            return 0.0
        first = reply_doc[0]
        first_pos = str(getattr(first, "pos_", "")).upper()
        if first_pos not in {"VERB", "AUX"}:
            return 0.0
        if lemma_overlap_root >= 0.15 or lemma_overlap_dim >= 0.15:
            return 0.0
        return 0.20

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


