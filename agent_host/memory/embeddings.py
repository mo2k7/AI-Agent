"""Semantic embedding service backed by Gemini text-embedding-004.

Provides real 768-dimensional dense embeddings that capture semantic meaning.
Thread-safe LRU cache prevents redundant API calls within a session.

Usage
-----
    from google import genai
    client = genai.Client(api_key="...")
    svc = EmbeddingService(client)
    vec = svc.embed("user prefers dark mode", task_type="RETRIEVAL_DOCUMENT")
    # vec is a 768-float tuple
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.genai import Client as GenaiClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL = "text-embedding-004"
DIMENSION = 768
MAX_CACHE_SIZE = 512

# Gemini task-type strings that influence the embedding geometry.
TASK_STORE = "RETRIEVAL_DOCUMENT"
TASK_QUERY = "RETRIEVAL_QUERY"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EmbeddingService:
    """Generates semantic embeddings via the Gemini ``text-embedding-004`` model.

    * **Thread-safe** — an internal ``OrderedDict`` LRU cache is guarded by a
      lock so concurrent callers (e.g. ``run_in_executor`` threads) never
      corrupt the cache.
    * **Strict runtime** — embedding failures raise exceptions so callers can
      fail fast instead of silently degrading retrieval quality.
    """

    def __init__(self, genai_client: GenaiClient) -> None:
        self._client = genai_client
        self._cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._cache_lock = threading.Lock()

    # ----- public API -------------------------------------------------------

    def embed(
        self,
        text: str,
        *,
        task_type: str = TASK_STORE,
    ) -> tuple[float, ...]:
        """Return a 768-dim embedding for *text*.

        Results are cached keyed on ``(text, task_type)`` so repeated calls
        with the same arguments are free.
        """
        if not text or not text.strip():
            raise ValueError("Embedding text must be non-empty.")

        cache_key = f"{task_type}::{text}"

        with self._cache_lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]

        # -- Call Gemini API (outside the lock) --
        try:
            response = self._client.models.embed_content(
                model=MODEL,
                contents=[text],
                config={"task_type": task_type},
            )

            if (
                response is None
                or response.embeddings is None
                or len(response.embeddings) == 0
            ):
                raise RuntimeError("Embedding API returned empty response.")

            values = response.embeddings[0].values
            if values is None or len(values) == 0:
                raise RuntimeError("Embedding API returned empty vector values.")

            vector = tuple(float(v) for v in values)

        except Exception as exc:
            logger.error("Embedding API call failed", exc_info=True)
            raise RuntimeError("Embedding API call failed.") from exc

        # -- Store in cache (re-check to avoid overwriting concurrent insert) --
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
            self._cache[cache_key] = vector
            self._cache.move_to_end(cache_key)
            while len(self._cache) > MAX_CACHE_SIZE:
                self._cache.popitem(last=False)

        return vector

    def embed_batch(
        self,
        texts: list[str],
        *,
        task_type: str = TASK_STORE,
    ) -> list[tuple[float, ...]]:
        """Batch-embed multiple texts in one API call.

        Returns a list aligned with *texts* of 768-dim vectors.
        """
        if not texts:
            return []

        # Check cache for every item first; record which need API calls.
        results: list[tuple[float, ...]] = [tuple(0.0 for _ in range(DIMENSION)) for _ in range(len(texts))]
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        with self._cache_lock:
            for i, text in enumerate(texts):
                if not text or not text.strip():
                    raise ValueError("Embedding text must be non-empty.")
                cache_key = f"{task_type}::{text}"
                if cache_key in self._cache:
                    self._cache.move_to_end(cache_key)
                    results[i] = self._cache[cache_key]
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)

        if not uncached_texts:
            return results

        # -- Call Gemini API for uncached texts --
        try:
            response = self._client.models.embed_content(
                model=MODEL,
                contents=uncached_texts,
                config={"task_type": task_type},
            )

            if response is None or response.embeddings is None:
                raise RuntimeError("Batch embedding API returned empty response.")

            if len(response.embeddings) < len(uncached_texts):
                raise RuntimeError(
                    (
                        "Batch embedding returned partial results: "
                        f"requested={len(uncached_texts)} received={len(response.embeddings)}"
                    )
                )

            for j, embedding in enumerate(response.embeddings):
                if j >= len(uncached_indices):
                    break
                idx = uncached_indices[j]
                values = embedding.values
                if values is None or len(values) == 0:
                    raise RuntimeError(f"Batch embedding {j} returned null/empty values.")
                vector = tuple(float(v) for v in values)
                results[idx] = vector

                # Cache it
                cache_key = f"{task_type}::{uncached_texts[j]}"
                with self._cache_lock:
                    self._cache[cache_key] = vector
                    self._cache.move_to_end(cache_key)
                    while len(self._cache) > MAX_CACHE_SIZE:
                        self._cache.popitem(last=False)

        except Exception as exc:
            logger.error("Batch embedding API call failed", exc_info=True)
            raise RuntimeError("Batch embedding API call failed.") from exc

        return results
