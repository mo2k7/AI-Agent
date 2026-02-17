"""Typed models for session and semantic memory management."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryMode(str, Enum):
    """Controls how memory is used for a prompt/session."""

    ON = "on"
    OFF = "off"
    EPHEMERAL = "ephemeral"


class MemoryKind(str, Enum):
    """Semantic memory categories."""

    PREFERENCE = "preference"
    PROFILE_FACT = "profile_fact"
    TASK_STATE = "task_state"
    ARTIFACT_REFERENCE = "artifact_reference"


@dataclass(frozen=True)
class SessionRecord:
    """Persisted session metadata."""

    session_id: str
    title: str
    memory_mode: MemoryMode
    created_at: float
    updated_at: float
    last_activity: float
    status: str = "active"


@dataclass(frozen=True)
class MemoryCandidate:
    """Candidate semantic memory extracted from a turn."""

    kind: MemoryKind
    fact_key: str
    content: str
    confidence: float
    source_role: str
    trust_flags: tuple[str, ...] = ()
    policy_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryRecord:
    """Stored semantic memory with provenance."""

    memory_id: str
    session_id: str
    kind: MemoryKind
    fact_key: str
    content: str
    confidence: float
    source_message_id: str
    trust_flags: tuple[str, ...]
    policy_flags: tuple[str, ...]
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class MemoryHit:
    """Retrieval result used for memory context composition."""

    memory_id: str
    session_id: str
    kind: MemoryKind
    content: str
    confidence: float
    score: float
    trust_flags: tuple[str, ...]
    policy_flags: tuple[str, ...]


@dataclass(frozen=True)
class MemoryContextBundle:
    """Context assembled from prior memory before model invocation."""

    session_id: str
    recent_turns: tuple[tuple[str, str], ...] = ()
    historical_turns: tuple[tuple[str, str], ...] = ()
    summary: str = ""
    semantic_hits: tuple[MemoryHit, ...] = ()


@dataclass(frozen=True)
class SessionMessage:
    """Persisted chat turn."""

    message_id: str
    role: str
    content: str
    created_at: float
    turn_index: int
    meta: dict[str, Any] = field(default_factory=dict)
