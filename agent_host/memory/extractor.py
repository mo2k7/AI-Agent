"""Heuristic semantic memory extractor.

Model-agnostic extraction from user/assistant turns for persistent memory.
"""

from __future__ import annotations

import re
from typing import Iterable

from .guardrails import assess_text_for_policy_flags, is_storable_memory_text
from .types import MemoryCandidate, MemoryKind

NAME_PATTERN = re.compile(r"\bmy\s+name\s+is\s+([A-Za-z][A-Za-z\-']{1,40})\b", re.IGNORECASE)
PREFERENCE_PATTERN = re.compile(
    r"\b(i\s+(?:prefer|like|want|always\s+want|usually\s+want)|please\s+always)\b",
    re.IGNORECASE,
)
PATH_PATTERN = re.compile(r"(~/[\w\-./]+|/[\w\-./]+)")
TASK_VERB_PATTERN = re.compile(r"\b(find|organize|move|copy|rename|delete|open|extract|search)\b", re.IGNORECASE)


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _content_confidence(text: str, *, base: float = 0.55) -> float:
    length_bonus = min(len(text) / 240.0, 0.25)
    return max(0.0, min(0.99, base + length_bonus))


def extract_semantic_memories(user_prompt: str, assistant_response: str) -> list[MemoryCandidate]:
    """Extract candidate semantic memories from a request/response pair."""
    candidates: list[MemoryCandidate] = []

    if user_prompt.strip() and is_storable_memory_text(user_prompt):
        candidates.extend(_extract_from_user_prompt(user_prompt))

    if assistant_response.strip() and is_storable_memory_text(assistant_response):
        candidates.extend(_extract_from_assistant_response(assistant_response))

    # Stable dedup by (kind, fact_key, content)
    seen: set[tuple[str, str, str]] = set()
    deduped: list[MemoryCandidate] = []
    for candidate in candidates:
        key = (candidate.kind.value, candidate.fact_key, candidate.content)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)

    return deduped


def _extract_from_user_prompt(prompt: str) -> Iterable[MemoryCandidate]:
    flags = assess_text_for_policy_flags(prompt).flags

    yielded: list[MemoryCandidate] = []

    # Profile facts
    match = NAME_PATTERN.search(prompt)
    if match:
        name = match.group(1).strip()
        yielded.append(
            MemoryCandidate(
                kind=MemoryKind.PROFILE_FACT,
                fact_key="profile_name",
                content=f"User name is {name}",
                confidence=0.92,
                source_role="user",
                trust_flags=("user_stated",),
                policy_flags=flags,
            )
        )

    # Preferences
    if PREFERENCE_PATTERN.search(prompt):
        snippet = prompt.strip()
        yielded.append(
            MemoryCandidate(
                kind=MemoryKind.PREFERENCE,
                fact_key=f"preference_{_normalize_key(snippet)[:48]}",
                content=snippet,
                confidence=_content_confidence(snippet, base=0.72),
                source_role="user",
                trust_flags=("user_stated",),
                policy_flags=flags,
            )
        )

    # Active task state from verbs
    if TASK_VERB_PATTERN.search(prompt):
        yielded.append(
            MemoryCandidate(
                kind=MemoryKind.TASK_STATE,
                fact_key=f"task_{_normalize_key(prompt)[:48]}",
                content=prompt.strip(),
                confidence=_content_confidence(prompt, base=0.60),
                source_role="user",
                trust_flags=("user_stated",),
                policy_flags=flags,
            )
        )

    # Artifact references (paths)
    for path in PATH_PATTERN.findall(prompt):
        yielded.append(
            MemoryCandidate(
                kind=MemoryKind.ARTIFACT_REFERENCE,
                fact_key=f"artifact_{_normalize_key(path)}",
                content=f"Referenced path: {path}",
                confidence=0.66,
                source_role="user",
                trust_flags=("user_stated",),
                policy_flags=flags,
            )
        )

    return yielded


def _extract_from_assistant_response(response: str) -> Iterable[MemoryCandidate]:
    flags = assess_text_for_policy_flags(response).flags

    yielded: list[MemoryCandidate] = []
    for path in PATH_PATTERN.findall(response):
        yielded.append(
            MemoryCandidate(
                kind=MemoryKind.ARTIFACT_REFERENCE,
                fact_key=f"artifact_{_normalize_key(path)}",
                content=f"Assistant mentioned path: {path}",
                confidence=0.48,
                source_role="assistant",
                trust_flags=("assistant_inferred",),
                policy_flags=flags,
            )
        )

    return yielded
