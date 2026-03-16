"""Port interface for NLP classification.

Abstracts the spaCy-based intent classifier so alternative NLP
implementations can be used.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class NLPClassifierPort(Protocol):
    """Abstract interface for clarification intent classification."""

    def classify(
        self,
        *,
        reply_prompt: str,
        root_prompt: str,
        pending_dimension: str | None,
        question_count: int,
    ) -> Any:
        """Classify whether text is a clarification reply vs a new task.

        Returns a ClarificationIntentResult-compatible object.
        """
        ...
