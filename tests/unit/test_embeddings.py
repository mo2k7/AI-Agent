"""Unit tests for the EmbeddingService (Gemini text-embedding-004 wrapper)."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent_host.memory.embeddings import (
    DIMENSION,
    EmbeddingService,
    MAX_CACHE_SIZE,
    MODEL,
    TASK_QUERY,
    TASK_STORE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_embedding_response(vectors: list[list[float]]):
    """Build a fake EmbedContentResponse matching the genai SDK shape."""
    embeddings = []
    for vec in vectors:
        embeddings.append(SimpleNamespace(values=vec))
    return SimpleNamespace(embeddings=embeddings, metadata=None)


def _make_genai_client(response=None, side_effect=None) -> MagicMock:
    """Build a mock genai.Client with models.embed_content."""
    client = MagicMock()
    if side_effect is not None:
        client.models.embed_content.side_effect = side_effect
    else:
        client.models.embed_content.return_value = response
    return client


# ---------------------------------------------------------------------------
# Tests — embed()
# ---------------------------------------------------------------------------


class TestEmbedSingle:
    def test_returns_768_dim_vector(self):
        fake_vec = [0.1] * DIMENSION
        client = _make_genai_client(_make_embedding_response([fake_vec]))
        svc = EmbeddingService(client)

        result = svc.embed("user prefers dark mode")
        assert result is not None
        assert len(result) == DIMENSION
        assert isinstance(result, tuple)
        assert result[0] == pytest.approx(0.1)

    def test_calls_api_with_correct_params(self):
        fake_vec = [0.5] * DIMENSION
        client = _make_genai_client(_make_embedding_response([fake_vec]))
        svc = EmbeddingService(client)

        svc.embed("hello world", task_type=TASK_QUERY)
        client.models.embed_content.assert_called_once_with(
            model=MODEL,
            contents=["hello world"],
            config={"task_type": TASK_QUERY},
        )

    def test_returns_none_on_api_error(self):
        client = _make_genai_client(side_effect=RuntimeError("network down"))
        svc = EmbeddingService(client)

        with pytest.raises(RuntimeError, match="Embedding API call failed"):
            svc.embed("some text")

    def test_returns_none_for_empty_text(self):
        client = _make_genai_client()
        svc = EmbeddingService(client)

        with pytest.raises(ValueError, match="non-empty"):
            svc.embed("")
        with pytest.raises(ValueError, match="non-empty"):
            svc.embed("   ")
        client.models.embed_content.assert_not_called()

    def test_returns_none_on_empty_response(self):
        client = _make_genai_client(SimpleNamespace(embeddings=None, metadata=None))
        svc = EmbeddingService(client)

        with pytest.raises(RuntimeError, match="Embedding API call failed"):
            svc.embed("hello")

    def test_returns_none_on_empty_embeddings_list(self):
        client = _make_genai_client(SimpleNamespace(embeddings=[], metadata=None))
        svc = EmbeddingService(client)

        with pytest.raises(RuntimeError, match="Embedding API call failed"):
            svc.embed("hello")

    def test_returns_none_on_none_values(self):
        response = SimpleNamespace(
            embeddings=[SimpleNamespace(values=None)], metadata=None
        )
        client = _make_genai_client(response)
        svc = EmbeddingService(client)

        with pytest.raises(RuntimeError, match="Embedding API call failed"):
            svc.embed("hello")


# ---------------------------------------------------------------------------
# Tests — caching
# ---------------------------------------------------------------------------


class TestEmbedCache:
    def test_cache_hit_avoids_second_api_call(self):
        fake_vec = [0.2] * DIMENSION
        client = _make_genai_client(_make_embedding_response([fake_vec]))
        svc = EmbeddingService(client)

        first = svc.embed("cached text")
        second = svc.embed("cached text")

        assert first == second
        assert client.models.embed_content.call_count == 1

    def test_different_task_types_have_separate_cache_keys(self):
        fake_vec = [0.3] * DIMENSION
        client = _make_genai_client(_make_embedding_response([fake_vec]))
        svc = EmbeddingService(client)

        svc.embed("same text", task_type=TASK_STORE)
        svc.embed("same text", task_type=TASK_QUERY)

        assert client.models.embed_content.call_count == 2

    def test_cache_eviction_at_max_size(self):
        """Cache evicts oldest entries when exceeding MAX_CACHE_SIZE."""
        svc = EmbeddingService(MagicMock())
        fake_vec = tuple([0.1] * DIMENSION)

        # Manually fill cache to max
        with svc._cache_lock:
            for i in range(MAX_CACHE_SIZE):
                svc._cache[f"RETRIEVAL_DOCUMENT::text_{i}"] = fake_vec

        # Add one more via embed()
        client = _make_genai_client(
            _make_embedding_response([[0.9] * DIMENSION])
        )
        svc._client = client
        svc.embed("overflow_text")

        with svc._cache_lock:
            assert len(svc._cache) == MAX_CACHE_SIZE
            # First entry should have been evicted
            assert "RETRIEVAL_DOCUMENT::text_0" not in svc._cache
            # New entry should be present
            assert "RETRIEVAL_DOCUMENT::overflow_text" in svc._cache

    def test_cache_thread_safety(self):
        """Concurrent embed calls don't corrupt the cache."""
        call_count = 0

        def counting_embed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _make_embedding_response([[float(call_count)] * DIMENSION])

        client = _make_genai_client(side_effect=counting_embed)
        svc = EmbeddingService(client)

        errors: list[Exception] = []

        def worker(text: str):
            try:
                for _ in range(10):
                    result = svc.embed(text)
                    assert result is not None
                    assert len(result) == DIMENSION
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(f"text_{i}",)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"


# ---------------------------------------------------------------------------
# Tests — embed_batch()
# ---------------------------------------------------------------------------


class TestEmbedBatch:
    def test_batch_returns_aligned_results(self):
        vecs = [[0.1] * DIMENSION, [0.2] * DIMENSION, [0.3] * DIMENSION]
        client = _make_genai_client(_make_embedding_response(vecs))
        svc = EmbeddingService(client)

        results = svc.embed_batch(["a", "b", "c"])
        assert len(results) == 3
        for r in results:
            assert r is not None
            assert len(r) == DIMENSION

    def test_empty_list_returns_empty(self):
        client = _make_genai_client()
        svc = EmbeddingService(client)

        assert svc.embed_batch([]) == []
        client.models.embed_content.assert_not_called()

    def test_batch_uses_cache_for_already_seen(self):
        vec = [0.4] * DIMENSION
        client = _make_genai_client(_make_embedding_response([vec]))
        svc = EmbeddingService(client)

        # Pre-cache one entry
        svc.embed("already cached")

        # Batch with the cached item + a new one
        client.models.embed_content.return_value = _make_embedding_response(
            [[0.5] * DIMENSION]
        )
        results = svc.embed_batch(["already cached", "new text"])

        assert results[0] is not None
        assert results[1] is not None
        # Only "new text" should trigger a second API call
        assert client.models.embed_content.call_count == 2

    def test_batch_handles_api_failure_gracefully(self):
        client = _make_genai_client(side_effect=RuntimeError("API down"))
        svc = EmbeddingService(client)

        with pytest.raises(RuntimeError, match="Batch embedding API call failed"):
            svc.embed_batch(["a", "b"])

    def test_batch_skips_empty_strings(self):
        client = _make_genai_client(_make_embedding_response([[0.1] * DIMENSION]))
        svc = EmbeddingService(client)

        with pytest.raises(ValueError, match="non-empty"):
            svc.embed_batch(["", "real text", "  "])
