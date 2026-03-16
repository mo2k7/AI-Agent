"""Adapter wrapping PlanClarificationIntentClassifier to satisfy NLPClassifierPort.

Thin delegation layer — all calls forwarded to the underlying classifier.
Defensive error boundary wraps any unexpected exception in AdapterError.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_host.contracts.types.errors import AdapterError

logger = logging.getLogger(__name__)


class SpacyNLPAdapter:
    """Wraps ``PlanClarificationIntentClassifier`` to satisfy ``NLPClassifierPort``."""

    def __init__(self, classifier: Any) -> None:
        self._classifier = classifier

    def classify(
        self,
        *,
        reply_prompt: str,
        root_prompt: str,
        pending_dimension: str | None,
        question_count: int,
    ) -> Any:
        try:
            return self._classifier.classify(
                reply_prompt=reply_prompt,
                root_prompt=root_prompt,
                pending_dimension=pending_dimension,
                question_count=question_count,
            )
        except Exception as exc:
            logger.error("SpacyNLPAdapter.classify failed: %s", exc)
            raise AdapterError(
                f"spacy_nlp.classify failed: {exc}",
                source="spacy_nlp",
                cause=exc,
            ) from exc
