"""Tests for strict embedding-backed retrieval behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent_host.memory.embeddings import DIMENSION, EmbeddingService
from agent_host.memory.retriever import Candidate, cosine_similarity, encode_text_semantic, rank_candidates
from agent_host.memory.types import MemoryKind, MemoryRecord


def _make_embedding_response(vectors: list[list[float]]):
    embeddings = [SimpleNamespace(values=v) for v in vectors]
    return SimpleNamespace(embeddings=embeddings, metadata=None)


def _make_embedding_service(vector: list[float] | None = None) -> EmbeddingService:
    client = MagicMock()
    if vector is None:
        client.models.embed_content.side_effect = RuntimeError("API unavailable")
    else:
        client.models.embed_content.return_value = _make_embedding_response([vector])
    return EmbeddingService(client)


def _make_record(
    *,
    memory_id: str = "mem-1",
    session_id: str = "sess-1",
    confidence: float = 0.8,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        session_id=session_id,
        kind=MemoryKind.PREFERENCE,
        fact_key="test_key",
        content="test content",
        confidence=confidence,
        source_message_id="msg-1",
        trust_flags=(),
        policy_flags=(),
        created_at=1000.0,
        updated_at=1000.0,
    )


def test_encode_text_semantic_requires_embedding_service() -> None:
    with pytest.raises(RuntimeError, match="Embedding service is required"):
        encode_text_semantic("user prefers dark mode", None)


def test_encode_text_semantic_raises_on_embedding_failure() -> None:
    service = _make_embedding_service(vector=None)
    with pytest.raises(RuntimeError, match="Embedding service returned no vector"):
        encode_text_semantic("user prefers dark mode", service)


def test_rank_candidates_requires_embedding_service() -> None:
    record = _make_record()
    candidate = Candidate(
        record=record,
        vector=tuple([0.1] * DIMENSION),
        token_set=("test", "content"),
    )
    with pytest.raises(RuntimeError, match="Embedding service is required"):
        rank_candidates(
            query="test",
            query_session_id="sess-1",
            candidates=[candidate],
            embedding_service=None,
        )


def test_rank_candidates_prefers_higher_semantic_similarity() -> None:
    query_vec = [0.0] * DIMENSION
    query_vec[0] = 1.0
    service = _make_embedding_service(query_vec)

    good = Candidate(
        record=_make_record(memory_id="good", confidence=0.9),
        vector=tuple(query_vec),
        token_set=("user", "dark", "mode"),
    )
    bad_vec = [0.0] * DIMENSION
    bad_vec[1] = 1.0
    bad = Candidate(
        record=_make_record(memory_id="bad", confidence=0.9),
        vector=tuple(bad_vec),
        token_set=("user", "dark", "mode"),
    )

    hits = rank_candidates(
        query="dark mode preference",
        query_session_id="sess-1",
        candidates=[bad, good],
        embedding_service=service,
    )
    assert [hit.memory_id for hit in hits[:2]] == ["good", "bad"]


def test_cosine_similarity_dimension_mismatch_returns_zero() -> None:
    assert cosine_similarity((1.0, 0.0), (1.0,)) == 0.0
