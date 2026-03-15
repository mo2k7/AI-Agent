"""Hybrid lexical/vector retrieval for semantic memory hits."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from .types import MemoryHit, MemoryKind, MemoryRecord

if TYPE_CHECKING:
    from .embeddings import EmbeddingService

logger = logging.getLogger(__name__)

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_\-]{2,}")


@dataclass(frozen=True)
class EncodedText:
    """Tokenized + vectorized text representation."""

    tokens: tuple[str, ...]
    vector: tuple[float, ...]


@dataclass(frozen=True)
class Candidate:
    """Candidate record with retrieval metadata."""

    record: MemoryRecord
    vector: tuple[float, ...]
    token_set: tuple[str, ...]


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(tok.lower() for tok in TOKEN_PATTERN.findall(text.lower()))


def encode_text_semantic(
    text: str,
    embedding_service: EmbeddingService | None,
    *,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> EncodedText:
    """Semantic encoding with Gemini embeddings.

    Strict runtime requires a working embedding service. Missing or failed
    embeddings are fatal for semantic memory indexing/retrieval.
    """
    tokens = tokenize(text)
    if embedding_service is None:
        raise RuntimeError("Embedding service is required for semantic retrieval.")
    try:
        vector = embedding_service.embed(text, task_type=task_type)
    except Exception:
        vector = None
    if vector is None:
        raise RuntimeError("Embedding service returned no vector")
    return EncodedText(tokens=tokens, vector=vector)


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_vec = list(left)
    right_vec = list(right)
    if not left_vec or not right_vec or len(left_vec) != len(right_vec):
        return 0.0

    dot = sum(a * b for a, b in zip(left_vec, right_vec))
    norm_l = sum(a * a for a in left_vec) ** 0.5
    norm_r = sum(b * b for b in right_vec) ** 0.5
    if norm_l == 0.0 or norm_r == 0.0:
        return 0.0
    return dot / (norm_l * norm_r)


def jaccard_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    a = set(left)
    b = set(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def rank_candidates(
    *,
    query: str,
    query_session_id: str,
    candidates: Iterable[Candidate],
    max_hits: int = 8,
    embedding_service: EmbeddingService | None,
) -> list[MemoryHit]:
    """Rank memory candidates using hybrid retrieval with trust-aware bias."""
    encoded_query = encode_text_semantic(
        query, embedding_service, task_type="RETRIEVAL_QUERY"
    )
    # Weights: with real embeddings, semantic similarity is much more
    # meaningful than lexical overlap.  Lexical still helps for exact
    # token matches, so we keep it as a minority signal.
    w_lexical = 0.15
    w_semantic = 0.55
    w_confidence = 0.30
    ranked: list[MemoryHit] = []

    for candidate in candidates:
        lexical = jaccard_similarity(encoded_query.tokens, candidate.token_set)
        semantic = cosine_similarity(encoded_query.vector, candidate.vector)
        confidence = candidate.record.confidence
        same_session_boost = 0.08 if candidate.record.session_id == query_session_id else 0.0
        suspicious_penalty = (
            0.2 if "prompt_injection_suspected" in candidate.record.policy_flags else 0.0
        )
        score = (w_lexical * lexical) + (w_semantic * semantic) + (w_confidence * confidence)
        score = max(0.0, score + same_session_boost - suspicious_penalty)

        ranked.append(
            MemoryHit(
                memory_id=candidate.record.memory_id,
                session_id=candidate.record.session_id,
                kind=MemoryKind(candidate.record.kind),
                content=candidate.record.content,
                confidence=candidate.record.confidence,
                score=score,
                trust_flags=candidate.record.trust_flags,
                policy_flags=candidate.record.policy_flags,
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:max_hits]
